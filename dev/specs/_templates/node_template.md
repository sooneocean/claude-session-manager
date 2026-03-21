# Node Template — Checkpoint Node Engine

> This template defines the standard format for checkpoint nodes.
> Each SOP stage writes one node at completion. Nodes are the AI-resumable context layer.

## Format

```markdown
---
node_id: "node-{NNN}-{stage}-{label}"
stage: "{s0|s1|s2|s3|s4|s5|s6|s7}"
stage_status: "{completed|fix_required|skipped|interrupted}"
gate_result: "{passed|auto_continue|fail|interrupted|done|skipped|conditional|disputed}"
created_at: "ISO8601"
spec_folder: "{relative path to spec folder}"
prev_node: "{previous node_id or null}"
feature: "{feature name}"
sdd_stage: "{S0|S1|S2|S3|S4|S5|S6|S7}"
---

## Conclusion
{What this stage accomplished. 1-3 sentences. Past tense. No reasoning process.}

## Artifacts
{Files produced by this stage. Paths relative to repo root.}
- `{path/to/file}`

## Next Input
{Everything the next stage needs to start. MUST be <2KB.
If content exceeds 2KB: write summary + "see {filepath} section {heading}".}

## Gate
- **Result**: {gate_result}
- **Next Stage**: {S1|S2|S3|S4|S5|S6|S7|DONE}
- **Next Action**: {Specific instruction for Orchestrator/Agent}
```

## Size Constraints

| Section | Target | Hard Limit |
|---------|--------|-----------|
| Frontmatter | ~200 bytes | 300 bytes |
| Conclusion | ~200 bytes | 500 bytes |
| Artifacts | ~100 bytes | 300 bytes |
| Next Input | ~500 bytes | 2048 bytes (2KB) |
| Gate | ~100 bytes | 200 bytes |
| **Total** | **~1.1 KB** | **~3.5 KB** |

## Sequence Number Generation

1. `ls {spec_folder}/nodes/node-*.md 2>/dev/null | sort -t'-' -k2 -n | tail -1`
2. Extract NNN from `node-(\d{3})-` pattern
3. New NNN = max + 1 (or 000 if no nodes exist)
4. Zero-pad to 3 digits

## Write Order (MUST follow exactly)

1. `mkdir -p {spec_folder}/nodes/`
2. Generate sequence number
3. Write node file: `{spec_folder}/nodes/node-{NNN}-{stage}-{label}.md`
4. Update CURRENT: `echo "node-{NNN}-{stage}-{label}.md" > {spec_folder}/nodes/CURRENT`
5. Update sdd_context.json (existing persistence, unchanged)

## Per-Stage Strategy Quick Reference

| Stage | label | Conclusion | Next Input Focus | gate_result |
|-------|-------|-----------|-----------------|-------------|
| S0 | consensus | Requirement consensus + work_type + spec_mode | scope_in, constraints, pain_points | passed |
| S1 | devspec | Tech approach + task count | Task list summary + key decisions + risks | auto_continue |
| S2 | review / skip | Review verdict + finding counts | Pass: proceed / Fail: critical issues | passed/fail/skipped |
| S3 | plan | Wave count + task count + complexity | Wave-by-wave task summary | auto_continue |
| S4 | impl | Tasks completed + files changed + build status | Changed files list for review | completed |
| S5-pass | review-pass | Review passed + score | Test scope + acceptance criteria ref | passed |
| S5-p1 | review-p1 | Fix required + P1 count + loop N/3 | blocking_fixes list | fix_required |
| S5-p0 | review-p0 | Redesign required + P0 count | P0 issue descriptions | redesign_required |
| S6-pass | test-pass | All tests passed + defect count | Changes summary for commit | passed |
| S6-fail | test-fail | Tests failed + defect count + loop N/3 | Defect list (TC + error) | fail |
| S7 | commit | Committed hash + file count | ATW: Feature Summary. Non-ATW: "SOP complete." | done |

## Writing Checklist

Before writing a node, verify:
- [ ] Conclusion is past tense, 1-3 sentences, no reasoning
- [ ] Artifacts lists actual file paths
- [ ] Next Input is <2KB (check: if it feels long, measure it)
- [ ] Next Input contains ONLY what next stage needs (no history)
- [ ] Gate result matches the per-stage strategy table
- [ ] Sequence number is correct (no gaps, no duplicates)
- [ ] CURRENT pointer updated AFTER node file written
