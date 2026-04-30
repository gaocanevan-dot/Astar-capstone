# Plan — Agent-Flow Centerpiece, Recall + Evidence-Confirmed Quality (Smoke-10)

Mode: SHORT consensus (no pre-mortem). Inherits all foundation items from `consensus-plan-150bad.md` (PoC-against-original, verifier_mode tagging, `classify_verdict` split, pragma 3-branch, `build_smoke_set.py`, forge-std cache). This plan adds levers ON TOP of that scaffolding; it does not replace it.

---

## 1. The architectural story (3-5 sentences)

The system is a **closed-loop multi-step LLM agent** that uses **tool calls (Slither / function-listing) and environment feedback (forge test verdicts)** to converge on **verifier-confirmed access-control findings** against the *original* contract. The agent is the headline: it observes (static facts), hypothesizes (top-3 ranked candidates), acts (writes a Foundry PoC), executes (forge in a real EVM), and **reflects** on the verdict — retrying the builder on `fail_error_runtime`, **escalating to top-2/top-3 candidates** on `fail_revert_ac`, and **abstaining** on `fail_error_compile` over `original` mode. Recall is lifted by *multi-candidate cascade + reflection*, evidence-confirmed quality is lifted by *verifier-gated reporting + abstention*. **RAG is one auxiliary tool among several** — used as a pattern-library lookup that injects an AC-anti-pattern checklist into the analyst, not as the foundation. The story is interview-defensible: this is an agent project (tool-use, multi-step, closed loop with environmental feedback), not a retrieval project.

---

## 2. RALPLAN-DR summary

### Principles (5)
1. **Agent flow is the headline.** Architecture diagram and report intro lead with the closed observe→act→verify→reflect loop, not RAG.
2. **RAG is a tool, not a foundation.** It plugs into one node as a swappable auxiliary; removing it must not break the story.
3. **Precision = evidence-confirmed correctness, not renamed Recall@1.** On a 42/42 vulnerable corpus, the word "precision" stays gated; we report "evidence-confirmed quality" with an explicit denominator.
4. **Honesty over theatre** *(inherited)*. Verifier runs against the *original* contract, `verifier_mode` is hand-tagged, vulnerable-only metrics never use the word "precision."
5. **Smoke-debug cost dominates.** Every lever must be exercisable end-to-end on the 10-case smoke in <30 min wall-clock with caching.

### Decision Drivers (top 3)
1. **Capstone narrative clarity** — the architecture must read as agent-first to a non-RAG-aware committee.
2. **Smoke debug cost** — 10 cases × per-lever ablation must fit in a single working session.
3. **Corpus reality** — 42 vulnerable / 0 safe forbids precision claims; we need an evidence-gated proxy.

### Viable Options per lever

#### Lever A — Multi-candidate verification (recall lever)
- **A1 (PICK)**: sequential cascade with early-exit. Build PoC for `candidates[0]`; if verdict ∈ {`fail_revert_ac`, `fail_error_runtime` after `max_retries`}, advance to `candidates[1]`, then `candidates[2]`. Early-exit on `pass`. Cheap, demoes the loop.
- **A2**: parallel build+verify of all 3, take any `pass`. Rejected: ~3× LLM + forge cost; smoke-budget violation.
- **A3**: only escalate on `fail_revert_ac`. Rejected as default: misses cases where top-1 is right-ish but builder can't compile against it; we'd lose recall to compile flakiness. Kept as a config flag.

#### Lever B — Reflection / self-consistency at the agent level (recall + quality)
- **B1**: keep SC=5 at analyst only. Status quo, no agent-loop story.
- **B2 (PICK)**: post-verifier **reflection node** that re-prompts analyst with `(verdict, error_summary, prior hypothesis)` whenever verdict ∈ {`fail_revert_ac`, `fail_error_runtime`} **and** the cascade is about to advance. The reflection re-ranks `candidates` (may demote `[0]`, promote `[1]`) and may rewrite the hypothesis for the new top. This is the headline agent-loop turn.
- **B3**: ensemble disagreement gate (abstain when SC vote spread < threshold). Rejected as default: adds another knob to tune on 10 cases; revisit post-DEF1.

