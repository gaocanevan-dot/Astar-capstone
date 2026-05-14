# B Smoke Summary — pre-MCC baseline on new dataset

- cases run: 10
- elapsed: 582.9s
- total LLM calls: 22
- total tokens (prompt+completion): 88048
- analyst strict-recall: 5/10 (50%)

## Verdict distribution

| verdict | count | % |
|---|---|---|
| abstain | 1 | 10% |
| pass | 9 | 90% |

## Per-case

| case_id | GT fn | pred | verdict | attempts | reason |
|---|---|---|---|---|---|
| ACF-001 | `requestNewKeep` | `initialize` | pass | 1 | PoC succeeded at cascade depth 1 (target='initialize') |
| ACF-002 | `burnRebalancer` | `mintRebalancer` | pass | 1 | PoC succeeded at cascade depth 1 (target='mintRebalancer') |
| ACF-003 | `create` | `initialize` | pass | 1 | PoC succeeded at cascade depth 1 (target='initialize') |
| ACF-004 | `__INIT_VAULT` | `grantRole` | pass | 1 | PoC succeeded at cascade depth 1 (target='grantRole') |
| ACF-005 | `request` | `request` | abstain | 2 | Cascade abstained at depth 1: PoC retries exhausted (last error: │   │   └─ ← [R |
| ACF-006 | `mintRebalancer` | `mintRebalancer` | pass | 1 | PoC succeeded at cascade depth 1 (target='mintRebalancer') |
| ACF-007 | `initialize` | `initialize` | pass | 1 | PoC succeeded at cascade depth 1 (target='initialize') |
| ACF-008 | `Log` | `Log` | pass | 2 | PoC succeeded at cascade depth 1 (target='Log') |
| ACF-009 | `commitCollateral` | `setCollateralEscrowBeacon` | pass | 1 | PoC succeeded at cascade depth 1 (target='setCollateralEscrowBeacon') |
| ACF-010 | `init` | `init` | pass | 1 | PoC succeeded at cascade depth 1 (target='init') |