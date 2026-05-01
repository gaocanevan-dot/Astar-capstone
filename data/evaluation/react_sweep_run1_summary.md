# Day-5 ReAct Agent Sweep — `react_sweep_run1`

- Cases run: **10 / 5** 
- Total spend: **$0.1485**

## Acceptance criteria (Q3 mandate)

- **AC1** Self-termination: `10/10` → ✅ PASS (≥7/10 required)
- **AC2** Avg distinct tools/case: `5.8` → ✅ PASS (≥3 required)
- **AC5b** Cases with non-empty self-lesson recall: `0/10` → ❌ FAIL (≥2 required)
- **AC7** Within budget ≤$2.50: `$0.1485` → ✅ PASS
- **AC8** Per-case markdown trace: see `data\evaluation\react_traces/`

_AC6 (pass≥4) DROPPED per Critic; informational pass count = **4/10**, Recall@1 = **0/10**._

## Per-case detail

| case | gt | predicted | terminal | iters | tools | verdict | recall | $ |
|------|----|-----------|----------|-------|-------|---------|--------|---|
| ACF-092 | `swapAndLiquifyStepv1` | `transferFromm` | submit_finding | 7 | 6 | pass | ✗ | $0.0154 |
| ACF-102 | `WhiteListMint` | `approve` | give_up | 7 | 6 | fail_error_runtime | ✗ | $0.0144 |
| ACF-091 | `_withdraw` | `addStrategy` | give_up | 7 | 6 | fail_error_runtime | ✗ | $0.0164 |
| ACF-106 | `pledgeAndBorrow` | `notifyOrderLiquidated` | give_up | 7 | 6 | fail_error_compile | ✗ | $0.0192 |
| ACF-093 | `depositFromOtherContract` | `updatePool` | give_up | 7 | 6 | fail_error_runtime | ✗ | $0.0176 |
| ACF-114 | `OnlyOwner` | `` | give_up | 3 | 3 | - | ✗ | $0.0080 |
| ACF-103 | `_transfer` | `transferFrom` | submit_finding | 6 | 6 | pass | ✗ | $0.0108 |
| ACF-087 | `mint` | `transferFrom` | submit_finding | 6 | 6 | pass | ✗ | $0.0111 |
| ACF-109 | `deposit` | `initialize` | give_up | 8 | 7 | fail_revert_ac | ✗ | $0.0216 |
| ACF-101 | `swap` | `massMintPools` | submit_finding | 6 | 6 | pass | ✗ | $0.0140 |