#### Lever C — Static-analysis tool calls inside the analyst (precision lever)
- **C1**: keep `compact_summary` (all functions) facts dump. Status quo.
- **C2**: switch to `suspicious_summary` filter. Cheap pre-filter, no agent story.
- **C3 (PICK)**: **agentic tool use** — analyst is given two tools: `list_functions(contract)` and `get_function_signature(name)`; emits 1-2 tool calls before producing the JSON hypothesis. Tool transcript is logged to `annotations.tool_trace`. This is the visible "agent" pattern for the report. Implementation: function-calling-style prompt with a small dispatcher in `analyst.py`, NOT a separate framework.

#### Lever D — Verifier-confirmed predictions only (evidence-confirmed quality)
- **D1**: dual-track reporting (raw analyst + verifier-confirmed). Useful but ambiguous as a headline.
- **D2 (PICK)**: report **evidence-confirmed quality** as the headline non-recall metric, with Critic's denominator: `pass / (pass + fail_revert_ac + fail_error_runtime)`. Excludes `fail_error_compile` and `abstain`.
- **D3 (PICK, additive)**: **`abstain` verdict** when verifier returns `fail_error_compile` on `verifier_mode == original` after all retries and all cascade steps — case is unknown, neither positive nor negative. D2 + D3 are complementary, not exclusive.

#### Lever E — RAG as auxiliary (positioning)
- **E1**: few-shot retrieval of past hits (status quo).
- **E2 (PICK)**: **pattern-library retrieval** — RAG store seeded with curated AC anti-patterns / CWE-style snippets (~20-30 entries, hand-authored, not case-derived). Analyst prompt receives "Relevant AC anti-patterns to check" instead of "Similar past cases." This decouples RAG from the labeled corpus and reframes it as a checklist tool.
- **E3**: counter-example retrieval (similar but safe). Rejected for this iteration: requires the safe-twin corpus from DEF1; revisit.
- **E4**: RAG-driven hypothesis schema. Rejected: over-couples the analyst output shape to RAG; bad for the "RAG is auxiliary" story.

### Why only-1-option is not the case
At least 2 options remain alive on every lever. Where options were eliminated, one-line rationale is given inline above.

---

## 3. Recommended picks

- **A1** (sequential cascade, early-exit) — keeps smoke wall-clock bounded and the loop is the story.
- **B2** (reflection node) — the single most agent-flavored addition; demoes "observe verdict, revise plan."
- **C3** (analyst-as-tool-user) — produces a tool-trace artifact that *is* the agent demo for the report.
- **D2 + D3** (evidence-confirmed quality with explicit denominator + abstain on compile-fail) — the only honest precision-shaped metric on a vulnerable-only corpus.
- **E2** (pattern-library RAG) — keeps the RAG seam alive without making RAG the centerpiece, and removes LOO-on-labels coupling.

Justification against drivers: (Driver-1) all picks privilege the agent-loop narrative; RAG is demoted from foundation to one tool node. (Driver-2) cascade is sequential with early-exit, reflection only fires when cascade advances, tool-use adds ≤2 cheap calls — total smoke runtime stays within budget. (Driver-3) D2+D3 are the only honest non-recall metric given the corpus.

---

## 4. Step-by-step implementation outline

### Step 1 — State + verdict surface (foundation hook)
- `src/agent/graph_lg.py:35-75` (`AuditGraphState`): add fields
  - `candidates: list[str]`
  - `candidate_idx: int` (which top-k slot is currently being tried; 0-indexed)
  - `cascade_log: Annotated[list[dict], add]` (one entry per `(idx, verdict, attempts)`)
  - `tool_trace: Annotated[list[dict], add]` (analyst tool-call log)
  - `verifier_mode: str` (from smoke set; threaded through)
  - `abstain: bool`
- `src/agent/adapters/foundry.py:23,47-104`: split `Verdict` into `pass | fail_revert_ac | fail_error_compile | fail_error_runtime` (already required by foundation AC3). The compile-marker branch returns `fail_error_compile`; the trailing `fail_error` branch returns `fail_error_runtime`.

