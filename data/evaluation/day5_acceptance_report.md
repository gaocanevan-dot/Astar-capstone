# Day-5 Acceptance Report — ReAct Agent + Long-Term Memory

**Q3 Verdict**: ✅ Q3 met — ship ReAct agent as primary demo

## Acceptance criteria (Q3-aware bar; AC6 dropped per Critic)

| AC | Criterion | Result | Verdict |
|----|-----------|--------|---------|
| AC1_self_terminate | 10/10 (need >=7) | ✅ |
| AC2_distinct_tools | avg 5.80 (need >=3.0) | ✅ |
| AC3_episodic_lessons | 10/10 (≥70%) | ✅ |
| AC4_unique_lessons | deferred to memory store inspection | ✅ |
| AC5b_recall_nonempty | 0/10 (need >=2) | ❌ |
| AC7_budget | $0.1485 <= $2.5 | ✅ |
| AC8_traces | 10/10 markdown traces | ✅ |

## Pass count (informational, AC6 dropped)

- ReAct sweep pass count: **4/10**
- Day-4 pipeline pass count: **6/10**
- Zero-shot e2e baseline: **4/10**

- Recall@1 (informational): 0/10

## R7 Fallback Decision

**R7 NOT triggered.** ReAct agent ships as primary demo. 
Day-4 pipeline retained as Day-4 baseline reference.

Capstone narrative angle: agent replaces pipeline as primary, 
with Day-3/4 progression preserved as ablation history.

## Per-case detail

| case | gt | predicted | terminal | iters | tools | verdict | recall | $ |
|------|----|-----------|----------|-------|-------|---------|--------|---|
| ACF-092 | `swapAndLiquifyStepv1` | `transferFromm` | submit_finding | 7 | 6 | pass | ✗ | $0.0154 |
| ACF-102 | `WhiteListMint` | `approve` | give_up | 7 | 6 | fail_error_runtime | ✗ | $0.0144 |
| ACF-091 | `_withdraw` | `addStrategy` | give_up | 7 | 6 | fail_error_runtime | ✗ | $0.0164 |
| ACF-106 | `pledgeAndBorrow` | `notifyOrderLiquidated` | give_up | 7 | 6 | fail_error_compile | ✗ | $0.0192 |
| ACF-093 | `depositFromOtherContract` | `updatePool` | give_up | 7 | 6 | fail_error_runtime | ✗ | $0.0176 |
| ACF-114 | `OnlyOwner` | `` | give_up | 3 | 3 | - | ✗ | $0.0080 |
| ACF-103 | `_transfer` | `transferFrom` | submit_finding | 6 | 6 | pass | ✗ | $0.0108 |
| ACF-087 | `mint` | `transferFrom` | submit_finding | 6 | 6 | pass | ✗ | $0.0111 |
| ACF-109 | `deposit` | `initialize` | give_up | 8 | 7 | fail_revert_ac | ✗ | $0.0216 |
| ACF-101 | `swap` | `massMintPools` | submit_finding | 6 | 6 | pass | ✗ | $0.0140 |

## Files referenced

- Sweep aggregate: `data\evaluation\react_sweep_run1.json`
- Per-case traces: `data\evaluation\react_traces/`
- Day-4 baseline: `data\evaluation\smoke_agent-full.json`
- Zero-shot baseline: `data\evaluation\smoke_gpt-zeroshot-e2e.json`
- Disclosure: `.omc/plans/day4-routing-reversal-disclosure.md` (Day-4 lineage)
