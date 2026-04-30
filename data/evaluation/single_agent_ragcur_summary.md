# Single-Agent Analyst Summary

- eval_set: `data\dataset\eval_set.json`
- total cases: 42
- evaluable cases (have ground truth): 41
- skipped (empty source): 2
- errored: 0

## Analyst Recall (function-level)

| Metric | Value |
|--------|-------|
| Strict Recall (exact name, top-1) | 24.39% (10/41) |
| Loose Recall (substring, top-1) | 36.59% (15/41) |
| hit@1 (any of top-1 matches GT) | 24.39% (10/41) |
| hit@2 (any of top-2 matches GT) | 34.15% (14/41) |
| hit@3 (any of top-3 matches GT) | 34.15% (14/41) |

## Compute

| Metric | Value |
|--------|-------|
| Total LLM calls | 40 |
| Total prompt tokens | 43500 |
| Total completion tokens | 32702 |
| Wall-clock total (s) | 456.2 |
| System fingerprints | fp_83e2dd34fc, gpt-5-mini-2025-08-07 |

## Per-case outcomes

| case_id | GT function | Predicted (top-1) | Top-3 candidates | hit@1 | hit@3 |
|---------|-------------|-------------------|------------------|-------|-------|
| NOYA-H-04 | `executeWithdraw` | `` | — | ✗ | ✗ |
| NOYA-H-08 | `sendTokensToTrustedAddress` | `sendTokensToTrustedAddress` | `sendTokensToTrustedAddress`, `transferPositionToAnotherConnector`, `updateSwapHandler` | ✓ | ✓ |
| NOYA-M-03 | `executeManagerAction` | `` | — | ✗ | ✗ |
| CSW-H-01 | `removeOwnerAtIndex` | `executeWithoutChainIdValidation` | `executeWithoutChainIdValidation`, `initialize`, `canSkipChainIdValidation` | ✗ | ✗ |
| GRA-H-02 | `upgradeTo` | `_initialize` | `_initialize`, `permit`, `addMinter` | ✗ | ✗ |
| GIT-M-02 | `setStakeParameters` | `initialize` | `initialize`, `lockAndBurn`, `communityStake` | ✗ | ✗ |
| C4-161 | `removeFeeder` | `removeFeeder` | `removeFeeder` | ✓ | ✓ |
| C4-35 | `removeFeeder` | `` | — | ✗ | ✗ |
| C4-222 | `mint` | `` | — | ✗ | ✗ |
| C4-6 | `increaseDebt` | `increaseDebt` | `increaseDebt` | ✓ | ✓ |
| C4-21 | `setUp` | `startRewardsCycle` | `startRewardsCycle`, `initialize`, `setRewardsAmount` | ✗ | ✗ |
| C4-55 | `removeFeeder` | `` | — | ✗ | ✗ |
| C4-29 | `burn` | `burn(uint256[] memory ids, uint256[] memory amounts, address to)` | `burn(uint256[] memory ids, uint256[] memory amounts, address to)` | ✗ | ✗ |
| C4-17 | `testExploit` | `calculateAndDistributeRewards` | `calculateAndDistributeRewards` | ✗ | ✗ |
| C4-438 | `buy` | `initialize` | `initialize`, `buy`, `refund` | ✗ | ✓ |
| C4-111 | `unknown_function` | `` | — | ✗ | ✗ |
| C4-80 | `auctionStartTime` | `` | — | ✗ | ✗ |
| C4-19 | `isIncluded` | `` | — | ✗ | ✗ |
| C4-487 | `onDeposit` | `` | — | ✗ | ✗ |
| C4-186 | `removeFeeder` | `removeFeeder` | `removeFeeder`, `_removeFeeder` | ✓ | ✓ |
| C4-22 | `isIncluded` | `isIncluded(address)` | `isIncluded(address)`, `transferFrom(address,address,uint256)`, `CallRedeemhook()` | ✗ | ✗ |
| C4-328 | `unknown_function` | `` | — | ✗ | ✗ |
| C4-169 | `setUnderlyingPrice` | `setDirectPrice` | `setDirectPrice`, `setUnderlyingPrice` | ✗ | ✓ |
| C4-51 | `AddProposal` | `AddProposal` | `AddProposal` | ✓ | ✓ |
| C4-318 | `fillOrder` | `` | — | ✗ | ✗ |
| C4-165 | `updateBaseRate` | `updateBaseRate` | `updateBaseRate` | ✓ | ✓ |
| C4-172 | `queue` | `queue` | `queue` | ✓ | ✓ |
| C4-63 | `AddProposal` | `initialize` | `initialize`, `setPendingAdmin`, `acceptAdmin` | ✗ | ✗ |
| C4-174 | `approve` | `approve(address owner, address spender)` | `approve(address owner, address spender)` | ✗ | ✗ |
| C4-67 | `incrementWindow` | `incrementWindow` | `incrementWindow` | ✓ | ✓ |
| C4-3 | `wrap` | `unwrap` | `unwrap`, `wrap` | ✗ | ✓ |
| C4-248 | `testExploit` | `withdraw` | `withdraw` | ✗ | ✗ |
| C4-54 | `unwrapWETH9` | `sweepToken` | `sweepToken`, `unwrapWETH9`, `refundETH` | ✗ | ✓ |
| C4-286 | `unknown_function` | `` | — | ✗ | ✗ |
| C4-572 | `setUp` | `incrementNonce` | `incrementNonce`, `initialize` | ✗ | ✗ |
| C4-229 | `burnFeiHeld` | `burnFeiHeld` | `burnFeiHeld` | ✓ | ✓ |
| C4-226 | `testMisleadingGetAddress` | `deploy` | `deploy`, `initialize`, `setGovernor` | ✗ | ✗ |
| C4-484 | `activateProposal` | `activateProposal(uint256)` | `activateProposal(uint256)` | ✗ | ✗ |
| C4-126 | `install` | `` | — | ✗ | ✗ |
| C4-190 | `receiveCollateral` | `receiveCollateral` | `receiveCollateral` | ✓ | ✓ |
| C4-264 | `unknown_function` | `wrap` | `wrap` | ✗ | ✗ |

## Skipped (empty source)

- NOYA-H-04 (VaultWithdrawManager): empty contract_source
- NOYA-M-03 (VaultManager): empty contract_source