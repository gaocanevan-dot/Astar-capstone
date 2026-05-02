# Day-6 — RAG Effective (PRE-COMMITTED, do NOT edit after sweep)

**Status when committed**: Day-5b shipped (Day-5 ReAct architecture matches
Day-4 pipeline at 6/10; cascade unused or net-negative). Day-6 plan v6
APPROVED by ralplan consensus. Holdout = clean ACF subset filtered by
AC10a/b/c/d. RAG injection = `AntiPatternInjector` from
`src/agent/rag/anti_pattern_injector.py`, fired at first `propose_target`
step. Mode `--mode 6-rag-inject`.

This file is committed BEFORE the Day-6 3-arm sweep runs. It codifies
exactly what we will claim IF the sweep delivers the headline numbers
below. No tuning-after-the-fact.

**Activation gate** (mechanical, from `scripts/day6_acceptance_gate.py`):
- AC12 primary: pass(6-rag-inject) - pass(6-baseline) >= +3
- AC16 sign-test p < 0.10 one-tailed
- AC10a/b/c/d all PASS at Step 0b
- AC11 retrieval@3 family-coverage >= 0.5 on same-family cases
- AC15 injection tagged + no double-dip
- AC14 sweep cost <= $1.00

If gate exits non-zero, ship `day-6-rag-ineffective.md` or
`day-6-rag-inconclusive.md` based on the actual numbers.

---

## Headline (PRE-WRITTEN)

> "Day-6 system-injected anti_patterns RAG at the propose_target step
> lifts pass count from {N_BASELINE}/{n} to **{N_RAG}/{n}** on a fresh
> n={n} ACF holdout. The lift is large enough (+{DELTA} >= +3, sign-test
> p={P:.3f} < 0.10) to credit the RAG mechanism with a real
> candidate-ranking improvement, not single-seed variance. AC11 retrieval
> precision at top-3 is {AC11:.2f}, confirming the agent receives
> family-relevant patterns at the decision moment. The system-injection
> design (`AntiPatternInjector` from `src/agent/rag/`) is decoupled from
> ReAct loop and ablation-ready for Day-7 episodic + hybrid variants."

## Cross-day final scoreboard (template — fill in actual)

| System | Pass/n | Recall@1 | Cost | Architecture |
|---|---|---|---|---|
| Zero-shot e2e (Day-3 baseline) | 4/10 | 2/10 | $0.0956 | single LLM + single forge |
| Day-4 pipeline | 6/10 | 2/10 | $0.2912 | hardcoded cascade hybrid |
| Day-5b 5-baseline (ACF n=10) | 6/10 | 1/10 | $0.1872 | ReAct + 3-tier memory, no RAG |
| **Day-6 6-baseline (holdout_v1 n={n})** | **{N_BASELINE}/{n}** | {RC1B} | $0.{C1B} | ReAct, no RAG injection |
| **Day-6 6-rag-inject (holdout_v1 n={n})** | **{N_RAG}/{n}** | {RC1R} | $0.{C1R} | + system-injected anti_patterns at propose_target |
| Day-6 6-zero-shot (holdout_v1 n={n}) | {N_ZS}/{n} | {RC1Z} | $0.{C1Z} | reference for cross-corpus drift |

**3-arm experiment total cost**: $0.{TOTAL_COST} (cap: $1.00).

## What this DOES claim

1. **System-injected RAG at the right decision point lifts pass-count**
   beyond single-seed variance band on a held-out, hub-cleaned holdout.
2. **AntiPatternInjector is a viable building block** for ablation work:
   the abstract `RAGInjector` interface in `src/agent/rag/base.py` makes
   Day-7 episodic / hybrid drop-ins straightforward.
3. **Methodological rigor**: 7-AC minimal-core gate + 4-narrative
   pre-commit (Day-5b discipline extended) prevents post-hoc
   rationalization. AC10d hub-detection is a re-usable contamination
   audit primitive.

## What this does NOT claim

1. **NOT "agent learned to use RAG."** AC15 verifier confirms no organic
   `recall_anti_pattern` calls within injected cases. The lift is from
   system-injection, not agent elicitation. AC5b shape stays valid as a
   structural property of constrained ReAct.
2. **NOT generalization across vuln families.** Holdout is access-control
   only; reentrancy / oracle / etc. require a separate Day-7 ablation.
3. **NOT a refutation of Day-5b cascade negative finding.** Cascade was
   post-hoc retry; RAG-at-propose is pre-decision injection. Different
   mechanism, different evidence.

## Day-6 paper-worthy findings

1. **Right injection point matters more than which content is injected.**
   Cascade (post-hoc) was -1; RAG-at-propose was +{DELTA}. Same library,
   different mechanism placement.
2. **Hub-detection contamination audit (AC10d)** caught {DROP_N} cases that
   ID-overlap (AC10c) and function-name leakage (AC10b) both missed. The
   ACF-078 hub clustered {HUB_N} ostensibly-distinct holdout cases at
   Jaccard 0.40-0.67 against one library entry — a paper-quality
   contamination pattern that comes from sequentially-numbered DeFi-Hack
   cases sharing common attack code structure.
3. **AC5b shape persists for organic tools** even when system-injection
   succeeds — Day-5b finding holds.
4. **Modular RAG architecture** (`src/agent/rag/` package separable from
   `src/agent/react/`) enables future ablation without loop refactor.

## Acceptance criteria final tally (mechanically populated by gate)

| AC | Threshold | Result | Pass? |
|---|---|---|---|
| AC10a coverage | ≥60% | {AC10A:.0%} | {V10A} |
| AC10b leakage | <30% | {AC10B:.0%} | {V10B} |
| AC10c ID overlap | 0 | 0 | YES |
| AC10d Jaccard survivors | ≥15 | {AC10D_N} | {V10D} |
| AC11 retrieval@3 | ≥0.5 | {AC11:.2f} | {V11} |
| AC12 pass delta (primary) | ≥+3 | +{DELTA} | {V12} |
| AC13 self-term | ≥{N_SELFTERM_FLOOR}/{n} | {ST_BASELINE}/{n}, {ST_RAG}/{n} | {V13} |
| AC14 sweep cost | ≤$1.00 | $0.{TOTAL_COST} | {V14} |
| AC15 honest naming + no double-dip | required | {AC15_NOTES} | {V15} |
| AC16 sign-test p | <0.10 | {P_VALUE:.3f} | {V16} |
| AC18 holdout SHA256 | match | OK | YES |
| AC19 narratives mtime | < sweep start | OK | YES |
| AC20 tertiary branch ship | conditional | n/a (effective branch) | n/a |

## Stop rule (binding via commit message)

**This is the LAST post-hoc round on holdout_v1.** Commit message includes
literal `LAST_POSTHOC_ROUND_ON_HOLDOUT_V1`. Day-7+ requires either Path B
corpus (SmartBugs / Code4rena post-2023 / Slither audited) or Path C
synthetic corpus.

## Cross-sweep reference (F3 secondary, NOT gate)

- Day-5b 5-baseline ACF n=10: 6/10
- Day-6 6-baseline holdout_v1 n={n}: {N_BASELINE}/{n} = {RATE_BASELINE:.0%}
- Cross-sweep consistency flag: {F3_FLAG} (within 1σ of Day-5b baseline rate)
