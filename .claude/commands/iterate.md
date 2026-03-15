---
description: "產品迭代引擎 — 掃描現狀→提案功能→autopilot 實作→GitHub Release。觸發：「iterate」、「迭代」、「下一版」"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, Skill, AskUserQuestion, mcp__sequential-thinking__sequentialthinking
argument-hint: "<propose | release | status | 空=完整迭代>"
---

# /iterate — 產品自動迭代引擎

> 掃描產品現狀 → 提出下一版功能 → /autopilot 實作 → git tag + GitHub Release

## 環境資訊
- 當前分支: !`git branch --show-current 2>/dev/null || echo "(未初始化)"`
- 最新 tag: !`git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0"`
- Commits since last tag: !`git rev-list $(git describe --tags --abbrev=0 2>/dev/null || echo "HEAD")..HEAD --count 2>/dev/null || echo "N/A"`

## 輸入
指令：$ARGUMENTS

---

## 參數解析

| 參數 | 行為 |
|------|------|
| 空（無參數） | 完整迭代：掃描→提案→確認→autopilot→release |
| `propose` | 只掃描+提案，不實作不 release |
| `release` | 只做 release（git tag + gh release + CHANGELOG），跳過掃描+實作 |
| `status` | 查看迭代歷史 |

---

## 完整迭代流程

### Step 1: 掃描產品現狀

從以下來源自動收集優化候選：

#### 1.1 Tech Debt 掃描
```bash
# 掃描所有 sdd_context.json 的 tech_debt 欄位
for f in dev/specs/*/sdd_context.json; do
  echo "=== $(basename $(dirname $f)) ==="
  python -c "import json; d=json.load(open('$f')); [print(f'  - {t}') for s in d.get('stages',{}).values() for t in s.get('output',{}).get('tech_debt',[])]"
done
```

#### 1.2 Review Findings 殘留
```bash
# 掃描 S5 review 中被記錄但未修正的 P2
grep -r "P2" dev/specs/*/review/ --include="*.md" -l
```

#### 1.3 程式碼品質
```bash
# 靜態分析（若可用）
python -m mypy src/ --ignore-missing-imports 2>&1 | tail -5
# 測試覆蓋
python -m pytest tests/ -q 2>&1 | tail -3
```

#### 1.4 Spec vs Code 差異
```bash
# 檢查 spec 是否與實作一致
# 比對 dev_spec 描述的架構 vs 實際程式碼結構
```

### Step 2: 排序候選（ROI 評分）

使用 sequential-thinking 分析每個候選：

| 評分維度 | 權重 | 說明 |
|---------|------|------|
| 用戶影響 | 40% | 對使用體驗的改善程度 |
| 技術信心 | 30% | 實作的確定性和風險 |
| 實作成本 | 30% | 預估改動量（S/M/L） |

**ROI = (影響 × 信心) ÷ 成本**

### Step 3: 提案（Gate — 必停）

呈現 Top 3-5 候選，使用 AskUserQuestion 讓用戶選擇：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  /iterate — 下一版功能提案

  當前版本: {latest_tag}
  掃描來源: tech_debt({n}) + review P2({n}) + 品質({n})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

候選功能（依 ROI 排序）：

1. [ROI: 8.5] {功能名稱}
   來源: {tech_debt | review P2 | 品質掃描}
   影響: {描述}
   規模: {S/M/L}

2. [ROI: 7.2] {功能名稱}
   ...

3. [ROI: 6.0] {功能名稱}
   ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

AskUserQuestion: 選擇要做的功能（可多選），或提出自己的需求。

### Step 4: 實作（觸發 /autopilot）

將用戶選擇的功能描述傳給 /autopilot：

```
Skill(skill: "autopilot", args: "{用戶選擇的功能描述}")
```

等待 autopilot 完成 S0→S7。

### Step 5: Release

#### 5.1 決定版本號

基於本輪改動的 work_type 自動推算：

| work_type | 版本變更 | 範例 |
|-----------|---------|------|
| bugfix | patch +1 | v0.1.0 → v0.1.1 |
| refactor | patch +1 | v0.1.0 → v0.1.1 |
| new_feature | minor +1 | v0.1.0 → v0.2.0 |
| breaking change | major +1 | v0.1.0 → v1.0.0 |

用 AskUserQuestion 確認版本號（可覆寫）。

#### 5.2 生成 CHANGELOG

從上個 tag 到 HEAD 的 commit 自動生成：

```bash
# 取得上個 tag 到 HEAD 的 commits
git log $(git describe --tags --abbrev=0 2>/dev/null || echo "")..HEAD --pretty=format:"- %s" --no-merges
```

分類整理為：
```markdown
## [v{X.Y.Z}] - {YYYY-MM-DD}

### Added
- {feat: commits}

### Changed
- {refactor: commits}

### Fixed
- {fix: commits}
```

追加到 `CHANGELOG.md` 頂部（保留歷史）。

#### 5.3 Git Tag + GitHub Release

```bash
# Commit CHANGELOG
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for v{X.Y.Z}"

# Tag
git tag -a v{X.Y.Z} -m "Release v{X.Y.Z}"

# GitHub Release（若 gh 可用）
gh release create v{X.Y.Z} --title "v{X.Y.Z}" --notes-file <(changelog_section)
```

> 若 `gh` 不可用，只做本地 tag，提示用戶手動 push。

### Step 6: 記錄迭代歷史

更新 `dev/iterate-history.json`：

```json
{
  "iterations": [
    {
      "version": "v{X.Y.Z}",
      "date": "{YYYY-MM-DD}",
      "features": ["{功能描述}"],
      "work_type": "{type}",
      "commits": ["{sha}"],
      "sop_folder": "dev/specs/{folder}"
    }
  ]
}
```

---

## Release-Only 模式

```bash
/iterate release
```

跳過 Step 1-4，直接執行 Step 5-6。
適用於手動實作後想補做 release 的場景。

---

## Propose-Only 模式

```bash
/iterate propose
```

只執行 Step 1-3（掃描+提案），不實作不 release。
適用於「看看有什麼可以做」的探索場景。

---

## Status 模式

```bash
/iterate status
```

讀取 `dev/iterate-history.json` 和 git tags，顯示：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  迭代歷史

  v0.3.0 | 2026-03-15 | feat: real-time streaming
  v0.2.0 | 2026-03-15 | feat: session persistence
  v0.1.0 | 2026-03-15 | feat: initial CSM tool
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 安全規則

1. **Gate 必停**：Step 3（提案確認）和 Step 5.1（版本號確認）必須用戶確認
2. **不自動 push**：git push 需要用戶明確要求
3. **CHANGELOG 追加不覆蓋**：新版本記錄加在頂部，不動歷史
4. **每輪最多 3 個功能**：避免單次迭代過大
