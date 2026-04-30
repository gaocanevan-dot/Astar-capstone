# Baseline Summary — slither

- cases: 42
- evaluable (GT present): 41
- flagged (contract-level positive): 0
- elapsed: 61.6s
- total LLM calls: 0
- total tokens: 0

## Function-level Recall

| Metric | Value |
|--------|-------|
| Strict | 0/41 = 0.0% |
| Loose  | 0/41 = 0.0% |

## Per-case

| case_id | GT | flagged | primary pred | strict | loose | err |
|---------|----|---------|--------------|--------|-------|-----|
| NOYA-H-04 | `executeWithdraw` | False | `` | ✗ | ✗ | empty contract_source |
| NOYA-H-08 | `sendTokensToTrustedAddress` | False | `` | ✗ | ✗ | slither rc=1 |
| NOYA-M-03 | `executeManagerAction` | False | `` | ✗ | ✗ | empty contract_source |
| CSW-H-01 | `removeOwnerAtIndex` | False | `` | ✗ | ✗ | slither rc=1 |
| GRA-H-01 | `` | False | `` | ✗ | ✗ | slither rc=1 |
| GRA-H-02 | `upgradeTo` | False | `` | ✗ | ✗ | slither rc=1 |
| GIT-M-02 | `setStakeParameters` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-161 | `removeFeeder` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-35 | `removeFeeder` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-222 | `mint` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-6 | `increaseDebt` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-21 | `setUp` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-55 | `removeFeeder` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-29 | `burn` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-17 | `testExploit` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-438 | `buy` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-111 | `unknown_function` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-80 | `auctionStartTime` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-19 | `isIncluded` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-487 | `onDeposit` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-186 | `removeFeeder` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-22 | `isIncluded` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-328 | `unknown_function` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-169 | `setUnderlyingPrice` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-51 | `AddProposal` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-318 | `fillOrder` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-165 | `updateBaseRate` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-172 | `queue` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-63 | `AddProposal` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-174 | `approve` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-67 | `incrementWindow` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-3 | `wrap` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-248 | `testExploit` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-54 | `unwrapWETH9` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-286 | `unknown_function` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-572 | `setUp` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-229 | `burnFeiHeld` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-226 | `testMisleadingGetAddress` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-484 | `activateProposal` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-126 | `install` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-190 | `receiveCollateral` | False | `` | ✗ | ✗ | slither rc=1 |
| C4-264 | `unknown_function` | False | `` | ✗ | ✗ | slither rc=1 |