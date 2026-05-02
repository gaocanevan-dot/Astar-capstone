# Day-5b Acceptance Gate Verdict

**Decision: SHIP day-5b-honest-framing.md**

Total cost across 3 arms: **$0.5642** (cap: $0.7) → ✅

Lift criterion: at least one of (5b-tool, 5b-mandate) has `pass ≥ 5` AND `self_term ≥ 7`
  Winning arms: ['5b-tool', '5b-mandate']
  → ✅

## Per-arm scoreboard

| Arm | n | pass | self_term | recall@1 | tools/case | cascade_fired | sys_forced | cost |
|-----|---|------|-----------|----------|------------|---------------|------------|------|
| 5-baseline | 10 | 6 | 10 | 1 | 6.1 | 0 | 0 | $0.1872 |
| 5b-tool | 10 | 6 | 10 | 0 | 6.0 | 0 | 0 | $0.1515 |
| 5b-mandate | 10 | 5 | 10 | 0 | 6.6 | 5 | 0 | $0.2255 |

## Chosen narrative: `.omc/plans/day-5b-honest-framing.md`

**This is the LAST post-hoc round on n=10.** No further architecture changes on this smoke set without a fresh held-out corpus.
