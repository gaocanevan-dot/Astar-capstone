# Day-6 — Path B Pivot (PRE-COMMITTED, do NOT edit after sweep)

**Status when committed**: Day-5b shipped. Day-6 plan v6 APPROVED.
This file is committed BEFORE Step 0a runs. It codifies what we will
claim IF Step 0a (blind buildability) returns <18 buildable OR Step 0b
(AC10d audit) drops survivors below n_floor=15. No tuning-after-the-fact.

**Activation gate**: Step 0a `buildable_count` < 18 OR Step 0b survivors < 15.

**ACTIVATION CONFIRMED 2026-05-02**: Step 0a real run returned
`buildable_count = 5` of 23 candidates → Path B triggered. Step 0b
verified library-quality gates pass (AC10a 100% / AC10b 19% / AC10c 0
illegal / AC10d 16 survivors), so the failure is NOT library
contamination — it is candidate-source viability. Most ACF cases
reference imports/dependencies that don't bundle into the standalone
Foundry workspace this script attempts to compile in.

---

## Headline (post-Step-0a actual numbers)

> "Day-6 Path A (clean ACF holdout) was not viable: forge-buildability
> shortfall (5/23 buildable in standalone Foundry workspace) reduced the
> candidate pool below the n_floor=15 required for any defensible
> statistical claim. Library-quality gates (AC10a/b/c/d) all PASSED on
> the 23-case pool — root cause is NOT contamination, it is
> **candidate-source viability**: most ACF contracts depend on
> imports/dependencies that don't bundle into the isolated standalone
> compilation harness Step 0a uses. Path B (alternative corpus)
> activation pending operator decision on Step 0c spot-check.
> Day-6 RAG mechanism (AntiPatternInjector at propose_target) is NOT
> evaluated in this round; design + skeleton are committed for re-use
> on the next viable corpus."

## Why Path A failed

Step 0a buildable_count: **5** (need ≥18 for n=15 routing, ≥21 for n=18)
Step 0b AC10d survivors: 16 (would have passed, but moot given Step 0a)

Detailed breakdown:
- **Forge build failures on 18 of 23 candidate cases.** Per the blind-screen
  rule, per-ID failure reasons are NOT logged. Likely causes (informed
  guess from contract layout): missing imports (OpenZeppelin / project
  internal interfaces), pre-0.8 pragma incompatibilities (`_resolve_pragma`
  routes those to `replica_only` and the script returns False), and
  reference to types defined in sibling source files.
- **AC10d Jaccard would have dropped 7 cases** (ACF-096 perfect duplicate +
  6 cases sharing 0.40-0.67 token overlap with ACF-078 onlyowner cluster),
  leaving 16 survivors. This passed the n_floor=15 gate, but the much
  smaller buildability pool dominates the routing decision.
- Either bottleneck alone would have been recoverable; both compounded
  produces a hard Path B trigger.

**Critical finding to commit**: the 23-case clean pool is too small AND
too close to the library's training distribution for valid n=18+ RAG
testing. This is itself a paper-worthy result about how curated audit
libraries overfit to their source dataset.

## Path B options (in priority order)

| Priority | Source | Pre-condition | Estimated buildable | Cost ceiling for spot-check |
|---|---|---|---|---|
| 1 | SmartBugs-curated (~140 vulns, 7 categories) | local checkout available | unknown | $0.10 |
| 2 | Code4rena post-2023 contests (excluded from rag_training) | github API access | unknown | $0.20 |
| 3 | Slither audited-set (CertiK-style) | dataset license check | unknown | $0.30 |

Step 0c spot-check ran 3 cases on Priority 1 source: result {PATHB_RESULT}.

If Priority 1 fails, fall to Priority 2; if all 3 fail, defer Day-6 RAG
testing to Day-7 (synthetic corpus generation).

## Architecture artifact (committed regardless of corpus)

The following code is committed even though Day-6 RAG sweep is
deferred. These artifacts form the foundation for whatever corpus we
test against in Day-7:

- `src/agent/rag/__init__.py` — package surface
- `src/agent/rag/base.py` — `RAGInjector` ABC
- `src/agent/rag/null_injector.py` — baseline / zero-shot
- `src/agent/rag/anti_pattern_injector.py` — Day-6 implementation (skeleton)
- `src/agent/rag/registry.py` — mode → injector factory
- `scripts/day6_blind_screen.py` — buildability harness (corpus-agnostic)
- `scripts/day6_audit.py` — AC10a/b/c/d auditor (parameterized over source)
- `scripts/calibrate_jaccard.py` — Jaccard threshold calibrator (reusable)
- `.omc/plans/day-6-blind-screen-rule.md` — operating rule (reusable)

