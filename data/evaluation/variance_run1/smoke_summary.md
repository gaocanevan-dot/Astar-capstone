# Smoke Ablation Summary

Day-3 A — full 4-arm × 10-case sweep on the C5/Repair smoke set.

- Total wall spend: **$0.1107**

## Per-arm metrics

| Arm | n | Recall@1 | pass | revert_ac | err_compile | err_runtime | abstain | skipped | crash | cascade>1 | CVR | USD |
|-----|---|----------|------|-----------|-------------|-------------|---------|---------|-------|----------|-----|-----|
| agent-full | 6 | 2/6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1.00 | $0.1106 |

## `agent-full` per-case detail

| case_id | gt fn | predicted | verdict | depth | refl | USD | finding_reason |
|---------|-------|-----------|---------|-------|------|-----|----------------|
| ACF-092 | `swapAndLiquifyStepv1` | `swapAndLiquify` | pass | 1 | 0 | $0.0103 | PoC succeeded at cascade depth 1 (target='swapAndLiquify') |
| ACF-114 | `OnlyOwner` | `BuyContract` | pass | 1 | 0 | $0.0288 | PoC succeeded at cascade depth 1 (target='BuyContract') |
| ACF-103 | `_transfer` | `transferFrom` | pass | 2 | 1 | $0.0278 | PoC succeeded at cascade depth 2 (target='transferFrom') |
| ACF-087 | `mint` | `mint` | pass | 1 | 0 | $0.0121 | PoC succeeded at cascade depth 1 (target='mint') |
| ACF-109 | `deposit` | `initialize` | pass | 1 | 0 | $0.0133 | PoC succeeded at cascade depth 1 (target='initialize') |
| ACF-101 | `swap` | `mint` | pass | 1 | 0 | $0.0183 | PoC succeeded at cascade depth 1 (target='mint') |