### Step 2 — Multi-candidate cascade (Lever A1)
- `src/agent/nodes/builder.py:95-125` (`build_poc`): add parameter `target_function: str` is already there; **add `candidate_rank: int = 0`** so the prompt can say "this is candidate #N of 3, prior candidates failed because…" using `cascade_log`.
- `src/agent/graph_lg.py`:
  - In `_node_analyst`: write `candidates`, set `candidate_idx=0`, set `target_function = candidates[0]`.
  - New router `_router_cascade_advance(state)`: invoked from the verify-result router when verdict ∈ {`fail_revert_ac`, `fail_error_runtime`-after-max-retries}. If `candidate_idx + 1 < len(candidates)`: increment, reset `poc_attempts=0`, append to `cascade_log`, route to `reflection`. Else: route to `mark_safe` (or `abstain` per Step 4).
  - New node `_node_advance_candidate(state)`: bumps `candidate_idx`, sets `target_function = candidates[idx]`.

### Step 3 — Reflection node (Lever B2)
- New file `src/agent/nodes/reflection.py` with `reflect(state) -> dict` that re-prompts the analyst LLM with `(prior_target, prior_hypothesis, verdict, error_summary, candidates)` and returns `{target_function, hypothesis}` for the new candidate slot. Reflection is OFF the SC=5 path; it is a single deterministic call per cascade-advance.
- `src/agent/graph_lg.py`: add `reflection` node between `advance_candidate` and `builder` on the cascade path. Loop: `verifier → advance_candidate → reflection → builder → verifier`.
- Recursion-limit bump: `run_single_case` config currently `50 + max_retries*3`; change to `60 + max_retries*3 + 3*max_retries*3` (cascade up to 3 candidates × retries × ~3 hops).

### Step 4 — Abstain on compile-fail over original (Lever D3)
- `src/agent/graph_lg.py`: in `_router_verify_result`, when verdict == `fail_error_compile` AND `verifier_mode == "original"` AND `poc_attempts >= max_retries`: route to a new `_node_abstain(state)` that sets `abstain=True`, `finding_confirmed=False`, `finding_reason="abstained: compile-fail on original after retries"`. End. Cascade does NOT advance on compile-fail-over-original (the function-set is intact; the issue is environmental, not analyst-wrong).
- Replicas (`oz_vendored`, `replica_only`) still cascade-advance on compile-fail (we control the replica, fail is on us).

### Step 5 — Analyst as tool-user (Lever C3)
- `src/agent/nodes/analyst.py`: add a small dispatcher loop (max 2 tool calls) using OpenAI function-calling format. Tools:
  - `list_functions(contract_source) -> list[{name, visibility, state_mutability, modifiers}]` — derived from `static_analyzer.analyze(...).functions`.
  - `get_function_body(contract_source, function_name) -> str` — regex slice from source.
- Each tool call appended to `tool_trace`. After ≤2 calls or `tool_choice="none"`, model emits the existing `candidates / target_function / hypothesis / confidence / reasoning` JSON.
- Backward-compat: feature-flagged via `analyst_use_tools: bool = True`. When False, falls back to current `analyze()` exactly.
- Self-consistency (`analyze_consistent`) wraps the tool-using analyst N=5 times unchanged (RRF over `candidates` lists).

### Step 6 — RAG as pattern library (Lever E2)
- New file `src/agent/adapters/rag_patterns.py`: small wrapper that seeds `TfidfRagStore` with `data/patterns/ac_patterns.jsonl` (~25 hand-authored entries: id, title, anti_pattern_solidity, why_dangerous, fix). Format compatible with existing `TfidfRagStore`.
- New file `data/patterns/ac_patterns.jsonl` (curated; ~25 entries; hand-authored — NOT derived from the 42 cases).
- `src/agent/adapters/rag.py`: extend `format_few_shot_context` with a sibling `format_pattern_context(retrieved) -> str` that emits "## Relevant AC anti-patterns to check" (different header so analyst prompt distinguishes).
- `src/agent/graph_lg.py`: `_make_rag_retrieve` accepts a `mode: Literal["few_shot", "pattern_library"] = "pattern_library"` (new default). `few_shot` remains as an ablation knob. `_node_analyst` reads `rag_few_shot` field name unchanged; semantic content is now patterns by default.

