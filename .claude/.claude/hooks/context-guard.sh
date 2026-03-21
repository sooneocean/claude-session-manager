#!/bin/bash
# Hook: PostToolUse (all tools)
# Purpose: Monitor context window usage and warn before hitting the limit
#          v3.0.0: Added cost-based warning integration
#
# Strategy:
#   1. Track transcript file size (direct proxy for context usage)
#   2. Track tool call count (backup metric)
#   3. Warn at 3 levels, only on level transitions (no spam)
#   4. (v3.0.0) Also check session cost from cost-tracker JSONL
#
# Thresholds (tuned for 1M context window):
#   Level 1 (Notice):   transcript > 1500KB OR 120+ calls
#   Level 2 (Warning):  transcript > 2500KB OR 200+ calls
#   Level 3 (Critical): transcript > 3500KB OR 300+ calls

INPUT=$(cat)

# ── Extract fields ──
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"' 2>/dev/null)
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)

[ -z "$SESSION_ID" ] && exit 0

# ── Session state file ──
STATE_FILE="/tmp/.claude_ctx_guard_${SESSION_ID}"

# ── Read previous state ──
CALLS=0
WARNED_LEVEL=0
COST_WARNED=0
if [ -f "$STATE_FILE" ]; then
  CALLS=$(sed -n '1p' "$STATE_FILE" 2>/dev/null || echo 0)
  WARNED_LEVEL=$(sed -n '2p' "$STATE_FILE" 2>/dev/null || echo 0)
  COST_WARNED=$(sed -n '3p' "$STATE_FILE" 2>/dev/null || echo 0)
  # Ensure numeric
  CALLS=$((CALLS + 0))
  WARNED_LEVEL=$((WARNED_LEVEL + 0))
  COST_WARNED=$((COST_WARNED + 0))
fi
CALLS=$((CALLS + 1))

# ── Measure transcript size (primary metric) ──
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

# ── Persist state ──
printf "%d\n%d\n%d\n" "$CALLS" "$LEVEL" "$COST_WARNED" > "$STATE_FILE"

# ── Output warning only on level increase (minimize context overhead) ──
if [ "$LEVEL" -gt 0 ] && [ "$LEVEL" -gt "$WARNED_LEVEL" ]; then
  case $LEVEL in
    1)
      echo "[CTX-GUARD] transcript=${TRANSCRIPT_KB}KB calls=${CALLS} — Context 使用量偏高，控制後續操作規模。"
      ;;
    2)
      echo "[CTX-GUARD ⚠️] transcript=${TRANSCRIPT_KB}KB calls=${CALLS} — 建議：持久化 SDD Context 後執行 /compact。"
      ;;
    3)
      echo "[CTX-GUARD 🚨] transcript=${TRANSCRIPT_KB}KB calls=${CALLS} — 立即持久化所有狀態並 /compact！不要再執行大型 Read/Write！"
      ;;
  esac
fi

exit 0
