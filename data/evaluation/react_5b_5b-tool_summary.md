# Day-5 ReAct Agent Sweep — `react_5b_5b-tool`

- Cases run: **10 / 10** 
- Total spend: **$0.1515**

## Acceptance criteria (Q3 mandate)

- **AC1** Self-termination: `10/10` → ✅ PASS (≥7/10 required)
- **AC2** Avg distinct tools/case: `6.0` → ✅ PASS (≥3 required)
- **AC5b** Cases with non-empty self-lesson recall: `0/10` → ❌ FAIL (≥2 required)
- **AC7** Within budget ≤$2.50: `$0.1515` → ✅ PASS
- **AC8** Per-case markdown trace: see `data\evaluation\react_traces/`

_AC6 (pass≥4) DROPPED per Critic; informational pass count = **6/10**, Recall@1 = **0/10**._

## Per-case detail

| case | gt | predicted | terminal | iters | tools | verdict | recall | $ |
|------|----|-----------|----------|-------|-------|---------|--------|---|
| ACF-092 | `swapAndLiquifyStepv1` | `transferFromm` | submit_finding | 6 | 6 | pass | ✗ | $0.0095 |
| ACF-102 | `WhiteListMint` | `transferFrom` | give_up | 6 | 6 | fail_error_runtime | ✗ | $0.0149 |
| ACF-091 | `_withdraw` | `addStrategy` | give_up | 6 | 6 | fail_error_runtime | ✗ | $0.0149 |
| ACF-106 | `pledgeAndBorrow` | `initialize` | give_up | 6 | 6 | fail_error_compile | ✗ | $0.0146 |
| ACF-093 | `depositFromOtherContract` | `initialize` | give_up | 6 | 6 | fail_error_runtime | ✗ | $0.0141 |
| ACF-114 | `OnlyOwner` | `BuyContract` | submit_finding | 7 | 6 | pass | ✗ | $0.0191 |
| ACF-103 | `_transfer` | `transferFrom` | submit_finding | 6 | 6 | pass | ✗ | $0.0099 |
| ACF-087 | `mint` | `transferFrom` | submit_finding | 7 | 6 | pass | ✗ | $0.0132 |
| ACF-109 | `deposit` | `initialize` | submit_finding | 6 | 6 | pass | ✗ | $0.0149 |
| ACF-101 | `swap` | `massMintPools` | submit_finding | 8 | 6 | pass | ✗ | $0.0264 |
