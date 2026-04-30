# Single-Agent Analyst Summary

- eval_set: `data\dataset\eval_set.json`
- total cases: 42
- evaluable cases (have ground truth): 41
- skipped (empty source): 2
- errored: 0

## Analyst Recall (function-level)

| Metric | Value |
|--------|-------|
| Strict Recall (exact name, top-1) | 43.90% (18/41) |
| Loose Recall (substring, top-1) | 48.78% (20/41) |
| hit@1 (any of top-1 matches GT) | 43.90% (18/41) |
| hit@2 (any of top-2 matches GT) | 51.22% (21/41) |
| hit@3 (any of top-3 matches GT) | 53.66% (22/41) |

## Compute

| Metric | Value |
|--------|-------|
| Total LLM calls | 200 |
| Total prompt tokens | 231535 |
| Total completion tokens | 167959 |
| Wall-clock total (s) | 34129.6 |
| System fingerprints | gpt-5-mini-2025-08-07 |

## Per-case outcomes

| case_id | GT function | Predicted (top-1) | Top-3 candidates | hit@1 | hit@3 |
|---------|-------------|-------------------|------------------|-------|-------|
| NOYA-H-04 | `executeWithdraw` | `` | — | ✗ | ✗ |
| NOYA-H-08 | `sendTokensToTrustedAddress` | `sendTokensToTrustedAddress` | `sendTokensToTrustedAddress`, `addLiquidity`, `transferPositionToAnotherConnector` | ✓ | ✓ |
| NOYA-M-03 | `executeManagerAction` | `` | — | ✗ | ✗ |
| CSW-H-01 | `removeOwnerAtIndex` | `initialize` | `initialize`, `executeWithoutChainIdValidation`, `canSkipChainIdValidation` | ✗ | ✗ |
| GRA-H-02 | `upgradeTo` | `_initialize` | `_initialize`, `permit`, `addMinter` | ✗ | ✗ |
| GIT-M-02 | `setStakeParameters` | `initialize` | `initialize`, `lockAndBurn`, `_authorizeUpgrade` | ✗ | ✗ |
| C4-161 | `removeFeeder` | `removeFeeder` | `removeFeeder`, `addFeeder`, `transferOwnership` | ✓ | ✓ |
| C4-35 | `removeFeeder` | `` | — | ✗ | ✗ |
| C4-222 | `mint` | `` | — | ✗ | ✗ |
| C4-6 | `increaseDebt` | `increaseDebt` | `increaseDebt` | ✓ | ✓ |
| C4-21 | `setUp` | `startRewardsCycle` | `startRewardsCycle`, `distributeInitialSupply`, `testExploit` | ✗ | ✗ |
| C4-55 | `removeFeeder` | `removeFeeder` | `removeFeeder`, `addFeeder`, `initialize` | ✓ | ✓ |
| C4-29 | `burn` | `burn` | `burn` | ✓ | ✓ |
| C4-17 | `testExploit` | `calculateAndDistributeRewards` | `calculateAndDistributeRewards` | ✗ | ✗ |
| C4-438 | `buy` | `initialize` | `initialize`, `buy`, `refund` | ✗ | ✓ |
| C4-111 | `unknown_function` | `` | — | ✗ | ✗ |
| C4-80 | `auctionStartTime` | `_setAuctionStartTime` | `_setAuctionStartTime`, `_clearAuctionState`, `_auctionCurrentPrice` | ✗ | ✗ |
| C4-19 | `isIncluded` | `isIncluded` | `isIncluded` | ✓ | ✓ |
| C4-487 | `onDeposit` | `pay` | `pay`, `onDeposit()`, `onDeposit` | ✗ | ✓ |
| C4-186 | `removeFeeder` | `removeFeeder` | `removeFeeder`, `_removeFeeder` | ✓ | ✓ |
| C4-22 | `isIncluded` | `` | — | ✗ | ✗ |
| C4-328 | `unknown_function` | `` | — | ✗ | ✗ |
| C4-169 | `setUnderlyingPrice` | `setUnderlyingPrice` | `setUnderlyingPrice`, `setDirectPrice` | ✓ | ✓ |
| C4-51 | `AddProposal` | `AddProposal` | `AddProposal` | ✓ | ✓ |
| C4-318 | `fillOrder` | `` | — | ✗ | ✗ |
| C4-165 | `updateBaseRate` | `updateBaseRate` | `updateBaseRate`, `updateBaseRate(uint newBaseRatePerYear)`, `updateBaseRate(uint256)` | ✓ | ✓ |
| C4-172 | `queue` | `queue` | `queue` | ✓ | ✓ |
| C4-63 | `AddProposal` | `AddProposal` | `AddProposal` | ✓ | ✓ |
| C4-174 | `approve` | `approve(address owner, address spender)` | `approve(address owner, address spender)`, `approve`, `approve(address owner, address spender) external returns (bool)` | ✗ | ✓ |
| C4-67 | `incrementWindow` | `incrementWindow` | `incrementWindow` | ✓ | ✓ |
| C4-3 | `wrap` | `wrap` | `wrap`, `unwrap`, `wrap(address to_, address from_)` | ✓ | ✓ |
| C4-248 | `testExploit` | `withdraw` | `withdraw` | ✗ | ✗ |
| C4-54 | `unwrapWETH9` | `sweepToken` | `sweepToken`, `unwrapWETH9`, `refundETH` | ✗ | ✓ |
| C4-286 | `unknown_function` | `onRedeem` | `onRedeem`, `setTreasury`, `initialize` | ✗ | ✗ |
| C4-572 | `setUp` | `incrementNonce` | `incrementNonce`, `initialize`, `setExecutionDelegate` | ✗ | ✗ |
| C4-229 | `burnFeiHeld` | `burnFeiHeld` | `burnFeiHeld` | ✓ | ✓ |
| C4-226 | `testMisleadingGetAddress` | `deploy` | `deploy`, `initialize`, `setGovernor` | ✗ | ✗ |
| C4-484 | `activateProposal` | `activateProposal` | `activateProposal` | ✓ | ✓ |
| C4-126 | `install` | `install` | `install`, `install(bytes4[] memory _selectors, address[] memory _plugins)` | ✓ | ✓ |
| C4-190 | `receiveCollateral` | `receiveCollateral` | `receiveCollateral`, `receiveCollateral(address[] memory _tokens, uint256[] memory _amounts)` | ✓ | ✓ |
| C4-264 | `unknown_function` | `wrap` | `wrap`, `unwrap`, `initialize` | ✗ | ✗ |

## Skipped (empty source)

- NOYA-H-04 (VaultWithdrawManager): empty contract_source
- NOYA-M-03 (VaultManager): empty contract_source