### Step 7 — Metrics module (Lever D2)
- New file `src/agent/eval/precision.py`:
  ```python
  def evidence_confirmed_quality(rows) -> dict:
      # denominator: pass + fail_revert_ac + fail_error_runtime
      # numerator: pass
      # report numerator/denominator + raw counts + abstain_rate + compile_fail_rate
      # NEVER call this "precision" in any string the user sees
  ```
- Headline metric helper: `def smoke_summary(rows) -> dict` returning `recall_at_1`, `recall_at_3` (any candidate slot reached `pass`), `evidence_confirmed_quality`, `abstain_rate`, `cascade_activation_rate` (% of cases where idx>0 was tried), `mean_cascade_depth_on_pass`, per-`verifier_mode` breakdown.
- `scripts/run_audit.py` (or current runner — verify path) imports `smoke_summary`, prints the table, also writes `data/results/smoke_<run_id>.json`.

### Step 8 — Smoke runner + ablation arms
- Extend `GRAPH_FACTORIES` in `graph_lg.py` with arms exercised in this iteration on the 10-smoke:
  - `agent-full` = A1+B2+C3+D2+D3+E2 (the headline)
  - `no-cascade` (drop A1)
  - `no-reflection` (drop B2)
  - `no-tool-use` (drop C3, fall back to `compact_summary` dump)
  - `no-rag` (drop E2)
  - `no-abstain` (drop D3, route compile-fails to mark_safe)
- `scripts/run_smoke.py` (new): loops over arms × 10 smoke cases, writes `data/results/smoke_ablation.csv`. Uses forge-std cache from `~/.cache/omc/forge-std/` (foundation AC).

### Step 9 — Tests
- `tests/test_cascade_router.py`: unit-test `_router_cascade_advance` for each verdict combo and idx state.
- `tests/test_classify_verdict.py`: cases covering `fail_error_compile` vs `fail_error_runtime` split.
- `tests/test_reflection_node.py`: deterministic mock LLM, assert reflection re-targets to `candidates[idx+1]` and updates hypothesis.
- `tests/test_analyst_tool_dispatcher.py`: mock function-calling LLM; assert ≤2 tool calls, `tool_trace` populated.
- `tests/test_evidence_confirmed_quality.py`: explicit denominator policy; abstain and compile-fail excluded.
- `tests/test_rag_pattern_mode.py`: pattern-library mode emits "AC anti-patterns" header, not "Similar known-vulnerable cases."

---

## 5. Acceptance criteria (10-case smoke; absolute)

Foundation (inherited; must still hold): AC1 smoke schema with `verifier_mode`; AC2 PoC against original on `original` mode; AC3 `classify_verdict` split; AC4 pragma 3-branch policy; AC5 forge-std cache hit on every case after first; AC6 `build_smoke_set.py` enforces ≥3 distinct `verifier_mode` tags or raises `SmokeSetInfeasible`; AC7+AC8 (vulnerable-only metrics policy, no "precision" word in metric module strings).

