# Full-Pipeline Summary (analyst + builder + verifier)

- cases run: 42
- total wall-clock: 9876.5s
- total LLM calls: 78
- total tokens (prompt+completion): 182079
- total builder retries: 4
- system fingerprints: gpt-5-mini-2025-08-07

## Verdict distribution

| Verdict | Count | % |
|---------|-------|---|
| pass | 34 | 81% |
| fail_revert_ac | 0 | 0% |
| fail_error | 0 | 0% |
| skipped | 8 | 19% |

## Layer metrics

- Analyst-level function-recall (strict): 17/42
- Analyst-level function-recall (loose):  18/42
- End-to-end PoC-pass (forge test success): 34/42
- AC-intercepted (contract appears safe):  0/42
- Retry-exhausted (likely compile/dep issue): 0/42
- Skipped (empty source or no target):       8/42

## Per-case outcomes

| case_id | GT fn | Analyst pred | Verdict | Attempts | Reason |
|---------|-------|--------------|---------|----------|--------|
| NOYA-H-04 | `executeWithdraw` | `` | skipped | 0 | empty contract_source |
| NOYA-H-08 | `sendTokensToTrustedAddress` | `updateSwapHandler` | pass | 1 | PoC executed and attack succeeded |
| NOYA-M-03 | `executeManagerAction` | `` | skipped | 0 | empty contract_source |
| CSW-H-01 | `removeOwnerAtIndex` | `executeWithoutChainIdValidation` | pass | 1 | PoC executed and attack succeeded |
| GRA-H-01 | `` | `initialize` | pass | 1 | PoC executed and attack succeeded |
| GRA-H-02 | `upgradeTo` | `_initialize` | pass | 1 | PoC executed and attack succeeded |
| GIT-M-02 | `setStakeParameters` | `initialize` | pass | 1 | PoC executed and attack succeeded |
| C4-161 | `removeFeeder` | `removeFeeder` | pass | 1 | PoC executed and attack succeeded |
| C4-35 | `removeFeeder` | `` | skipped | 0 | analyst returned empty target_function |
| C4-222 | `mint` | `mint` | pass | 1 | PoC executed and attack succeeded |
| C4-6 | `increaseDebt` | `increaseDebt` | pass | 2 | PoC executed and attack succeeded |
| C4-21 | `setUp` | `distributeInitialSupply` | pass | 2 | PoC executed and attack succeeded |
| C4-55 | `removeFeeder` | `` | skipped | 0 | analyst returned empty target_function |
| C4-29 | `burn` | `burn` | pass | 1 | PoC executed and attack succeeded |
| C4-17 | `testExploit` | `calculateAndDistributeRewards` | pass | 1 | PoC executed and attack succeeded |
| C4-438 | `buy` | `initialize` | pass | 1 | PoC executed and attack succeeded |
| C4-111 | `unknown_function` | `` | skipped | 0 | analyst returned empty target_function |
| C4-80 | `auctionStartTime` | `_setAuctionStartTime` | pass | 1 | PoC executed and attack succeeded |
| C4-19 | `isIncluded` | `` | skipped | 0 | analyst returned empty target_function |
| C4-487 | `onDeposit` | `pay` | pass | 1 | PoC executed and attack succeeded |
| C4-186 | `removeFeeder` | `removeFeeder` | pass | 1 | PoC executed and attack succeeded |
| C4-22 | `isIncluded` | `CallRedeemhook` | pass | 1 | PoC executed and attack succeeded |
| C4-328 | `unknown_function` | `` | skipped | 0 | analyst returned empty target_function |
| C4-169 | `setUnderlyingPrice` | `setDirectPrice` | pass | 1 | PoC executed and attack succeeded |
| C4-51 | `AddProposal` | `AddProposal` | pass | 1 | PoC executed and attack succeeded |
| C4-318 | `fillOrder` | `fillOrder` | pass | 1 | PoC executed and attack succeeded |
| C4-165 | `updateBaseRate` | `updateBaseRate` | pass | 1 | PoC executed and attack succeeded |
| C4-172 | `queue` | `queue` | pass | 1 | PoC executed and attack succeeded |
| C4-63 | `AddProposal` | `AddProposal` | pass | 2 | PoC executed and attack succeeded |
| C4-174 | `approve` | `approve` | pass | 1 | PoC executed and attack succeeded |
| C4-67 | `incrementWindow` | `incrementWindow` | pass | 1 | PoC executed and attack succeeded |
| C4-3 | `wrap` | `wrap` | pass | 1 | PoC executed and attack succeeded |
| C4-248 | `testExploit` | `withdraw` | pass | 1 | PoC executed and attack succeeded |
| C4-54 | `unwrapWETH9` | `sweepToken` | pass | 1 | PoC executed and attack succeeded |
| C4-286 | `unknown_function` | `` | skipped | 0 | analyst returned empty target_function |
| C4-572 | `setUp` | `incrementNonce` | pass | 1 | PoC executed and attack succeeded |
| C4-229 | `burnFeiHeld` | `burnFeiHeld` | pass | 1 | PoC executed and attack succeeded |
| C4-226 | `testMisleadingGetAddress` | `deploy` | pass | 1 | PoC executed and attack succeeded |
| C4-484 | `activateProposal` | `activateProposal` | pass | 1 | PoC executed and attack succeeded |
| C4-126 | `install` | `install` | pass | 1 | PoC executed and attack succeeded |
| C4-190 | `receiveCollateral` | `receiveCollateral` | pass | 2 | PoC executed and attack succeeded |
| C4-264 | `unknown_function` | `wrap` | pass | 1 | PoC executed and attack succeeded |