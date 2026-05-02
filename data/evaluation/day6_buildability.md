# Day-6 Step 0a — Blind Buildability Pre-Screen

Per blind-screen rule: count-only artifact. Per-ID results NOT logged.

## Result

```json
{
  "screened_at_start": "2026-05-02T16:03:45Z",
  "screened_at_finish": "2026-05-02T16:04:25Z",
  "candidates_total": 23,
  "buildable_count": 5
}
```

## Preliminary n routing (PENDING AC10d at Step 0b)

The final routing decision is made at Step 1 (freeze holdout)
after Step 0b reports AC10d Jaccard-survivor count. Effective
candidate count = min(buildable_count, ac10d_survivor_count).

buildable=5 < 18 → **PATH B ESCALATION** (Step 0c spot-check)

Preliminary decision: `pathB`
