# Day-6 AC10d — Jaccard Threshold Calibration (R1)

**Computed by**: `scripts/calibrate_jaccard.py`
**Holdout pool**: 23 clean unused ACF cases (086..118 minus Day-5b 10)
**Library**: 85 anti_patterns entries

## Distribution of max-Jaccard per holdout case

| bin | range | count |
|---|---|---|
| [0.00, 0.10) | | 0 |
| [0.10, 0.20) | | 10 |
| [0.20, 0.30) | | 4 |
| [0.30, 0.40) | | 2 |
| [0.40, 0.50) | | 2 |
| [0.50, 0.60) | | 2 |
| [0.60, 0.70) | | 2 |
| [0.70, 0.80) | | 0 |
| [0.80, 0.90) | | 0 |
| [0.90, 1.00) | | 1 |

## Statistics

- P50: 0.200
- P75: 0.400
- P90: 0.642
- P95: 0.667
- Min: 0.108
- Max: 1.000
- Natural gap (>=0.10 wide): 0.833

## Hub detection (top-1 match counts)

| library_id | times top-1 | hub? |
|---|---|---|
| ACF-078 | 7 | **YES** |
| C4-229 | 3 | no |
| C4-487 | 2 | no |
| C4-318 | 2 | no |
| ACF-067 | 2 | no |

## Recommended AC10d threshold

**Threshold: 0.400**

Rationale: contamination hub(s) detected ([('ACF-078', 7)]); using max(P75=0.400, 0.40) = 0.400 to catch hub cluster (natural gap 0.8333333333333333 is misleading here)

Cases with max-Jaccard >= threshold are flagged as contaminated
and dropped from the holdout. If drops bring n below 15, escalate
to Path B (per Day-5b stop-rule + Critic minor finding).

## Per-case detail (sorted by max_jaccard descending)

| ACF id | max_jaccard | matched_against | drop? |
|---|---|---|---|
| ACF-096 | 1.000 | ACF-081 | YES |
| ACF-115 | 0.667 | ACF-078 | YES |
| ACF-117 | 0.667 | ACF-078 | YES |
| ACF-116 | 0.545 | ACF-078 | YES |
| ACF-112 | 0.500 | ACF-078 | YES |
| ACF-113 | 0.400 | ACF-078 | YES |
| ACF-118 | 0.400 | ACF-078 | YES |
| ACF-111 | 0.375 | ACF-078 | no |
| ACF-088 | 0.318 | C4-6 | no |
| ACF-107 | 0.261 | C4-229 | no |
| ACF-100 | 0.225 | C4-484 | no |
| ACF-090 | 0.200 | C4-229 | no |
| ACF-095 | 0.200 | C4-229 | no |
| ACF-110 | 0.169 | ACF-067 | no |
| ACF-099 | 0.167 | C4-29 | no |
| ACF-105 | 0.147 | C4-487 | no |
| ACF-089 | 0.146 | C4-54 | no |
| ACF-086 | 0.143 | ACF-065 | no |
| ACF-097 | 0.128 | C4-318 | no |
| ACF-098 | 0.128 | C4-318 | no |
| ACF-104 | 0.121 | ACF-051 | no |
| ACF-094 | 0.117 | C4-487 | no |
| ACF-108 | 0.108 | ACF-067 | no |
