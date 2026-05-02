# Day-5 ReAct Agent Sweep — `react_5b_5b-mandate`

- Cases run: **10 / 10** 
- Total spend: **$0.2255**

## Acceptance criteria (Q3 mandate)

- **AC1** Self-termination: `10/10` → ✅ PASS (≥7/10 required)
- **AC2** Avg distinct tools/case: `6.6` → ✅ PASS (≥3 required)
- **AC5b** Cases with non-empty self-lesson recall: `0/10` → ❌ FAIL (≥2 required)
- **AC7** Within budget ≤$2.50: `$0.2255` → ✅ PASS
- **AC8** Per-case markdown trace: see `data\evaluation\react_traces/`

_AC6 (pass≥4) DROPPED per Critic; informational pass count = **5/10**, Recall@1 = **0/10**._

## Per-case detail

| case | gt | predicted | terminal | iters | tools | verdict | recall | $ |
|------|----|-----------|----------|-------|-------|---------|--------|---|
| ACF-092 | `swapAndLiquifyStepv1` | `swapTokensForOther` | submit_finding | 7 | 6 | pass | ✗ | $0.0142 |
| ACF-102 | `WhiteListMint` | `transferFrom` | give_up | 10 | 7 | fail_error_runtime | ✗ | $0.0291 |
| ACF-091 | `_withdraw` | `deposit` | give_up | 8 | 8 | fail_error_runtime | ✗ | $0.0255 |
| ACF-106 | `pledgeAndBorrow` | `notifyRepayBorrow` | give_up | 8 | 7 | fail_error_compile | ✗ | $0.0280 |
| ACF-093 | `depositFromOtherContract` | `withdraw` | give_up | 10 | 7 | fail_error_runtime | ✗ | $0.0294 |
| ACF-114 | `OnlyOwner` | `PlaceBet` | give_up | 12 | 7 | fail_error_compile | ✗ | $0.0486 |
| ACF-103 | `_transfer` | `transferFrom` | submit_finding | 6 | 6 | pass | ✗ | $0.0127 |
| ACF-087 | `mint` | `transferFrom` | submit_finding | 6 | 6 | pass | ✗ | $0.0102 |
| ACF-109 | `deposit` | `initialize` | submit_finding | 7 | 6 | pass | ✗ | $0.0140 |
| ACF-101 | `swap` | `massMintPools` | submit_finding | 6 | 6 | pass | ✗ | $0.0138 |
