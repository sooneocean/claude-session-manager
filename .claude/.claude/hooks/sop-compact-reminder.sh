#!/bin/bash
# Hook: SessionStart on compact
# Purpose: Re-inject SOP persistent state after context window compaction
#
# Strategy: Don't tell Claude to "go read files" — inject the actual data
# so it's guaranteed to be in context after compaction.
#
# Size guard: If sdd_context.json > 50KB, only inject key fields.
# Multi-SOP: If multiple in_progress found, list all for user to choose.

INPUT=$(cat)
PROJECT_DIR=$(echo "$INPUT" | jq -r '.cwd // "."' 2>/dev/null)
[ -z "$PROJECT_DIR" ] && PROJECT_DIR="."

MAX_JSON_SIZE=51200  # 50KB threshold

# ══════════════════════════════════════
# 1. Collect all active SDD Contexts
# ══════════════════════════════════════
ACTIVE_CONTEXTS=()   # array of "source|path"

# Unified: Quick & Full Spec all under dev/specs/*/sdd_context.json
COMPLETED_SUMMARY=""
for f in $(ls -td "$PROJECT_DIR"/dev/specs/*/sdd_context.json 2>/dev/null); do
  [ -f "$f" ] || continue
  STATUS=$(jq -r '.sdd_context.status // empty' "$f" 2>/dev/null)
  SPEC_MODE=$(jq -r '.sdd_context.spec_mode // "unknown"' "$f" 2>/dev/null)
  FEATURE=$(jq -r '.sdd_context.feature // "unknown"' "$f" 2>/dev/null)
  if [ "$STATUS" = "in_progress" ]; then
    case "$SPEC_MODE" in
      quick) SOURCE="Quick" ;;
      full)  SOURCE="Full Spec" ;;
      *)     SOURCE="$SPEC_MODE" ;;
    esac
    ACTIVE_CONTEXTS+=("$SOURCE|$f")
  elif [ "$STATUS" = "completed" ]; then
    # Only inject one-line summary for completed features (context hygiene)
    COMPLETED_SUMMARY="${COMPLETED_SUMMARY}\n- [Completed] ${FEATURE}"
  fi
done

# ══════════════════════════════════════
# 2. Helper: try node-based recovery (priority path)
# ══════════════════════════════════════
NODE_RECOVERY_SUCCESS=0

try_node_recovery() {
  local SPEC_FOLDER="$1"
  local NODES_DIR="$PROJECT_DIR/$SPEC_FOLDER/nodes"

  [ -d "$NODES_DIR" ] || return 1

  local NODE_PATH=""
  local RECOVERY_NOTE=""

  # Path A: Read CURRENT pointer
  local CURRENT_FILE="$NODES_DIR/CURRENT"
  if [ -f "$CURRENT_FILE" ]; then
    local CURRENT_NODE
    CURRENT_NODE=$(cat "$CURRENT_FILE" | tr -d '[:space:]')
    if [ -f "$NODES_DIR/$CURRENT_NODE" ] && [ -s "$NODES_DIR/$CURRENT_NODE" ]; then
      NODE_PATH="$NODES_DIR/$CURRENT_NODE"
      RECOVERY_NOTE="via CURRENT pointer"
    fi
  fi

  # Path B: Fallback scan (CURRENT missing or corrupt)
  if [ -z "$NODE_PATH" ]; then
    local LATEST
    LATEST=$(ls "$NODES_DIR"/node-*.md 2>/dev/null | sort -t'-' -k2 -n | tail -1)
    if [ -n "$LATEST" ] && [ -s "$LATEST" ]; then
      NODE_PATH="$LATEST"
      RECOVERY_NOTE="via fallback scan (CURRENT missing)"
    fi
  fi

  # Path C: No nodes exist
  [ -z "$NODE_PATH" ] && return 1

  echo "## Checkpoint Node（Auto-Recovery, $RECOVERY_NOTE）"
  echo ""
  cat "$NODE_PATH"
  echo ""
  echo "---"
  echo "**Resume from the Next Input section above. Read Gate for exact next action.**"
  NODE_RECOVERY_SUCCESS=1
  return 0
}

# ══════════════════════════════════════
# 2.5 Helper: output one SDD Context
# ══════════════════════════════════════
output_sdd_context() {
  local SOURCE="$1"
  local CTX_PATH="$2"

  # Validate JSON
  if ! jq empty "$CTX_PATH" 2>/dev/null; then
    echo "⚠️ JSON 格式損壞，無法解析: $CTX_PATH"
    echo "請手動讀取檔案確認狀態: \`Read $CTX_PATH\`"
    return
  fi

  local FEATURE=$(jq -r '.sdd_context.feature // "unknown"' "$CTX_PATH")
  local STAGE=$(jq -r '.sdd_context.current_stage // "unknown"' "$CTX_PATH")
  local SPEC_MODE=$(jq -r '.sdd_context.spec_mode // "unknown"' "$CTX_PATH")
  local SPEC_FOLDER=$(jq -r '.sdd_context.spec_folder // ""' "$CTX_PATH")
  local LAST_UPDATED=$(jq -r '.sdd_context.last_updated // ""' "$CTX_PATH")

  # === Node-based recovery (priority) ===
  if [ -n "$SPEC_FOLDER" ]; then
    if try_node_recovery "$SPEC_FOLDER"; then
      # Node recovery succeeded — output compact sdd_context summary only
      echo ""
      echo "## SDD Context Summary (supplementary)"
      echo "- Feature: $FEATURE"
      echo "- Stage: $STAGE"
      echo "- Spec Mode: $SPEC_MODE"
      echo "- Context Path: \`$CTX_PATH\`"
      [ -n "$SPEC_FOLDER" ] && echo "- Spec Folder: $SPEC_FOLDER"
      echo ""
      # Skip full JSON dump — node has the essential resume info
      # Continue to stage hints and mandatory rules
      return
    fi
  fi

  # === Existing full sdd_context recovery (fallback) ===
  local FILE_SIZE=$(wc -c < "$CTX_PATH" 2>/dev/null | tr -d ' ')

  echo "## 當前 SOP 狀態"
  echo "- Feature: $FEATURE"
  echo "- Stage: $STAGE"
  echo "- Spec Mode: $SPEC_MODE"
  echo "- Source: $SOURCE ($CTX_PATH)"
  echo "- Last Updated: $LAST_UPDATED"
  [ -n "$SPEC_FOLDER" ] && echo "- Spec Folder: $SPEC_FOLDER"
  echo ""

  # Stage status summary
  echo "## Stage 進度"
  jq -r '
    .sdd_context.stages | to_entries[] |
    select(.value.status != null and .value.status != "pending") |
    "- \(.key | ascii_upcase): \(.value.status) (\(if .value.agent then .value.agent elif .value.agents then (.value.agents | join(", ")) else "—" end))"
  ' "$CTX_PATH" 2>/dev/null
  echo ""

  # Full JSON or key-fields-only based on size
  if [ "$FILE_SIZE" -gt "$MAX_JSON_SIZE" ] 2>/dev/null; then
    echo "## SDD Context 關鍵欄位（完整檔案 >50KB，已精簡）"
    jq '{
      sdd_context: {
        version: .sdd_context.version,
        feature: .sdd_context.feature,
        current_stage: .sdd_context.current_stage,
        spec_mode: .sdd_context.spec_mode,
        spec_folder: .sdd_context.spec_folder,
        status: .sdd_context.status,
        current_stage_output: .sdd_context.stages[
          .sdd_context.current_stage | split(" ")[0] | ascii_downcase
        ].output
      }
    }' "$CTX_PATH" 2>/dev/null
    echo ""
    echo "完整檔案路徑: \`$CTX_PATH\`（如需完整內容請用 Read tool 讀取）"
  else
    echo "## SDD Context 完整內容"
    jq '.' "$CTX_PATH" 2>/dev/null
  fi
  echo ""

  # ── Stale Detection ──
  local STALE_WARNINGS=""
  for stage_key in s0 s1 s2 s3 s4 s5 s6 s7; do
    local STAGE_UPPER=$(echo "$stage_key" | tr 'a-z' 'A-Z')
    local STAGE_STATUS=$(jq -r ".sdd_context.stages.${stage_key}.status // \"pending\"" "$CTX_PATH" 2>/dev/null)

    # If current_stage points to this stage but status is still "pending"
    if [ "$STAGE" = "$STAGE_UPPER" ] && [ "$STAGE_STATUS" = "pending" ]; then
      STALE_WARNINGS="${STALE_WARNINGS}\n⚠️ STALE: current_stage=$STAGE 但 stages.${stage_key}.status=pending（Agent 可能未完成持久化）"
    fi
  done

  if [ -n "$STALE_WARNINGS" ]; then
    echo "## ⚠️ Stale Detection 警告"
    echo -e "$STALE_WARNINGS"
    echo ""
    echo "建議：讀取 sdd_context.json 確認實際狀態，必要時手動修正。"
    echo ""
  fi

  # List spec folder .md files
  if [ -n "$SPEC_FOLDER" ] && [ -d "$PROJECT_DIR/$SPEC_FOLDER" ]; then
    local MD_FILES=$(ls "$PROJECT_DIR/$SPEC_FOLDER"/*.md 2>/dev/null)
    if [ -n "$MD_FILES" ]; then
      echo "## 相關 Spec 檔案"
      for md in $MD_FILES; do
        echo "- $(basename "$md") → \`$SPEC_FOLDER/$(basename "$md")\`"
      done
      echo ""
    fi
  fi

  # Stage-specific recovery hints
  echo "## 強制恢復指令"
  echo "1. 你正在 **$STAGE** 階段，必須從這個階段繼續"
  echo "2. 執行前先讀取上方 SDD Context 的 output 欄位了解前序階段成果"

  case "$STAGE" in
    S4)
      echo "3. 檢查 stages.s4.output.completed_tasks 確認已完成哪些任務"
      echo "4. 對照 stages.s3.output.waves 確認剩餘任務"
      ;;
    S5)
      echo "3. 讀取 stages.s4.output.changes 了解實作內容"
      echo "4. 執行 Scoped Code Review（/code-review s5）"
      ;;
    S6)
      echo "3. 讀取 stages.s5.output 了解 review 結論"
      echo "4. 檢查 repair_loop_count 確認是否還有修復配額"
      ;;
    S1)
      PHASES=$(jq -r '.sdd_context.stages.s1.output.completed_phases // [] | length' "$CTX_PATH" 2>/dev/null)
      if [ "$PHASES" = "1" ]; then
        echo "3. S1 Phase 1 已完成，需從 Phase 2（architect）繼續"
      else
        echo "3. S1 從 Phase 1（codebase-explorer）開始"
      fi
      ;;
    S0|S2|S3)
      echo "3. 呼叫對應的 Skill 繼續此階段"
      ;;
  esac

  echo "5. 遵守 CLAUDE.md 所有規則"
  echo "6. 若需要更多 spec 細節，讀取上方列出的 .md 檔案路徑"
}

# ══════════════════════════════════════
# 3. Git branch
# ══════════════════════════════════════
GIT_BRANCH=$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

# ══════════════════════════════════════
# 4. Main output
# ══════════════════════════════════════
echo "[SOP Context Recovery — Auto-injected]"
echo ""
echo "⚠️ MANDATORY: 對話已壓縮。以下是從 SDD Context 自動恢復的狀態，你必須基於此狀態繼續工作。"
echo ""
echo "Branch: $GIT_BRANCH"
echo ""

ACTIVE_COUNT=${#ACTIVE_CONTEXTS[@]}

if [ "$ACTIVE_COUNT" -eq 0 ]; then
  # ── No active SOP ──
  echo "[Context Compacted — No Active SOP]"
  echo "目前沒有進行中的 SOP 管線。"
  if [ -n "$COMPLETED_SUMMARY" ]; then
    echo ""
    echo "## 已完成的 Features（本 session）"
    echo -e "$COMPLETED_SUMMARY"
  fi
  echo ""
  echo "Recovery:"
  echo "1. Check TaskList for any in-progress tasks"
  echo "2. 新功能需求請啟動 S0（Skill: s0-understand）"
  echo "3. 遵守 CLAUDE.md 規則"

elif [ "$ACTIVE_COUNT" -eq 1 ]; then
  # ── Single active SOP ──
  IFS='|' read -r SOURCE CTX_PATH <<< "${ACTIVE_CONTEXTS[0]}"
  output_sdd_context "$SOURCE" "$CTX_PATH"

else
  # ── Multiple active SOPs ──
  echo "⚠️ 發現 $ACTIVE_COUNT 個進行中的 SOP，請用戶指定要恢復哪個："
  echo ""
  for i in "${!ACTIVE_CONTEXTS[@]}"; do
    IFS='|' read -r SOURCE CTX_PATH <<< "${ACTIVE_CONTEXTS[$i]}"
    FEATURE=$(jq -r '.sdd_context.feature // "unknown"' "$CTX_PATH" 2>/dev/null)
    STAGE=$(jq -r '.sdd_context.current_stage // "unknown"' "$CTX_PATH" 2>/dev/null)
    echo "$((i+1)). [$SOURCE] $FEATURE — Stage: $STAGE ($CTX_PATH)"
  done
  echo ""
  echo "請詢問用戶：「偵測到多個進行中的 SOP，你要繼續哪一個？」"
  echo ""
  # Still output the first one as default context
  echo "--- 以下預設顯示第一個 SOP 的完整狀態 ---"
  echo ""
  IFS='|' read -r SOURCE CTX_PATH <<< "${ACTIVE_CONTEXTS[0]}"
  output_sdd_context "$SOURCE" "$CTX_PATH"
fi

# ══════════════════════════════════════
# 5. Around the World (ATW) session detection
# ══════════════════════════════════════
# Guard: skip ATW injection if node recovery already included ATW context (prevents double-injection)
ATW_FILE="$PROJECT_DIR/dev/atw-session.json"
if [ "$NODE_RECOVERY_SUCCESS" -eq 0 ] && [ -f "$ATW_FILE" ]; then
  ATW_STATUS=$(jq -r '.status // empty' "$ATW_FILE" 2>/dev/null)
  if [ "$ATW_STATUS" = "in_progress" ]; then
    ATW_ID=$(jq -r '.session_id // "unknown"' "$ATW_FILE" 2>/dev/null)
    ATW_COMPLETED=$(jq -r '.stats.completed // 0' "$ATW_FILE" 2>/dev/null)
    ATW_TOTAL=$(jq -r '.stats.total // 0' "$ATW_FILE" 2>/dev/null)
    ATW_CURRENT_ID=$(jq -r '.current_feature_id // 0' "$ATW_FILE" 2>/dev/null)
    ATW_NEXT_DESC=$(jq -r --argjson id "$ATW_CURRENT_ID" '.features[] | select(.id == $id and .status == "queued") | .description' "$ATW_FILE" 2>/dev/null)

    echo ""
    echo "## 🌍 Around the World Session 活躍"
    echo "- Session: $ATW_ID"
    echo "- 進度: $ATW_COMPLETED / $ATW_TOTAL features 完成"

    if [ -n "$ATW_NEXT_DESC" ]; then
      echo "- 下一個 Feature (#$ATW_CURRENT_ID): $ATW_NEXT_DESC"
      echo ""
      echo "**指令：啟動下一個 feature 的 S0：**"
      echo "\`Skill(skill: \"s0-understand\", args: \"$ATW_NEXT_DESC\")\`"
    else
      # Current feature might be in_progress (not queued)
      ATW_IP_DESC=$(jq -r --argjson id "$ATW_CURRENT_ID" '.features[] | select(.id == $id and .status == "in_progress") | .description' "$ATW_FILE" 2>/dev/null)
      if [ -n "$ATW_IP_DESC" ]; then
        echo "- 當前 Feature (#$ATW_CURRENT_ID): $ATW_IP_DESC（進行中）"
        echo "- 請從上方 SOP 狀態繼續此 feature"
      fi
    fi
  fi
fi

# ── Mandatory rules (always) ──
echo ""
echo "## 強制規則"
echo "- Skill→Agent dispatch: detect SOP need → invoke Skill → Skill dispatches Agent"
echo "- CLAUDE.md rules: no Dio(), use design system, WLScaffold for pages"
echo "- DB safety: never delete without 3x confirmation + backup"
echo "- Gate rules: S0→S1 必停(確認需求), S3→S4 必停(確認計畫)"
echo "- Loop safety: S4↔S5 max 3x, S4↔S6 max 3x"
echo "- 使用繁體中文回應"

exit 0
