# Day-6 — RAG Ineffective (PRE-COMMITTED, do NOT edit after sweep)

**Status when committed**: Day-5b shipped. Day-6 plan v6 APPROVED.
This file is committed BEFORE the Day-6 sweep. It codifies what we
will claim IF the sweep returns delta ≤ 0. No tuning-after-the-fact.

**Activation gate** (from `scripts/day6_acceptance_gate.py`):
- pass(6-rag-inject) - pass(6-baseline) ≤ 0

(Tertiary 0 < delta < 3 → ship `day-6-rag-inconclusive.md` instead.)

---

## Headline (PRE-WRITTEN)

> "Day-6 system-injected anti_patterns RAG at the propose_target step
> did NOT lift pass count beyond baseline on a fresh n={n} ACF holdout
> (baseline {N_BASELINE}/{n}, rag {N_RAG}/{n}, delta {DELTA}, sign-test
> p={P:.3f}). The system-injection mechanism worked correctly (AC15
> verified, AC11 retrieval@3 = {AC11:.2f}) — agent receives
> family-relevant patterns at the decision moment, then proceeds to
> select the same target it would have selected without injection.
> Conclusion: **the bottleneck is base-LLM ranking stickiness, not
> retrieval availability.** Cascade graft (Day-5b, post-hoc retry) was
> -1; RAG injection (Day-6, pre-decision) is {DELTA}. Both interventions
> are net non-positive — root cause is upstream of the injection layer."

## Day-6 paper-worthy findings (negative-but-publishable)

1. **F5 — RAG injection content reaches agent context but does not shift
   first-target choice.** Verified by AC11 retrieval@3 = {AC11:.2f}
   (agent does receive same-family patterns) AND AC12 delta = {DELTA}
   (no behavioural change). Strong evidence that LLM base-ranking
   prior dominates retrieved content at this scale.
2. **AC5b shape persists across two intervention modalities.** Day-5
   `recall_self_lesson`: 0/10 organic. Day-5b `try_next_candidate`: 0/10
   organic. Day-6 `recall_anti_pattern` system-injected: agent reads
   it, doesn't act on it. Three independent failure modes converge on
   "constrained ReAct under iteration cap is impervious to retrieval
   in standard form."
3. **Hub-detection contamination audit (AC10d) caught {DROP_N} cases**
   that ID-overlap and function-name leakage both missed. Reusable
   audit primitive even when downstream RAG result is null.
4. **Modular RAG architecture (`src/agent/rag/`) survives the negative
   result intact.** The `RAGInjector` interface and the registry are
   ready for Day-7 alternative injectors (different content sources,
   different prompt formats, different injection points). The negative
   finding redirects future work toward content-shape and prompt-format
   ablations rather than retrieval-availability ablations.

## What this does NOT claim

1. **NOT "RAG is useless."** Only this specific injection point with
   this specific content shape underperformed. Day-7 alternatives
   (different prompt format, different content source, different injection
   timing) remain hypotheses.
2. **NOT generalization.** Single corpus (access-control), single library
   (anti_patterns), single embedding model (text-embedding-3-small).
3. **NOT a final verdict on the agent.** Day-5b ReAct architecture
   matches Day-4 hardcoded pipeline at 6/10 baseline; that result stands.

## Acceptance criteria final tally (mechanically populated)

| AC | Threshold | Result | Pass? |
|---|---|---|---|
| AC10a/b/c/d (audit gate) | various | passed Step 0b | YES |
| AC11 retrieval@3 | ≥0.5 | {AC11:.2f} | {V11} |
| AC12 pass delta (primary) | ≥+3 | {DELTA} | NO (this is the ineffective branch) |
| AC13 self-term | ≥{N_SELFTERM_FLOOR}/{n} | {ST_BASELINE}/{n}, {ST_RAG}/{n} | {V13} |
| AC14 sweep cost | ≤$1.00 | $0.{TOTAL_COST} | {V14} |
| AC15 honest naming + no double-dip | required | {AC15_NOTES} | {V15} |
| AC16 sign-test p | <0.10 | {P_VALUE:.3f} | NO (one-sided test cannot reject) |
| AC18 holdout SHA256 | match | OK | YES |
| AC19 narratives mtime | < sweep start | OK | YES |

## Cross-sweep reference (F3 secondary, NOT gate)

- Day-5b 5-baseline ACF n=10: 6/10
- Day-6 6-baseline holdout_v1 n={n}: {N_BASELINE}/{n} = {RATE_BASELINE:.0%}
- F3 flag: {F3_FLAG} (cross-sweep consistency)

## Stop rule

**LAST_POSTHOC_ROUND_ON_HOLDOUT_V1**. Day-7+ requires Path B/C corpus.

## Day-7 redirect (per F5)

The negative result reframes Day-7 priorities. Instead of "more retrieval
sources" (episodic, hybrid), Day-7 should test:
- Different prompt format (chain-of-thought scaffold vs raw injection)
- Different injection content (one detailed example vs k shallow examples)
- Different injection timing (before vs after candidate enumeration)

These hypotheses are addressable by new `RAGInjector` subclasses without
touching the loop, validating the modular architecture decision even on
a negative outcome.
