# Open Questions

## agent-flow-recall-evidence — 2026-04-28
- [ ] AC9 / AC11 thresholds — accept Recall@1 lift = +20pp (2/10) and evidence-confirmed quality >=0.70, or soften to +10pp / 0.60 for first iteration? — Sets the bar for whether the smoke run "passes"; too tight may force premature tuning, too loose hides regressions.
- [ ] Pattern-library authoring scope — user hand-authors ~25 `data/patterns/ac_patterns.jsonl` entries, or planner drafts from SWC/CWE/OZ docs for user to curate? — Affects whether RAG content is defensible as supervisor-original work and the iteration's wall-clock budget (~half-day either way).
- [ ] Tool-use prompt format — OpenAI function-calling vs. JSON-intent dispatched by us? — Function-calling is cleaner and produces cleaner `tool_trace`; JSON-intent is provider-portable. Determines `analyst.py` dispatcher shape.

## ralplan-iter4-agent-flow-recall — 2026-04-28
- [ ] `--max-usd-cost` ceiling value — user must pin a USD ceiling for `scripts/run_smoke.py` cost gate before 40-run sweep. — Without this, dry-run projection has nothing to compare against and the cost gate is inert.
- [ ] DEF1 manual pattern library — defer ~25 hand-authored AC patterns to follow-up iteration, or block iter4 on it? — TF-IDF default unblocks iter4; manual patterns become a comparison study (DEF1).
- [ ] Tool-use prompt format (carried) — still unresolved; needed before Day 2 task #10. — Determines `src/agent/nodes/analyst.py` wrapper shape.
- [ ] AC11 baseline-pin acceptance — user accepts `baseline + 0.10` as the AC11 bar after baseline is measured, regardless of measured value? — If measured baseline is already high (>0.85), `+0.10` may be infeasible on n=10 and AC11 needs a soft cap.