New for this iteration (proposed thresholds; user picks before execute):
- **AC9 — Recall@1 lift**: `agent-full` Recall@1 on smoke-10 ≥ baseline `single_agent_sc5` Recall@1 + **2 cases** (i.e. ≥+20pp absolute on n=10). User confirm Δ.
- **AC10 — Recall@3 reach**: `agent-full` Recall@3 (any cascade slot passed) ≥ Recall@1 + **1 case** (cascade actually helped at least once).
- **AC11 — Evidence-confirmed quality**: `agent-full` ≥ **0.70** with the explicit denominator (`pass / (pass + fail_revert_ac + fail_error_runtime)`). User confirm.
- **AC12 — Abstain rate bounded**: `abstain_rate` ≤ **0.30** on smoke-10 (proves abstain isn't a hiding-place for failures).
- **AC13 — Cascade activated**: `cascade_activation_rate > 0` on smoke-10 (proves Lever A is exercised, not dead code).
- **AC14 — Tool-trace non-empty**: ≥ 8/10 cases have `len(tool_trace) ≥ 1` (proves Lever C is exercised).
- **AC15 — Per-lever ablation table emitted**: `data/results/smoke_ablation.csv` has all 6 arms × 10 cases × `recall_at_1, recall_at_3, evidence_confirmed_quality, abstain_rate`.

---

## 6. Verification steps (concrete commands)

```bash
# 0. Foundation reuse
python scripts/build_smoke_set.py --out data/dataset/smoke_set.json
python -c "import json,sys; d=json.load(open('data/dataset/smoke_set.json')); assert len(d)==10; assert len({c['verifier_mode'] for c in d})>=3"

# 1. Unit tests
pytest tests/test_classify_verdict.py tests/test_cascade_router.py tests/test_reflection_node.py tests/test_analyst_tool_dispatcher.py tests/test_evidence_confirmed_quality.py tests/test_rag_pattern_mode.py -q

# 2. Single-arm dry run on 1 smoke case (smoke of the smoke)
python scripts/run_smoke.py --arm agent-full --limit 1 --case-id <pick one>

# 3. Full ablation on smoke-10
python scripts/run_smoke.py --arms agent-full,no-cascade,no-reflection,no-tool-use,no-rag,no-abstain \
  --smoke data/dataset/smoke_set.json --out data/results/smoke_ablation.csv

# 4. Headline summary
python -m agent.eval.precision --rows data/results/smoke_ablation.csv --arm agent-full
# expect: recall_at_1, recall_at_3, evidence_confirmed_quality, abstain_rate, cascade_activation_rate, tool_trace_coverage
```

---

## 7. Open questions (≤3)

1. **AC9 / AC11 thresholds.** I propose Recall@1 lift = +20pp (2 cases on n=10) and evidence-confirmed quality ≥ 0.70. Do you accept these, or want them softer (e.g. +10pp / 0.60) for the first iteration?
2. **Pattern library authoring scope.** ~25 hand-authored entries in `data/patterns/ac_patterns.jsonl` — do you author them yourself (closer to your supervisor's expectations) or should I generate a draft from public sources (SWC, CWE, OZ docs) for you to curate?
3. **Tool-use prompt format.** OpenAI-style function calling vs. a JSON-only "tool intent" emitted by the analyst that we dispatch ourselves. Function calling is cleaner; JSON-intent is portable across providers. Which do you prefer?

---

## 8. Capstone narrative one-liner

"This is a closed-loop multi-step agent for smart-contract access-control auditing — it observes via static-analysis tool calls, hypothesizes top-3 ranked candidates, acts by writing a Foundry PoC, executes it against the *original* contract, and reflects on the verifier's verdict to escalate, retry, or abstain; RAG is one auxiliary tool inside the loop, not the architecture."

---

## ADR

- **Decision**: Adopt agent-flow-centric design with five levers (A1, B2, C3, D2+D3, E2) on top of the foundation plan; keep RAG as a swappable pattern-library tool node.
- **Drivers**: capstone narrative clarity (agent-first), smoke debug cost, vulnerable-only corpus reality.
- **Alternatives considered**: parallel cascade (A2, cost), SC-disagreement abstain (B3, knob-tuning on n=10), `suspicious_summary` filter (C2, no agent story), counter-example RAG (E3, blocked on DEF1 safe-twins), RAG-driven hypothesis schema (E4, over-couples to RAG).
- **Why chosen**: each pick demonstrates an agent-loop behavior (cascade, reflection, tool use, evidence-gated reporting) that is independently visible in artifacts (cascade_log, tool_trace, abstain verdict, ablation table). Removing any single lever yields a directly measurable ablation row.
- **Consequences**: more nodes / more state fields / longer recursion limit; tool-use coupling to OpenAI function-calling (mitigated by Open Question 3); pattern-library authoring effort (~25 entries, ~half-day).
- **Follow-ups**: DEF1 safe-twin authoring unlocks E3 and re-enables literal precision; revisit B3 disagreement-gate after safe-twins; consider promoting cascade to parallel (A2) once smoke budget allows.