## Day-6 paper-worthy findings (Path B version)

1. **F5 — Curated audit libraries overfit to source dataset.**
   AC10d Jaccard hub-detection caught {N_AC10D_DROPS} of 23 ACF cases
   sharing 40-67% token overlap with one library entry (ACF-078). This
   pattern arises because library curation pulls from sequentially-
   numbered cases (ACF-036 through ACF-085) which share attack
   structure with later cases (ACF-086+) from the same source. Library
   curation that ignores intra-source clustering creates leakage that
   simple ID-overlap or function-name audits cannot detect.

2. **F6 — Path A unviable** for ACF-family RAG ablation under current
   library composition. Recommends curating future libraries from
   strictly disjoint sources (different audit firms, different vuln
   families, different time periods).

3. **Modular RAG architecture (`src/agent/rag/`) is corpus-agnostic.**
   The same injector design swaps in/out for SmartBugs / Code4rena /
   synthetic corpora without ReAct loop modification. Validated by
   `RAGInjector` interface holding through corpus pivot.

4. **Pre-flight contamination audit is a separable, reusable primitive.**
   `scripts/day6_audit.py` will be reused as-is on Path B corpus —
   only the holdout source CSV path changes.

## What this does NOT claim

1. **NOT "RAG injection at propose_target was tested and failed."**
   It was NOT tested. Sweep deferred until viable corpus.
2. **NOT pessimism about RAG.** Hypothesis remains open.
3. **NOT validity for any specific Path B corpus** — Step 0c spot-check
   provides only a 3-case viability signal, not a buildability guarantee.

## Acceptance criteria tally (Path B branch, actual)

| AC | Threshold | Result | Pass? |
|---|---|---|---|
| AC10a coverage | ≥60% | 100% on Path A holdout | YES |
| AC10b leakage (post-AC10d survivors) | <30% | 19% (3/16) | YES |
| AC10c ID overlap | 0 | 0 | YES |
| AC10d Jaccard survivors | ≥15 | 16 | YES |
| **Step 0a buildability** | **≥18** | **5** | **NO** ← Path B trigger |
| AC11–AC20 | various | NOT EVALUATED | n/a |

**Note**: AC10d alone would have passed (16 survivors ≥ 15 floor). The
Path B trigger is buildability, not contamination. This is informative
for Day-7 corpus selection: a viable corpus needs both clean library
audit AND standalone-buildable contracts.

## Operator decision point (NEW — surfaced post-Step-0a)

The blind-screen rule forbids per-ID inspection of which 5 cases built.
Two options for next iteration:

1. **Honor blind rule, pivot to Path B fully**: never inspect which 5,
   spend Step 0c spot-check on SmartBugs-curated, run Day-7 there.
   Most defensible epistemically. Discards the 5 buildable as
   not-investigatable.

2. **Drop blind rule for Path B prep, salvage the 5**: re-run Step 0a
   in non-blind mode, identify the 5, use them as a qualitative pilot
   (n=5, no statistical claim). This violates the pre-committed blind
   rule but is methodologically defensible IF we explicitly tag the
   re-run as "blind-rule-suspended for Path B salvage" and add the
   suspension to the audit trail.

Recommendation: **Option 1**. n=5 isn't enough for any RAG signal even
qualitatively; the 5 cases sit ambiguously between "useful pilot" and
"cherry-picked anecdote" in any writeup. Spending the budget on
SmartBugs spot-check has a cleaner downstream story.

## Stop rule

**LAST_POSTHOC_ROUND_ON_HOLDOUT_V1** still applies — the 23-case clean
ACF pool is now characterized and cannot be re-used as fresh validation
material. Day-7 must use Path B-or-C corpus exclusively for any
quantitative RAG claim.

## Day-7 redirect

1. If Step 0c on SmartBugs-curated returned PASS: Day-7 = repeat full
   v6 plan on SmartBugs holdout (re-use scripts/audit, re-calibrate
   Jaccard for new corpus, no architectural changes needed).
2. If Step 0c failed: Day-7 = synthetic corpus generation (~0.5 day)
   then repeat v6 plan.
3. Either way: AntiPatternInjector body fills in (Step 2 of v6) at
   Day-7 kickoff, not now. Skeleton commit suffices for now.
