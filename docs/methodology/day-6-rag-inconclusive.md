# Day-6 — RAG Inconclusive (PRE-COMMITTED, do NOT edit after sweep)

**Status when committed**: Day-5b shipped. Day-6 plan v6 APPROVED.
This file is committed BEFORE the Day-6 sweep. It codifies what we
will claim IF the sweep returns 1 ≤ delta < 3 OR sign-test p ≥ 0.10.
No tuning-after-the-fact.

**Activation gate** (from `scripts/day6_acceptance_gate.py`):
- 1 ≤ delta < 3 OR (delta ≥ 3 AND sign-test p ≥ 0.10)

**Rerun cap (Architect closure)**: max 2 consecutive inconclusive
sweeps on the same intervention. 3rd attempt MUST ship
`day-6-rag-ineffective.md` regardless of delta.

---

## Headline (PRE-WRITTEN)

> "Day-6 system-injected anti_patterns RAG at the propose_target step
> produced a directional positive signal (delta = +{DELTA}, sign-test
> p={P:.3f}) that did NOT clear the AC12 publication threshold (+3 with
> p<0.10). At n={n}, this is the underpowered-positive outcome the
> v6 design explicitly anticipated. Reporting as DESCRIPTIVE only —
> AC12-D triggered, AC12 primary did not. Per Architect synthesis: this
> result requires Day-6.5c power analysis before any re-investment, NOT
> automatic n-doubling on the same holdout (which would be data snooping
> by the Day-5b stop-rule logic)."

## Why this branch exists

n=15 or n=18 cannot detect small effects (delta=1 or 2) at α<0.10. v6
plan v4-Critic-approved this branch as the honest middle outcome,
preferring Type I error control over Type II — i.e., we'd rather miss a
real small effect than claim a false-positive.

## Day-6.5c power analysis required (BEFORE any rerun)

Per architect closure + critic approval:

1. **What sample size would have been needed** to detect the observed
   delta at p<0.10? Compute and document.
2. **Is that sample size achievable** within budget on a NEW corpus?
3. **What's the smallest effect size** that's worth detecting given
   downstream usage of the RAG mechanism?
4. **Decision rule**: only proceed to Day-7 RAG-related work if (2) is
   yes AND (3) is met.

If Day-6.5c concludes (2) or (3) cannot be satisfied, treat the Day-6
result as Day-7-redirect "directional, not actionable" and pivot to
content-shape ablations on the existing AntiPatternInjector instead of
sample-size expansion.

## Day-6 paper-worthy findings (under-powered version)

1. **F5 — Directional positive on small sample.** Suggestive but not
   significant evidence that pre-decision RAG injection moves
   candidate-ranking. Requires replication on larger corpus.
2. **Hub-detection contamination audit (AC10d) caught {DROP_N} cases**
   that ID-overlap and function-name leakage missed.
3. **AC5b shape on injected content**: agent received the patterns but
   shifted target {SHIFT_RATE:.0%} of the time, with successful
   {DELTA}/{n} downstream pass impact. Lower bound on real effect.
4. **Modular RAG architecture validated** for ablation despite
   inconclusive primary outcome.

## What this does NOT claim

1. **NOT "RAG works."** Primary publication threshold not met.
2. **NOT "RAG is broken."** Direction is correct; magnitude undetectable
   at this n.
3. **NOT a basis for production deployment** of the AntiPatternInjector
   in any downstream system.

## Acceptance criteria tally (mechanically populated)

| AC | Threshold | Result | Pass? |
|---|---|---|---|
| AC10a/b/c/d | various | passed Step 0b | YES |
| AC11 retrieval@3 | ≥0.5 | {AC11:.2f} | {V11} |
| AC12 pass delta (primary) | ≥+3 | +{DELTA} | NO (inconclusive branch) |
| **AC12-D descriptive** | ≥+2 (directional only) | +{DELTA} | YES |
| AC13 self-term | ≥{N_SELFTERM_FLOOR}/{n} | {ST_BASELINE}/{n}, {ST_RAG}/{n} | {V13} |
| AC14 sweep cost | ≤$1.00 | $0.{TOTAL_COST} | {V14} |
| AC15 honest naming + no double-dip | required | {AC15_NOTES} | {V15} |
| AC16 sign-test p | <0.10 | {P_VALUE:.3f} | NO |
| AC18 holdout SHA256 | match | OK | YES |
| AC19 narratives mtime | < sweep start | OK | YES |
| AC20 tertiary branch shipped | required | YES (this file) | YES |

## Publication-language constraint (Critic minor finding)

**Any document mentioning AC12-D MUST also state the AC12 primary
result in the same sentence/bullet.** AC12-D may NOT appear in
abstract or conclusion sections without AC12 outcome attached.
This rule is enforced by content review, not mechanical verifier.

## Cross-sweep reference (F3 secondary, NOT gate)

- Day-5b 5-baseline ACF n=10: 6/10
- Day-6 6-baseline holdout_v1 n={n}: {N_BASELINE}/{n} = {RATE_BASELINE:.0%}

## Stop rule

**LAST_POSTHOC_ROUND_ON_HOLDOUT_V1**. The 23-case clean ACF pool is
now consumed; characterization runs (different embedding, expanded
library) MAY reuse same IDs but scoring is not re-counted as fresh
evidence (per v6 narrowed pool-exhaustion clause).

## Rerun history slot (mechanical)

| attempt | sweep_date | result_branch | delta | p |
|---|---|---|---|---|
| 1 | {SWEEP_DATE} | inconclusive | +{DELTA} | {P_VALUE:.3f} |

If this table reaches 2 entries with branch=inconclusive, attempt 3
MUST ship `day-6-rag-ineffective.md` (Architect rerun-cap closure).
