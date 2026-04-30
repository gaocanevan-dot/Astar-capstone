# Single-Agent Analyst Summary

- eval_set: `data\dataset\eval_set.json`
- total cases: 42
- evaluable cases (have ground truth): 41
- skipped (empty source): 2
- errored: 0

## Analyst Recall (function-level)

| Metric | Value |
|--------|-------|
| Strict Recall (exact name, top-1) | 46.34% (19/41) |
| Loose Recall (substring, top-1) | 46.34% (19/41) |
| hit@1 (any of top-1 matches GT) | 46.34% (19/41) |
| hit@2 (any of top-2 matches GT) | 58.54% (24/41) |
| hit@3 (any of top-3 matches GT) | 60.98% (25/41) |

## Compute

| Metric | Value |
|--------|-------|
| Total LLM calls | 40 |
| Total prompt tokens | 33968 |
| Total completion tokens | 35274 |
| Wall-clock total (s) | 473.8 |
| System fingerprints | fp_83e2dd34fc, gpt-5-mini-2025-08-07 |

## Per-case outcomes

| case_id | GT function | Predicted (top-1) | Top-3 candidates | hit@1 | hit@3 |
|---------|-------------|-------------------|------------------|-------|-------|
| NOYA-H-04 | `executeWithdraw` | `` | — | ✗ | ✗ |
| NOYA-H-08 | `sendTokensToTrustedAddress` | `updateSwapHandler` | `updateSwapHandler`, `updateValueOracle`, `sendTokensToTrustedAddress` | ✗ | ✓ |
| NOYA-M-03 | `executeManagerAction` | `` | — | ✗ | ✗ |
| CSW-H-01 | `removeOwnerAtIndex` | `initialize` | `initialize`, `executeWithoutChainIdValidation`, `canSkipChainIdValidation` | ✗ | ✗ |
| GRA-H-02 | `upgradeTo` | `addMinter` | `addMinter`, `mint`, `_initialize` | ✗ | ✗ |
| GIT-M-02 | `setStakeParameters` | `initialize` | `initialize`, `lockAndBurn`, `release` | ✗ | ✗ |
| C4-161 | `removeFeeder` | `removeFeeder` | `removeFeeder` | ✓ | ✓ |
| C4-35 | `removeFeeder` | `` | — | ✗ | ✗ |
| C4-222 | `mint` | `mint` | `mint` | ✓ | ✓ |
| C4-6 | `increaseDebt` | `increaseDebt` | `increaseDebt` | ✓ | ✓ |
| C4-21 | `setUp` | `distributeInitialSupply` | `distributeInitialSupply`, `setUp`, `testExploit` | ✗ | ✓ |
| C4-55 | `removeFeeder` | `` | — | ✗ | ✗ |
| C4-29 | `burn` | `burn` | `burn` | ✓ | ✓ |
| C4-17 | `testExploit` | `calculateAndDistributeRewards` | `calculateAndDistributeRewards` | ✗ | ✗ |
| C4-438 | `buy` | `initialize` | `initialize`, `buy`, `refund` | ✗ | ✓ |
| C4-111 | `unknown_function` | `` | — | ✗ | ✗ |
| C4-80 | `auctionStartTime` | `` | — | ✗ | ✗ |
| C4-19 | `isIncluded` | `isIncluded` | `isIncluded` | ✓ | ✓ |
| C4-487 | `onDeposit` | `pay` | `pay`, `onDeposit` | ✗ | ✓ |
| C4-186 | `removeFeeder` | `removeFeeder` | `removeFeeder`, `_removeFeeder` | ✓ | ✓ |
| C4-22 | `isIncluded` | `isIncluded` | `isIncluded`, `transferFrom`, `CallRedeemhook` | ✓ | ✓ |
| C4-328 | `unknown_function` | `` | — | ✗ | ✗ |
| C4-169 | `setUnderlyingPrice` | `setDirectPrice` | `setDirectPrice`, `setUnderlyingPrice` | ✗ | ✓ |
| C4-51 | `AddProposal` | `AddProposal` | `AddProposal` | ✓ | ✓ |
| C4-318 | `fillOrder` | `fillOrder` | `fillOrder` | ✓ | ✓ |
| C4-165 | `updateBaseRate` | `updateBaseRate` | `updateBaseRate` | ✓ | ✓ |
| C4-172 | `queue` | `queue` | `queue` | ✓ | ✓ |
| C4-63 | `AddProposal` | `AddProposal` | `AddProposal` | ✓ | ✓ |
| C4-174 | `approve` | `approve` | `approve` | ✓ | ✓ |
| C4-67 | `incrementWindow` | `incrementWindow` | `incrementWindow` | ✓ | ✓ |
| C4-3 | `wrap` | `wrap` | `wrap`, `unwrap` | ✓ | ✓ |
| C4-248 | `testExploit` | `withdraw` | `withdraw` | ✗ | ✗ |
| C4-54 | `unwrapWETH9` | `sweepToken` | `sweepToken`, `unwrapWETH9`, `refundETH` | ✗ | ✓ |
| C4-286 | `unknown_function` | `` | — | ✗ | ✗ |
| C4-572 | `setUp` | `incrementNonce` | `incrementNonce`, `initialize` | ✗ | ✗ |
| C4-229 | `burnFeiHeld` | `burnFeiHeld` | `burnFeiHeld` | ✓ | ✓ |
| C4-226 | `testMisleadingGetAddress` | `` | — | ✗ | ✗ |
| C4-484 | `activateProposal` | `activateProposal` | `activateProposal` | ✓ | ✓ |
| C4-126 | `install` | `install` | `install` | ✓ | ✓ |
| C4-190 | `receiveCollateral` | `receiveCollateral` | `receiveCollateral` | ✓ | ✓ |
| C4-264 | `unknown_function` | `wrap` | `wrap` | ✗ | ✗ |

## Skipped (empty source)

- NOYA-H-04 (VaultWithdrawManager): empty contract_source
- NOYA-M-03 (VaultManager): empty contract_source