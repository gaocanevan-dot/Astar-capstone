# Plan iter4 — Agent-flow Recall Lift on n=10 Smoke Set

**Mode:** RALPLAN-DR Short, Planner pass 2 (revision against Critic 10-item bar)
**Foundation locked:** see iteration 3; not re-litigated.
**Levers (unchanged):** A1 cascade / B2 reflection (locked) / C3 tool-use / D2+D3 evidence-confirmed quality + abstain / E2 RAG (TF-IDF default).

---

## 1. Revision diff vs iter3

- **Ablation 6→4 arms.** Drop `no-tool-use` (dual-log artifact covers it) and `no-abstain` (post-processing toggle on `agent-full` predictions). Final arms: `agent-full` / `no-cascade` / `no-reflection` / `no-rag`. 4×10 = **40 runs**. (Critic #1)
- **RAG default = TF-IDF over `data/dataset/rag_training_dataset.json`** (85 docs, structured AC patterns; verified). Manual ~25-pattern library is optional polish, not a blocker. (Critic #2)
- **Reflection (B2) explicitly LOCKED** to top-K candidates emitted by analyst; cannot expand candidate set. Reason: n=10 + cascade early-exit cannot validate "expand candidate set" hypothesis cleanly. (Critic #3)
- **Headline metric = AC9 Recall@1 lift** (≥+2 cases vs `single_agent_sc5`). AC11 supports. (Critic #4)
- **AC11 two-step**: measure baseline first via `scripts/measure_baseline.py`, pin `≥ baseline + 0.10` afterwards. No hard-coded 0.70. (Critic #5)
- **AC10 restated** to `cascade_lift ≥ 1` (cases resolved at top-2/3 that top-1 missed). A1 has early-exit on pass, so Recall@3 ≠ Recall@1+1 by construction. (Critic #6)
- **AC16 dropped.** Dual-log artifact retained as visual evidence; no corpus-level metric on n=10. (Critic #9)
- **Cascade routing corrected**: `fail_revert_ac` → advance_candidate; **post-retry** `fail_error_runtime` → abstain. Runtime errors imply PoC was wrong, not candidate. (Critic #10)
- **Forge-std cache wired BEFORE ablation runs** as foundation prerequisite — `~/.cache/omc/forge-std/` skip-if-present check inside `src/agent/adapters/foundry.py:188-216`. (Critic #8)
- **`scripts/run_smoke.py` and `scripts/measure_baseline.py` are explicit deliverables** (neither exists today). `run_smoke.py` includes `--dry-run-3-cases` projection AND `--max-usd-cost` ceiling. (Critic #7, additional findings)

---

## 2. RALPLAN-DR summary

**Principles (5)**
1. Smoke-set integrity: n=10 hand-tagged `verifier_mode`, ≥1 high + ≥1 medium, ≥3 distinct tags or `SmokeSetInfeasible`.
2. PoC-against-original via `verifier_mode` seam; replace `poc_imports_original` heuristic.
3. Recall@1 (vulnerable-only) is the headline; word "precision" is forbidden in metric module identifiers.
4. Determinism best-effort; arm = compile-time independent runner; cost-gated before any full sweep.
5. Reporting layer (abstain) and verification layer (cascade/reflection/tool-use/RAG) are separable.

**Decision drivers (3)**
1. Capstone-defensibility: "agent finds more bugs than `single_agent_sc5`" on n=10 (AC9).
2. n=10 + ~3 weeks budget: cheapest viable evidence per lever.
3. Reproducibility: smoke set frozen + dual-log + ADR + cost-cap.

**Picks per lever**
- A1 cascade (top-K=3, early-exit on pass; route per Critic #10).
- B2 reflection LOCKED to top-K.
- C3 tool-use as wrapper around analyst (dual-log `analyst_hypothesis_pre_tool` / `_post_tool`).
- D2+D3 evidence-confirmed quality + abstain (abstain = post-processing on `agent-full`).
- E2 RAG default = TF-IDF over `data/dataset/rag_training_dataset.json`; manual patterns deferred.

---

## 3. Revised acceptance criteria (AC1-AC15; AC16 dropped)

- **AC1-AC8** unchanged from iter3 (smoke set sanity, schema, `verifier_mode` seam wired, `classify_verdict` split into `fail_error_compile` / `fail_error_runtime`, pragma 3-branch handler, dual-log artifact, forge-std cache foundation hit).
- **AC9 (HEADLINE) — Recall@1 lift.** `agent-full` Recall@1 on n=10 ≥ `single_agent_sc5` Recall@1 + 2 cases.
- **AC10 — cascade_lift ≥ 1.** `agent-full` resolves ≥1 case at top-2 or top-3 that top-1 missed (counted before early-exit short-circuits later candidates).
- **AC11 (two-step) — confirmed_vulnerability_rate uplift.**
  - Step 1: run `scripts/measure_baseline.py --predictions data/evaluation/single_agent_sc5_predictions.json --smoke-set data/dataset/smoke_set.json` → pin `baseline_cvr` to `data/evaluation/baseline_cvr.txt`.
  - Step 2: assert `agent-full.confirmed_vulnerability_rate ≥ baseline_cvr + 0.10`.
- **AC12** — `no-cascade` Recall@1 ≤ `agent-full` Recall@1 (cascade isolates lift).
- **AC13** — `no-reflection` Recall@1 ≤ `agent-full` Recall@1 (reflection isolates lift).
- **AC14** — `no-rag` Recall@1 ≤ `agent-full` Recall@1 (RAG isolates lift).
- **AC15** — abstain rule applied as post-processing toggle on `agent-full` predictions; emits `agent-full.abstain.json` with `abstained=True/False` per case; documented in `summary.md`.

---

## 4. Implementation outline (ordered; file paths + line refs)

1. **Forge-std cache (foundation prereq).** `src/agent/adapters/foundry.py:188-216` — replace fresh `forge install` with `~/.cache/omc/forge-std/` skip-if-present + symlink/copy into per-case tmpdir.
2. **`classify_verdict` split.** `src/agent/adapters/foundry.py` (verdict classifier) — add `fail_error_compile` vs `fail_error_runtime` branches; update `src/agent/adapters/revert_keywords.yaml` if needed.
3. **State schema additions.** `src/agent/state.py` — add `verifier_mode`, `top_k_candidates`, `analyst_hypothesis_pre_tool`, `analyst_hypothesis_post_tool`, `cascade_trace`, `reflection_trace`, `abstained` to `AuditAnnotations` (TypedDict, `total=False`).
4. **`verifier_mode`-driven seam.** `src/agent/adapters/foundry.py:163-185` — replace `poc_imports_original` heuristic with `case.verifier_mode`-driven gate (`replica_only` / `original_required` / `mirror_pragma`).
5. **Pragma 3-branch.** `src/agent/adapters/foundry.py` (pragma resolver) — mirror `^0.8`; force `replica_only` on pre-0.8; force `0.8.20` on no-pragma.
6. **Cascade router (A1).** `src/agent/graph.py` — top-K=3 candidate iteration; route `pass` → END; `fail_revert_ac` → advance_candidate; **post-retry** `fail_error_runtime` → abstain; `fail_error_compile` → builder retry (≤5).
7. **Reflection node (B2 LOCKED).** `src/agent/nodes/reflector.py` (new) — input = top-K candidates + cascade_trace; output = re-ranked top-K (no new candidates); wire after cascade in `agent-full`.
8. **Tool-use wrapper (C3).** `src/agent/nodes/analyst.py` — wrap analyst call with optional tool-use lane; persist `analyst_hypothesis_pre_tool` and `_post_tool` to state.
9. **RAG default = TF-IDF.** `src/agent/adapters/rag.py` — backend = sklearn TF-IDF over `data/dataset/rag_training_dataset.json`; manual pattern library opt-in via `--rag-mode manual`.
10. **`scripts/run_smoke.py`** (new) — args: `--arms agent-full,no-cascade,no-reflection,no-rag` `--dry-run-3-cases` `--max-usd-cost N`; runs 4×10=40, writes `data/evaluation/{arm}.json` + `summary.md`.
11. **`scripts/measure_baseline.py`** (new) — computes `confirmed_vulnerability_rate` over `single_agent_sc5_predictions.json` on smoke set; writes `data/evaluation/baseline_cvr.txt` (single float).
12. **Ablation orchestration.** `scripts/run_smoke.py --arms ...` with cost gate (dry-run projection + USD ceiling) → 40 runs only after gate passes.

---

## 5. Capstone narrative one-liner

"On 10 hand-tagged Code4rena access-control cases, a 4-lever LangGraph agent (cascade + locked reflection + tool-use + TF-IDF RAG) finds at least 2 more bugs at top-1 than the `single_agent_sc5` baseline, with each lever's contribution isolated by a 4-arm ablation."

---

## 6. ADR snippet

- **Decision:** 4-lever agent (A1 / B2-locked / C3 / D2+D3 / E2-TF-IDF) on n=10 smoke set; 4-arm ablation.
- **Drivers:** capstone-defensibility, n=10 budget, reproducibility.
- **Alternatives considered:** 6-arm ablation (rejected: no-tool-use redundant with dual-log; no-abstain reproducible by post-processing); 5-arm with manual pattern library (deferred to DEF1); Recall@3 ≥ Recall@1+1 (rejected: cascade early-exit invalidates by construction); fixed AC11=0.70 (rejected: baseline unmeasured).
- **Why chosen:** 4 arms isolate the 3 verification levers + RAG; reporting layer separable; cost-gated; AC9 headline directly answers capstone question.
- **Consequences (positive):** smaller sweep (40 runs), faster iteration, dual-log gives qualitative tool-use evidence, abstain toggle is replayable.
- **Consequences (negative):** tool-use lever's quantitative contribution is qualitative-only (visual); manual pattern library deferred; baseline measurement adds 1 prerequisite step.
- **Follow-ups:**
  - **DEF1** — Author ~25 manual access-control patterns and re-run `agent-full` with `--rag-mode manual` to compare against TF-IDF default.
  - **DEF2** — Expand smoke set to n=30 to enable corpus-level `tool_use_changed_top1_rate` (the dropped AC16).
  - **DEF3** — Safe-twin authoring + 70% precision target (carried forward from foundation).

---

## 7. Day 1 / Day 2 / Day 3 ordered task list

### Day 1 — Foundation prerequisites
1. **Wire forge-std cache.** Edit `src/agent/adapters/foundry.py:188-216` to skip-if-present at `~/.cache/omc/forge-std/`. **Done when:** running same case twice; second run logs `forge-std: cache hit` and skips `forge install`.
2. **Split `classify_verdict`.** Add `fail_error_compile` vs `fail_error_runtime` in `src/agent/adapters/foundry.py`. **Done when:** `pytest tests/unit/test_adapters_foundry.py::test_verdict_split` green on ≥2 fixtures (one compile fail, one runtime revert non-AC).
3. **Add state schema fields.** Extend `AuditAnnotations` in `src/agent/state.py`. **Done when:** `python -c "from agent.state import AuditAnnotations; AuditAnnotations(verifier_mode='replica_only', cascade_trace=[])"` does not raise.
4. **Wire `verifier_mode` seam.** Replace `poc_imports_original` in `src/agent/adapters/foundry.py:163-185`. **Done when:** unit test asserts `verifier_mode=replica_only` skips original import; `original_required` requires it; `mirror_pragma` mirrors.
5. **Pragma 3-branch.** Add resolver in `src/agent/adapters/foundry.py`. **Done when:** unit test covers `^0.8` mirror, pre-0.8 forced replica, no-pragma forced 0.8.20.
6. **Hand-tag smoke set.** Author `data/dataset/smoke_set.json` with 10 cases, each `verifier_mode` set, ≥1 high + ≥1 medium, ≥3 distinct tags. **Done when:** `scripts/build_eval_set.py --validate --smoke` passes; otherwise abort with `SmokeSetInfeasible`.
7. **Measure baseline cvr.** Implement and run `scripts/measure_baseline.py`. **Done when:** `data/evaluation/baseline_cvr.txt` exists and contains a float in `[0.0, 1.0]`.

### Day 2 — Levers
8. **Cascade router (A1).** Edit `src/agent/graph.py`. **Done when:** smoke run on 1 case shows `cascade_trace` length ≤3 and route per Critic #10; `fail_error_runtime` post-retry → abstain.
9. **Reflection node (B2 LOCKED).** Create `src/agent/nodes/reflector.py`. **Done when:** unit test asserts output candidate set ⊆ input candidate set (no new candidates).
10. **Tool-use wrapper (C3).** Edit `src/agent/nodes/analyst.py`. **Done when:** smoke run on 1 case writes both `analyst_hypothesis_pre_tool` and `_post_tool` to per-case artifact.
11. **RAG default = TF-IDF.** Edit `src/agent/adapters/rag.py`. **Done when:** `agent-full` smoke run on 1 case logs `rag_mode=tfidf` and retrieves ≥1 doc from `rag_training_dataset.json`.
12. **`scripts/run_smoke.py`.** Implement with `--dry-run-3-cases` + `--max-usd-cost`. **Done when:** `python scripts/run_smoke.py --arms agent-full --dry-run-3-cases` prints projected USD without running full sweep.

### Day 3 — Ablation + report
13. **Cost gate.** `python scripts/run_smoke.py --arms agent-full,no-cascade,no-reflection,no-rag --dry-run-3-cases --max-usd-cost <user-set>`. **Done when:** dry-run projection ≤ ceiling; otherwise abort.
14. **Run 40-case ablation.** Drop `--dry-run-3-cases`. **Done when:** `data/evaluation/{agent-full,no-cascade,no-reflection,no-rag}.json` all populated with 10 entries each.
15. **Apply abstain post-processing.** Generate `data/evaluation/agent-full.abstain.json`. **Done when:** file exists; `abstained` field per case.
16. **Aggregate `summary.md`.** Implement aggregator. **Done when:** `summary.md` contains AC9 Recall@1 lift, AC10 cascade_lift, AC11 two-step (baseline + post-agent), AC12-AC15 ablation deltas, all with file paths to backing artifacts.
17. **Verify ACs.** Run all assertions. **Done when:** AC9-AC15 pass or any failure logged with which arm/case.

---

**File paths summary**
- Plan: `E:\Studying Material\Capstone\agent\.omc\plans\ralplan-iter4-agent-flow-recall.md`
- Companion (existing prior iter): `E:\Studying Material\Capstone\agent\.omc\plans\agent-flow-recall-evidence.md`
- Smoke set (to author): `E:\Studying Material\Capstone\agent\data\dataset\smoke_set.json`
- Baseline pin (to write): `E:\Studying Material\Capstone\agent\data\evaluation\baseline_cvr.txt`
- New scripts: `E:\Studying Material\Capstone\agent\scripts\run_smoke.py`, `E:\Studying Material\Capstone\agent\scripts\measure_baseline.py`
