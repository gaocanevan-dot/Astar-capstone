# Function-level Precision & MRR

**Contract-level precision is undefined** on this dataset because all 42 cases
are labeled `vulnerable` (no safe cases → FP has no source).

**Function-level Precision@k** = (correct picks in top-k) / (picks in top-k).
Methods that output <3 candidates per case are NOT unfairly penalized —
denominator uses actual pick count.

**MRR** = mean reciprocal rank of GT within top-3 (0 if GT not in top-3).

| Method | P@1 (41) | P@3 (41) | MRR (41) | P@1 (clean 32) | P@3 (clean 32) | MRR (clean 32) |
|--------|----------|----------|----------|-----------------|-----------------|-----------------|
| Slither baseline | 0.0% (0/0) | 0.0% (0/0) | 0.000 | 0.0% (0/0) | 0.0% (0/0) | 0.000 |
| GPT zero-shot (1-fn prompt) | 65.7% (23/35) | 47.1% (24/51) | 0.573 | 88.5% (23/26) | 58.5% (24/41) | 0.734 |
| GPT zero-shot (top-3 prompt) | 50.0% (16/32) | 39.3% (22/56) | 0.451 | 64.0% (16/25) | 46.7% (21/45) | 0.568 |
| Single-agent (no RAG) | 59.4% (19/32) | 47.2% (25/53) | 0.533 | 70.4% (19/27) | 53.3% (24/45) | 0.667 |
| Single-agent + RAG curated (TF-IDF) | 35.7% (10/28) | 26.9% (14/52) | 0.293 | 45.5% (10/22) | 34.1% (14/41) | 0.375 |
| Single-agent + static (top-k) | 59.4% (19/32) | 47.3% (26/55) | 0.541 | 65.4% (17/26) | 52.3% (23/44) | 0.620 |
| Single-agent + static (FILTERED) | 62.5% (20/32) | 50.0% (25/50) | 0.545 | 69.2% (18/26) | 52.5% (21/40) | 0.609 |
| Single-agent SC=5 ⭐ | 54.1% (20/37) | 36.6% (26/71) | 0.557 | 69.0% (20/29) | 47.2% (25/53) | 0.698 |
| Single-agent SC=5 + Embedding RAG 🆕 | 54.5% (18/33) | 30.1% (22/73) | 0.484 | 69.2% (18/26) | 39.3% (22/56) | 0.620 |
| Full pipeline (no RAG) | 51.5% (17/33) | 51.5% (17/33) | 0.415 | 63.0% (17/27) | 63.0% (17/27) | 0.531 |