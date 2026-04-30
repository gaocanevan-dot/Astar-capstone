# Baseline Summary — gpt_zeroshot

- cases: 42
- evaluable (GT present): 41
- flagged (contract-level positive): 35
- elapsed: 390.4s
- total LLM calls: 40
- total tokens: 50201

## Function-level Recall

| Metric | Value |
|--------|-------|
| Strict | 23/41 = 56.1% |
| Loose  | 23/41 = 56.1% |

## Per-case

| case_id | GT | flagged | primary pred | strict | loose | err |
|---------|----|---------|--------------|--------|-------|-----|
| NOYA-H-04 | `executeWithdraw` | False | `` | ✗ | ✗ | empty contract_source |
| NOYA-H-08 | `sendTokensToTrustedAddress` | True | `sendTokensToTrustedAddress` | ✓ | ✓ |  |
| NOYA-M-03 | `executeManagerAction` | False | `` | ✗ | ✗ | empty contract_source |
| CSW-H-01 | `removeOwnerAtIndex` | True | `executeWithoutChainIdValidation` | ✗ | ✗ |  |
| GRA-H-01 | `` | False | `` | ✗ | ✗ |  |
| GRA-H-02 | `upgradeTo` | False | `` | ✗ | ✗ |  |
| GIT-M-02 | `setStakeParameters` | False | `` | ✗ | ✗ |  |
| C4-161 | `removeFeeder` | True | `removeFeeder` | ✓ | ✓ |  |
| C4-35 | `removeFeeder` | False | `` | ✗ | ✗ |  |
| C4-222 | `mint` | False | `` | ✗ | ✗ |  |
| C4-6 | `increaseDebt` | True | `increaseDebt` | ✓ | ✓ |  |
| C4-21 | `setUp` | True | `startRewardsCycle` | ✗ | ✗ |  |
| C4-55 | `removeFeeder` | True | `removeFeeder` | ✓ | ✓ |  |
| C4-29 | `burn` | True | `burn` | ✓ | ✓ |  |
| C4-17 | `testExploit` | True | `calculateAndDistributeRewards` | ✗ | ✗ |  |
| C4-438 | `buy` | True | `buy` | ✓ | ✓ |  |
| C4-111 | `unknown_function` | True | `harvest` | ✗ | ✗ |  |
| C4-80 | `auctionStartTime` | True | `_setCreatorDiscount` | ✗ | ✗ |  |
| C4-19 | `isIncluded` | True | `isIncluded` | ✓ | ✓ |  |
| C4-487 | `onDeposit` | True | `pay` | ✗ | ✗ |  |
| C4-186 | `removeFeeder` | True | `removeFeeder` | ✓ | ✓ |  |
| C4-22 | `isIncluded` | True | `isIncluded` | ✓ | ✓ |  |
| C4-328 | `unknown_function` | True | `transferERC20` | ✗ | ✗ |  |
| C4-169 | `setUnderlyingPrice` | True | `setUnderlyingPrice` | ✓ | ✓ |  |
| C4-51 | `AddProposal` | True | `AddProposal` | ✓ | ✓ |  |
| C4-318 | `fillOrder` | True | `fillOrder` | ✓ | ✓ |  |
| C4-165 | `updateBaseRate` | True | `updateBaseRate` | ✓ | ✓ |  |
| C4-172 | `queue` | True | `queue` | ✓ | ✓ |  |
| C4-63 | `AddProposal` | True | `AddProposal` | ✓ | ✓ |  |
| C4-174 | `approve` | True | `approve` | ✓ | ✓ |  |
| C4-67 | `incrementWindow` | True | `incrementWindow` | ✓ | ✓ |  |
| C4-3 | `wrap` | True | `wrap` | ✓ | ✓ |  |
| C4-248 | `testExploit` | True | `withdraw` | ✗ | ✗ |  |
| C4-54 | `unwrapWETH9` | True | `unwrapWETH9` | ✓ | ✓ |  |
| C4-286 | `unknown_function` | True | `onRedeem` | ✗ | ✗ |  |
| C4-572 | `setUp` | True | `incrementNonce` | ✗ | ✗ |  |
| C4-229 | `burnFeiHeld` | True | `burnFeiHeld` | ✓ | ✓ |  |
| C4-226 | `testMisleadingGetAddress` | True | `deploy` | ✗ | ✗ |  |
| C4-484 | `activateProposal` | True | `activateProposal` | ✓ | ✓ |  |
| C4-126 | `install` | True | `install` | ✓ | ✓ |  |
| C4-190 | `receiveCollateral` | True | `receiveCollateral` | ✓ | ✓ |  |
| C4-264 | `unknown_function` | True | `wrap` | ✗ | ✗ |  |