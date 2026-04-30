# Smoke Ablation Summary

Day-3 A — full 4-arm × 10-case sweep on the C5/Repair smoke set.

- Total wall spend: **$0.2912**

## Per-arm metrics

| Arm | n | Recall@1 | pass | revert_ac | err_compile | err_runtime | abstain | skipped | crash | cascade>1 | CVR | USD |
|-----|---|----------|------|-----------|-------------|-------------|---------|---------|-------|----------|-----|-----|
| agent-full | 10 | 2/10 | 6 | 0 | 0 | 3 | 1 | 0 | 0 | 4 | 0.67 | $0.2911 |

## `agent-full` per-case detail

| case_id | gt fn | predicted | verdict | depth | refl | USD | finding_reason |
|---------|-------|-----------|---------|-------|------|-----|----------------|
| ACF-092 | `swapAndLiquifyStepv1` | `swapTokensForOther` | pass | 1 | 0 | $0.0115 | PoC succeeded at cascade depth 1 (target='swapTokensForOther') |
| ACF-102 | `WhiteListMint` | `setApprovalForAll` | fail_error_runtime | 3 | 2 | $0.0357 | All top-3 candidates intercepted by access control — contract appears safe for t |
| ACF-091 | `_withdraw` | `addStrategy` | fail_error_runtime | 3 | 2 | $0.0478 | All top-3 candidates intercepted by access control — contract appears safe for t |
| ACF-106 | `pledgeAndBorrow` | `initialize` | abstain | 1 | 0 | $0.0218 | Cascade abstained at depth 1: PoC retries exhausted (last error: Error: Compiler |
| ACF-093 | `depositFromOtherContract` | `updatePool` | fail_error_runtime | 3 | 2 | $0.0474 | All top-3 candidates intercepted by access control — contract appears safe for t |
| ACF-114 | `OnlyOwner` | `ForceBet` | pass | 3 | 2 | $0.0693 | PoC succeeded at cascade depth 3 (target='ForceBet') |
| ACF-103 | `_transfer` | `transfer` | pass | 1 | 0 | $0.0143 | PoC succeeded at cascade depth 1 (target='transfer') |
| ACF-087 | `mint` | `mint` | pass | 1 | 0 | $0.0125 | PoC succeeded at cascade depth 1 (target='mint') |
| ACF-109 | `deposit` | `initialize` | pass | 1 | 0 | $0.0137 | PoC succeeded at cascade depth 1 (target='initialize') |
| ACF-101 | `swap` | `mint` | pass | 1 | 0 | $0.0171 | PoC succeeded at cascade depth 1 (target='mint') |
