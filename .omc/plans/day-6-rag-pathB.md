# Day-6 — Path B Pivot (PRE-COMMITTED, do NOT edit after sweep)

**Status when committed**: Day-5b shipped. Day-6 plan v6 APPROVED.
This file is committed BEFORE Step 0a runs. It codifies what we will
claim IF Step 0a (blind buildability) returns <18 buildable OR Step 0b
(AC10d audit) drops survivors below n_floor=15. No tuning-after-the-fact.

**Activation gate**: Step 0a `buildable_count` < 18 OR Step 0b survivors < 15.

---

## Headline (PRE-WRITTEN)

> "Day-6 Path A (clean ACF holdout) was not viable: contamination
> hub-detection (AC10d) and/or forge-buildability shortfall reduced the
> candidate pool below the n_floor=15 required for any defensible
> statistical claim. Path B activated: Step 0c spot-check on
> {PATHB_SOURCE} confirmed/refused viability ({PATHB_RESULT}). The
> Day-6 RAG mechanism (AntiPatternInjector at propose_target) is NOT
> evaluated in this round; design + skeleton are committed for re-use
> on the next viable corpus."

## Why Path A failed

Step 0a buildable_count: {BUILDABLE_COUNT} (need ≥18)
Step 0b AC10d survivors: {SURVIVORS} (need ≥{N_FLOOR})

Reason for shortfall (one of):
- Forge build failures on {N_BUILD_FAIL} of 23 candidate cases
  (toolchain mismatch, missing dependencies, contract source corruption)
- AC10d Jaccard contamination dropped {N_AC10D_DROPS} cases
  (anti_patterns library too tightly coupled to ACF source — same
  attack patterns recur across sequentially-numbered DeFi-Hack cases)
- Both

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

## Acceptance criteria tally (Path B branch)

| AC | Threshold | Result | Pass? |
|---|---|---|---|
| AC10a coverage | ≥60% | {AC10A:.0%} on Path A holdout | {V10A} |
| AC10b leakage | <30% | {AC10B:.0%} on Path A holdout | {V10B} |
| AC10c ID overlap | 0 | 0 | YES |
| AC10d Jaccard survivors | ≥15 | {SURVIVORS} (< floor) | NO (this is why we're here) |
| AC11–AC20 | various | NOT EVALUATED | n/a |

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
