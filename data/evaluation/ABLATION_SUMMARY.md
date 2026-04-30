# Ablation Summary (RAG on/off + baselines)

Dataset: 42-case Code4rena access-control bad cases (2 empty-source, 40 evaluable).

## Main results

| Method | N | Flagged | Func-Recall (strict) | Func-Recall (loose) | PoC-pass | Retries | LLM calls | Tokens |
|--------|---|---------|----------------------|---------------------|----------|---------|-----------|--------|
| Slither (baseline) | 42 | 0/42 (0.0%) | 0/41 (0.0%) | 0/41 (0.0%) | - | - | 0 | 0 |
| GPT-X zero-shot (baseline) | 42 | 35/42 (83.3%) | 23/41 (56.1%) | 23/41 (56.1%) | - | - | 40 | 50201 |
| Single-agent analyst (no RAG) | 42 | - | 19/41 (46.3%) | 19/41 (46.3%) | - | - | 40 | 69242 |
| Single-agent + RAG (self-hits) | *missing:* `single_agent_rag_predictions.json` | | | | | | | |
| Single-agent + RAG (curated 85 docs) | 42 | - | 10/41 (24.4%) | 15/41 (36.6%) | - | - | 40 | 76202 |
| Full pipeline (no RAG) | 42 | 34/42 (81.0%) | 17/41 (41.5%) | 18/41 (43.9%) | 34/42 (81.0%) | 4 | 78 | 182079 |
| Full pipeline + RAG (self-hits) | *missing:* `full_pipeline_rag_predictions.json` | | | | | | | |
| Full pipeline + RAG (curated 85 docs) | *missing:* `full_pipeline_ragcur_predictions.json` | | | | | | | |

## Pipeline-row breakdown (verdict distribution)

| Method | pass | fail_revert_ac | fail_error | skipped |
|--------|------|----------------|------------|---------|
| Full pipeline (no RAG) | 34 | 0 | 0 | 8 |

## Notes

- Dataset currently has **42 unique cases** (per US-002 dedup finding), below the plan target of 150. Numbers here are feasibility signals, not statistical claims.
- All dataset cases are labeled vulnerable → Precision/F1 require safe cases (US-003, deferred). Current table reports Recall-side metrics only.
- "Flagged" for pipeline rows = cases where forge confirmed the PoC (`execution_result == pass`). For baselines it is the raw contract-level flag.
- Static analyzer (US-007) is written but intentionally excluded from ablation per user direction — only RAG on/off is ablated this round.