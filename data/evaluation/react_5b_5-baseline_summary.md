# Day-5 ReAct Agent Sweep — `react_5b_5-baseline`

- Cases run: **10 / 10** 
- Total spend: **$0.1872**

## Acceptance criteria (Q3 mandate)

- **AC1** Self-termination: `10/10` → ✅ PASS (≥7/10 required)
- **AC2** Avg distinct tools/case: `6.1` → ✅ PASS (≥3 required)
- **AC5b** Cases with non-empty self-lesson recall: `0/10` → ❌ FAIL (≥2 required)
- **AC7** Within budget ≤$2.50: `$0.1872` → ✅ PASS
- **AC8** Per-case markdown trace: see `data\evaluation\react_traces/`

_AC6 (pass≥4) DROPPED per Critic; informational pass count = **6/10**, Recall@1 = **1/10**._

## Per-case detail

| case | gt | predicted | terminal | iters | tools | verdict | recall | $ |
|------|----|-----------|----------|-------|-------|---------|--------|---|
| ACF-092 | `swapAndLiquifyStepv1` | `transferFromm` | submit_finding | 6 | 6 | pass | ✗ | $0.0098 |
| ACF-102 | `WhiteListMint` | `withdraw` | give_up | 6 | 6 | fail_error_runtime | ✗ | $0.0122 |
| ACF-091 | `_withdraw` | `addStrategy` | give_up | 7 | 6 | fail_error_runtime | ✗ | $0.0130 |
| ACF-106 | `pledgeAndBorrow` | `notifyRepayBorrow` | give_up | 10 | 7 | fail_error_compile | ✗ | $0.0401 |
| ACF-093 | `depositFromOtherContract` | `withdraw` | give_up | 7 | 6 | fail_error_runtime | ✗ | $0.0195 |
| ACF-114 | `OnlyOwner` | `BuyContract` | submit_finding | 7 | 6 | pass | ✗ | $0.0253 |
| ACF-103 | `_transfer` | `transferFrom` | submit_finding | 7 | 6 | pass | ✗ | $0.0106 |
| ACF-087 | `mint` | `transferFrom` | submit_finding | 7 | 6 | pass | ✗ | $0.0118 |
| ACF-109 | `deposit` | `deposit` | submit_finding | 10 | 6 | pass | ✓ | $0.0246 |
| ACF-101 | `swap` | `mint` | submit_finding | 7 | 6 | pass | ✗ | $0.0203 |
