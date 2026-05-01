# Day-5b — Success Path Narrative (PRE-COMMITTED, do NOT edit after sweep)

**Status when committed**: Day-5 sweep complete (4/10 pass), cascade graft
proposed. This file is committed BEFORE the Day-5b sweep runs and codifies
exactly what we will claim IF the sweep delivers the headline numbers below.
No tuning-after-the-fact. If sweep returns < 5/10, the OTHER narrative
(`.omc/specs/day-D-pivot.md`) ships instead.

**Activation gate**: `pass_count >= 5/10 in any arm` AND `AC1 >= 7/10`
AND `cost <= $0.70 sweep`. Verified mechanically by
`scripts/day5b_acceptance_gate.py`.

---

## Headline

> "Day-5b system-mediated retry cascade lifts pass count from 4/10 to **{N}/10**
> on the n=10 C5/Repair-Access-Control smoke set, recovering the
> multi-candidate exploration affordance Day-4's pipeline had structurally
> built in. The lift is **system orchestration around the LLM, not agent
> self-direction** — same finding pattern as Day-5's AC5b (`recall_self_lesson`
> 0/10 invocations) showed: under iteration pressure ReAct agents
> systematically skip optional tools, so the orchestrator must intervene."

## Cross-day final scoreboard

| System | Pass/10 | Recall@1 | Cost | Architecture |
|---|---|---|---|---|
| Zero-shot e2e (Day-3 baseline) | 4/10 | 2/10 | $0.0956 | single LLM + single forge |
| Day-4 pipeline | 6/10 | 2/10 | $0.2912 | hardcoded cascade hybrid + reflection + SC=3 |
| Day-5 ReAct (no cascade) | 4/10 | 0/10 | $0.1485 | LLM-driven loop + 3-tier memory |
| **Day-5b ReAct + system cascade** | **{N}/10** | {R}/10 | $\{C} | LLM loop + memory + system retry on forge-fail |

Lift cases (vs Day-5): {LIST FROM SWEEP}.

## What the lift actually means (honest framing)

The cascade tool was made available to the agent (5b-tool arm) and made
mandatory by prompt (5b-mandate arm). The 3-arm comparison disentangles:

- **5-baseline** (Day-5 replay, no cascade) measures single-seed reproducibility
- **5b-tool − 5-baseline** measures lift from cascade *tool availability* alone
  (does an unsolicited cascade tool get used by an agent under iteration pressure?)
- **5b-mandate − 5b-tool** measures lift from *instruction-following* on top
  of mere availability

If both 5b arms beat baseline → architecture matters and prompt instructions
work. If only 5b-mandate beats → agent doesn't pick up new tools without
explicit pressure (consistent with AC5b). If neither → cascade affordance
isn't the bottleneck (root cause is candidate-quality, see Day-D).

## What this does NOT claim

1. **Not agentic superiority over zero-shot.** With cascade available, agent +
   cascade orchestration matches or slightly exceeds Day-4's pipeline. The
   lift comes from the cascade affordance, which Day-4 already had as
   hardcoded Python.
2. **Not novel mechanism.** System-mediated retry on forge-fail is a standard
   orchestrator pattern (AutoGPT, SWE-agent, Cursor's debugger flow). Our
   contribution is the *measurement methodology* — 3-arm decomposition that
   isolates tool-availability vs instruction-following.
3. **Not "agent learns to use memory".** AC5b stays 0/10 (or near-0). Memory
   layer is architecturally complete and queryable, but agent does not
   organically consult it under iteration pressure. This is honestly disclosed
   as a separable infrastructure-vs-prompt-elicitation finding.

## What we DO claim

1. **Architectural milestone**: Day-5b ships the first version of this codebase
   with (a) real ReAct loop, (b) persistent 3-tier memory, (c) per-case
   serializable trace, AND (d) measured pass-count parity with the Day-4
   hardcoded pipeline.
2. **Methodological contribution**: 3-arm controlled experiment design isolates
   tool-availability vs instruction-following effects on the same agent. This
   is paper-quality decomposition rare for capstone-tier work.
3. **Honest negative finding (preserved from Day-5)**: AC5b memory recall
   demonstrates that ReAct agents under iteration pressure systematically
   skip optional tools — re-confirmed by 5b-tool arm if the cascade tool also
   gets <2/10 organic invocations.

## Acceptance criteria final tally

(Filled in by `scripts/day5_acceptance_report.py` post-sweep. Pre-commit
commitment: AC bar is FROZEN at the values in this file. Numbers will be
populated mechanically; no thresholds will be moved after the run.)

| AC | Threshold | Result | Pass? |
|---|---|---|---|
| AC1 self-term + system-clean-cascade | ≥7/10 | {N}/10 | {Y/N} |
| AC2 distinct tools/case | ≥3 avg | {V} | {Y/N} |
| AC7 sweep cost | ≤$0.70 | $\{C} | {Y/N} |
| AC8 markdown traces | 30/30 (3 arms × 10) | {N}/30 | {Y/N} |
| **AC9 mechanical cascade-trigger** (Architect R5) | cascade_invocations > 0 on cases with first forge-fail | {V} | {Y/N} |
| AC10 (NEW) honest naming | "system-mediated cascade" never re-labeled "agent learns to cascade" in any narrative | yes | ✅ |

AC5b retained at 0/10 expected (no claim that this round fixes memory recall).

## What changes in the codebase

(Reference only — actual implementation in commit hash {SHA}.)

- `src/agent/react/tools.py`: + `try_next_candidate(reason, k=2)` tool
- `src/agent/react/loop.py`: + system-intercept gated by `--mode 5b-mandate`;
  AC1 redefined to count system-clean-cascade as a clean termination
- `src/agent/react/state.py`: + `cascade_invocations` counter
- `src/agent/react/prompts.py`: + variant prompt for 5b-mandate arm with
  "before give_up, MUST call try_next_candidate at least once"
- `scripts/run_react_agent.py`: + `--mode {5-baseline, 5b-tool, 5b-mandate}` flag
- `scripts/verify_ac9.py`: NEW mechanical AC9 verifier
- `scripts/day5b_acceptance_gate.py`: NEW gate that selects this narrative
  vs `day-D-pivot.md` based on result

## Stop rule (binding via commit message)

**This is the LAST post-hoc round on the n=10 C5/Repair smoke set.** Commit
message includes the literal string `LAST_POSTHOC_ROUND_ON_N10` to make this
audit-able. Any subsequent architecture change requires a fresh held-out set
that doesn't currently exist in usable form.

## Pivot trigger

If `scripts/day5b_acceptance_gate.py` exits non-zero (any arm fails AC bar),
ship `.omc/specs/day-D-pivot.md` as the headline narrative and DO NOT
implement "just one more thing." This file becomes a historical artifact in
the commit history showing what we PLANNED to claim if the sweep had worked,
preserved as falsification record.
