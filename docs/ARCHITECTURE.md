# Architecture — Single-Agent Variant (v0.3.0-dev)

This document describes the **single-agent** variant of the access-control
vulnerability framework. This is an early feasibility check — a deliberate
reduction of the full LangGraph design in `.omc/plans/consensus-plan-150bad.md`.

## Why single-agent?

The full plan specifies a three-node LangGraph (Analyst → Builder → Verifier)
with conditional retry edges and four ablation arms. That's ~3 weeks of work.
Before building it, we wanted to answer a simpler question:

> **Can a one-shot LLM call on raw Solidity source even identify the
> vulnerable function above chance?**

If yes, the full pipeline's RAG + static analysis + PoC verification adds
measurable value. If no, the problem is upstream (prompting, model choice).

The single-agent variant answers this question on the 42 real Code4rena cases
currently in `data/dataset/eval_set.json`.

## Components implemented (this session)

| Module | Role |
|---|---|
| `src/agent/state.py` | `AuditCore` (10 fields per framework.md §4.1) + `AuditAnnotations` (implementation-level metadata). Both TypedDict; annotations uses `total=False` with explicit field names rather than `Dict[str, Any]`. |
| `src/agent/adapters/llm.py` | OpenAI wrapper. Reads `OPENAI_MODEL` from `.env` (defaults to `gpt-4o-mini`). Detects reasoning-family models (gpt-5, o-series) and strips `temperature`+`seed`. Falls back to `FALLBACK_MODEL` on `model_not_found`. Logs `system_fingerprint`, `tokens_prompt`, `tokens_completion`, `llm_calls`, `wall_clock_seconds` into the caller's `AuditAnnotations`. |
| `src/agent/nodes/analyst.py` | One-shot analyst. System prompt = access-control auditor role. User prompt = contract source (truncated at 20k chars). Response must be JSON with `target_function`, `hypothesis`, `confidence`, `reasoning`. Defensive JSON parsing handles unfenced / fenced outputs. |
| `src/agent/eval/metrics.py` | `compute_analyst_recall(predictions) -> AnalystRecall` with two flavors: strict (exact match on `vulnerable_function`) and loose (case-insensitive contiguous substring). Ignores cases with empty ground truth. |
| `scripts/run_single_agent.py` | Driver: loops `eval_set.json`, calls analyst per case, aggregates metrics, writes `data/evaluation/single_agent_predictions.json` + `data/evaluation/single_agent_summary.md`. |

## Flow

```text
eval_set.json (42 cases, Code4rena access-control findings)
         │
         ▼
┌────────────────────────┐
│ run_single_agent.py    │
│  for each case:        │
│    if empty source →   │
│      skip              │
│    else →              │
│      analyst.analyze() │
└────────────┬───────────┘
             │
             ▼
┌────────────────────────┐
│ analyst.analyze()      │
│  1. build system +     │
│     user prompt from   │
│     raw source         │
│  2. llm.invoke_json()  │
│  3. parse JSON →       │
│     {target_function,  │
│      hypothesis, ...}  │
│  4. update annotations │
└────────────┬───────────┘
             │
             ▼
┌────────────────────────┐
│ metrics.py             │
│  compute Recall across │
│  42 cases (strict +    │
│  loose)                │
└────────────┬───────────┘
             │
             ▼
 single_agent_summary.md
 single_agent_predictions.json
```

No builder, no verifier, no Foundry, no RAG, no static analysis. **By design**
for the feasibility check.

## What's NOT here (but will be when full variant activates)

| Component | Source story | When |
|---|---|---|
| Slither + regex static facts in analyst prompt | US-007 | Full-graph session |
| Chroma RAG few-shot over dev-only corpus with LOO | US-008 | Full-graph session |
| Foundry `.t.sol` PoC generator (Builder) | US-011 | Full-graph session |
| `forge test` verdict classifier (Verifier) with OZ v5 / custom-error fixtures | US-006 + US-012 | Full-graph session |
| 4 compile-time distinct graphs (full / no-static / no-rag / no-verify-loop) | US-013 + US-014 | Full-graph session |
| Slither + GPT-4 zero-shot baselines | US-015 | After full-graph works |
| Precision + F1 (requires safe cases) | — | After US-003 safe-case construction |
| Dev/test split + bootstrap CI | — | After harvesting reaches ~200 cases |

## Model pinning honesty

Per plan §2 P5 ("determinism best-effort, fingerprint-tracked"):

- `.env` pins `OPENAI_MODEL` (currently `gpt-5-mini`, user's project doesn't
  have access → runtime fallback to `gpt-4o-mini`).
- Every prediction record stores `system_fingerprint` at call time so runs are
  auditable even if the fingerprint drifts.
- `temperature=0.1, seed=42` are passed when the model accepts them; silently
  omitted for gpt-5 / o-series.

The paper should quote both the requested snapshot and the observed
fingerprint, with a footnote that reproducibility is modulo provider drift.

## How to reproduce

```bash
# From repo root:
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/run_single_agent.py
# or 5-case smoke:
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/run_single_agent.py --limit 5
# schema-only dry run (no LLM cost):
venv/Scripts/python.exe scripts/run_single_agent.py --dry-run
```

Outputs land in `data/evaluation/single_agent_*`.

## Unit tests

```bash
venv/Scripts/python.exe -m pytest tests/unit/ -v
```

Covers:
- `test_state.py` — AuditCore 10-field contract, AuditAnnotations optional fields
- `test_metrics.py` — Recall edge cases (empty preds, missing GT, strict vs loose, exact substring semantics)
- `test_nodes_analyst.py` — JSON parse fallbacks, source truncation, confidence coercion, LLM mocked end-to-end

23 tests, all pass (as of this session).
