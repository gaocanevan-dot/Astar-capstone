# Day-5 ReAct Agent Sweep — `react_5b_smoke_acf114`

- Cases run: **1 / 1** 
- Total spend: **$0.0446**

## Acceptance criteria (Q3 mandate)

- **AC1** Self-termination: `1/1` → ❌ FAIL (≥7/10 required)
- **AC2** Avg distinct tools/case: `7.0` → ✅ PASS (≥3 required)
- **AC5b** Cases with non-empty self-lesson recall: `0/1` → ❌ FAIL (≥2 required)
- **AC7** Within budget ≤$2.50: `$0.0446` → ✅ PASS
- **AC8** Per-case markdown trace: see `data\evaluation\react_traces/`

_AC6 (pass≥4) DROPPED per Critic; informational pass count = **1/1**, Recall@1 = **0/1**._

## Per-case detail

| case | gt | predicted | terminal | iters | tools | verdict | recall | $ |
|------|----|-----------|----------|-------|-------|---------|--------|---|
| ACF-114 | `OnlyOwner` | `HouseWithdraw` | submit_finding | 10 | 7 | pass | ✗ | $0.0446 |
