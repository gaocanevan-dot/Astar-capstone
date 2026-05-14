# Ablation Sweep Summary

- Cumulative cost (estimated): $3.773
- Total elapsed: 34067s
- Arms: ['A1', 'A2', 'A3', 'A4']

## Per-arm headline metrics

| arm | N | strict R@1 | loose R@1 | hit@3 | PoC-pass | phantom-pass | error | $/case |
|---|---|---|---|---|---|---|---|---|
| A1 | 172 | 74/171 (43%) | 78/171 (46%) | 101/171 (59%) | 143/172 (83%) | 72/172 (42%) | 1/172 | $0.0102 |
| A2 | 172 | 73/171 (43%) | 76/171 (44%) | 73/171 (43%) | 134/172 (78%) | 70/172 (41%) | 2/172 | $0.0093 |
| A3 | 172 | 72/171 (42%) | 75/171 (44%) | 92/171 (54%) | 149/172 (87%) | 77/172 (45%) | 0/172 | $0.0037 |
| A4 | 172 | 0/171 (0%) | 0/171 (0%) | 0/171 (0%) | 0/172 (0%) | 0/172 (0%) | 172/172 | $0.0000 |

## Notes
- evaluable = cases where ground_truth_function is non-empty and != 'Unknown'
- strict R@1: predicted == GT (exact)
- loose R@1: case-insensitive substring match either direction
- hit@3: GT appears in top-3 candidates (strict)
- PoC-pass: forge verdict='pass' (A1/A2) or `flagged=True` (A3/A4)
- phantom-pass: PoC-pass but pred != GT (inline-replica self-attack)