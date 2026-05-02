# Day-6 Step 0b — Library Audit (AC10a/b/c/d)

Threshold for AC10d (from R2 rule file): **0.400**

## Acceptance results

| AC | Threshold | Observed | Pass? |
|---|---|---|---|
| AC10a coverage | ≥60% | 100% (3/3 families) | YES |
| AC10b function-name leakage (on survivors) | <30% | 19% (3/16) | YES |
| AC10b pre-drop leakage (transparency) | (informational) | 43% (10/23) | n/a |
| AC10c ID overlap (ACF 036-085) | 0 | 0 | YES |
| AC10d Jaccard drops AND n_after≥15 | 15 | 16 survivors (7 drops) | YES |

## AC10d drops (7 cases)

| id | max_jaccard | matched_against |
|---|---|---|
| ACF-096 | 1.000 | ACF-081 |
| ACF-115 | 0.667 | ACF-078 |
| ACF-117 | 0.667 | ACF-078 |
| ACF-116 | 0.545 | ACF-078 |
| ACF-112 | 0.500 | ACF-078 |
| ACF-113 | 0.400 | ACF-078 |
| ACF-118 | 0.400 | ACF-078 |

## Survivors (16 cases)

- ACF-086 (max_jaccard=0.143)
- ACF-088 (max_jaccard=0.318)
- ACF-089 (max_jaccard=0.146)
- ACF-090 (max_jaccard=0.200)
- ACF-094 (max_jaccard=0.117)
- ACF-095 (max_jaccard=0.200)
- ACF-097 (max_jaccard=0.128)
- ACF-098 (max_jaccard=0.128)
- ACF-099 (max_jaccard=0.167)
- ACF-100 (max_jaccard=0.225)
- ACF-104 (max_jaccard=0.121)
- ACF-105 (max_jaccard=0.147)
- ACF-107 (max_jaccard=0.261)
- ACF-108 (max_jaccard=0.108)
- ACF-110 (max_jaccard=0.169)
- ACF-111 (max_jaccard=0.375)

## Decision

**PASS** — proceed to Step 1 (freeze holdout, n_target depends on buildability + AC10d survivor count = 16).
