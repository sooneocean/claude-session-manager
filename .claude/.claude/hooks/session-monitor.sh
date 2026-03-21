#!/bin/bash
# Hook: PostToolUse (all tools)
# Purpose: Unified session monitor — replaces context-guard + strategic-compact
#
# Key optimization: INSTANT EXIT for read-only tools (Read, Grep, Glob)
# These are ~70% of tool calls and don't need monitoring.
#
# Thresholds (tuned for 1M context window):
#   Level 1 (Notice):   transcript > 1500KB OR 120+ calls
#   Level 2 (Warning):  transcript > 2500KB OR 200+ calls
#   Level 3 (Critical): transcript > 3500KB OR 300+ calls
#   Compact suggest:    every 200 non-readonly calls

INPUT=$(cat)

# ── Fast extract tool name (before full JSON parse) ──
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"' 2>/dev/null)

# ── INSTANT EXIT for read-only tools — no state, no overhead ──
case "$TOOL_NAME" in
  Read|Grep|Glob) exit 0 ;;
esac

# ── Extract remaining fields (only for non-readonly tools) ──
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)

[ -z "$SESSION_ID" ] && exit 0

# ── Profile check ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/lib/hook-profile.sh" ]; then
  source "$SCRIPT_DIR/lib/hook-profile.sh"
  check_hook "session-monitor"
fi

# ── Single state file (merged from context-guard + strategic-compact) ──
STATE_FILE="/tmp/.claude_session_monitor_${SESSION_ID}"
CALLS=0
WARNED_LEVEL=0
LAST_SUGGESTED=0
if [ -f "$STATE_FILE" ]; then
  CALLS=$(sed -n '1p' "$STATE_FILE" 2>/dev/null || echo 0)
  WARNED_LEVEL=$(sed -n '2p' "$STATE_FILE" 2>/dev/null || echo 0)
  LAST_SUGGESTED=$(sed -n '3p' "$STATE_FILE" 2>/dev/null || echo 0)
  CALLS=$((CALLS + 0))
  WARNED_LEVEL=$((WARNED_LEVEL + 0))
  LAST_SUGGESTED=$((LAST_SUGGESTED + 0))
fi
CALLS=$((CALLS + 1))

# ── Measure transcript size ──
TRANSCRIPT_KB=0
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
  TRANSCRIPT_BYTES=$(wc -c < "$TRANSCRIPT" 2>/dev/null | tr -d ' ')
  TRANSCRIPT_KB=$((TRANSCRIPT_BYTES / 1024))
fi

# ── Determine warning level ──
LEVEL=0
if [ "$TRANSCRIPT_KB" -gt 3500 ] || [ "$CALLS" -ge 300 ]; then
  LEVEL=3
elif [ "$TRANSCRIPT_KB" -gt 2500 ] || [ "$CALLS" -ge 200 ]; then
  LEVEL=2
elif [ "$TRANSCRIPT_KB" -gt 1500 ] || [ "$CALLS" -ge 120 ]; then
  LEVEL=1
fi

# ── Compact suggestion (every 200 non-readonly calls) ──
SINCE_LAST=$((CALLS - LAST_SUGGESTED))
if [ $SINCE_LAST -ge 200 ]; then
  LAST_SUGGESTED=$CALLS
fi

# ── Persist state ──
printf "%d\n%d\n%d\n" "$CALLS" "$LEVEL" "$LAST_SUGGESTED" > "$STATE_FILE"

# ── Output (only on level transitions — minimize context noise) ──
if [ "$LEVEL" -gt 0 ] && [ "$LEVEL" -gt "$WARNED_LEVEL" ]; then
  case $LEVEL in
    1) echo "[SESSION] transcript=${TRANSCRIPT_KB}KB calls=${CALLS} — Context 使用量偏高。" ;;
    2) echo "[SESSION ⚠️] transcript=${TRANSCRIPT_KB}KB calls=${CALLS} — 建議 /compact。" ;;
    3) echo "[SESSION 🚨] transcript=${TRANSCRIPT_KB}KB calls=${CALLS} — 立即 /compact！" ;;
  esac
elif [ $SINCE_LAST -eq 0 ] && [ "$CALLS" -gt 0 ]; then
  echo "[SESSION] ${CALLS} tool calls. Consider /compact if context feels stale."
fi

exit 0
