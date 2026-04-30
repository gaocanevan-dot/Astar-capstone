# Baseline Summary — gpt_zeroshot

- cases: 10
- evaluable (GT present): 10
- flagged (contract-level positive): 8
- elapsed: 246.9s
- total LLM calls: 10
- total tokens: 58587

## Function-level Recall

| Metric | Value |
|--------|-------|
| Strict | 2/10 = 20.0% |
| Loose  | 2/10 = 20.0% |

## Per-case

| case_id | GT | flagged | primary pred | strict | loose | err |
|---------|----|---------|--------------|--------|-------|-----|
| ACF-092 | `swapAndLiquifyStepv1` | True | `transferFromm` | ✗ | ✗ |  |
| ACF-102 | `WhiteListMint` | False | `` | ✗ | ✗ |  |
| ACF-091 | `_withdraw` | True | `report` | ✗ | ✗ |  |
| ACF-106 | `pledgeAndBorrow` | True | `notifyRepayBorrow` | ✗ | ✗ |  |
| ACF-093 | `depositFromOtherContract` | True | `depositFromOtherContract` | ✓ | ✓ |  |
| ACF-114 | `OnlyOwner` | True | `OwnerWithdraw` | ✗ | ✗ |  |
| ACF-103 | `_transfer` | False | `` | ✗ | ✗ |  |
| ACF-087 | `mint` | True | `mint` | ✓ | ✓ |  |
| ACF-109 | `deposit` | True | `cancelProposal` | ✗ | ✗ |  |
| ACF-101 | `swap` | True | `mint` | ✗ | ✗ |  |