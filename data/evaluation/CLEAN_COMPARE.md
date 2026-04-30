# Clean-vs-Full Comparison

Dirty labels excluded from CLEAN: `unknown_function`, `setUp`, `testExploit`, `testMisleadingGetAddress`.
Empty-GT cases (GRA-H-01) already excluded by `evaluable` filter.

| Method | hit@1 (full 41) | hit@3 (full 41) | hit@1 (clean 32) | hit@3 (clean 32) |
|--------|------------------|------------------|-------------------|-------------------|
| Slither baseline | 0.0% (0/41) | 0.0% (0/41) | 0.0% (0/32) | 0.0% (0/32) |
| GPT zero-shot (1-fn prompt) | 56.1% (23/41) | 58.5% (24/41) | 71.9% (23/32) | 75.0% (24/32) |
| GPT zero-shot (top-3 prompt) | 39.0% (16/41) | 53.7% (22/41) | 50.0% (16/32) | 65.6% (21/32) |
| Single-agent (no RAG) | 46.3% (19/41) | 61.0% (25/41) | 59.4% (19/32) | 75.0% (24/32) |
| Single-agent + RAG curated | 24.4% (10/41) | 34.1% (14/41) | 31.2% (10/32) | 43.8% (14/32) |
| Single-agent + static (top-k) | 46.3% (19/41) | 63.4% (26/41) | 53.1% (17/32) | 71.9% (23/32) |
| Single-agent + static (FILTERED) ⭐ | 48.8% (20/41) | 61.0% (25/41) | 56.2% (18/32) | 65.6% (21/32) |
| Single-agent SC=5 (self-consistency) ⭐ | 48.8% (20/41) | 63.4% (26/41) | 62.5% (20/32) | 78.1% (25/32) |
| Single-agent SC=5 + Embedding RAG 🆕 | 43.9% (18/41) | 53.7% (22/41) | 56.2% (18/32) | 68.8% (22/32) |
| Full pipeline (no RAG) | 41.5% (17/41) | 41.5% (17/41) | 53.1% (17/32) | 53.1% (17/32) |
| Full pipeline + RAG curated | (missing) | (missing) | (missing) | (missing) |