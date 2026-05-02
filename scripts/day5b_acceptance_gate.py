#!/usr/bin/env python3
"""Day-5b mechanical acceptance gate (Critic R4 + Architect R4 spirit).

Reads the 3 per-arm sweep aggregates and emits a binary verdict:
- exit 0 → ship `.omc/plans/day-5b-honest-framing.md` as the headline narrative
- exit non-zero → ship `.omc/plans/day-D-pivot.md` as pivot narrative

Acceptance bar (pre-committed in narratives):
- At least ONE of {5b-tool, 5b-mandate} reaches `pass_count >= 5/10`
- AC1 (self-terminate OR system-clean-cascade) ≥ 7/10 in the same arm
- Sum of all 3 arms' cost ≤ $0.70 (Critic ceiling)

Auto-prints which narrative ships + the per-arm scoreboard. Has no
discretionary path — the threshold is binary.

For full automation, wrap this in a shell script that calls
`git checkout -- src/agent/react/{loop,tools,prompts}.py` on non-zero
exit (but per Critic's pragmatism, the verbal commitment + the gate's
non-zero exit code is sufficient for capstone scope; not wiring git
revert.)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _arm_metrics(sweep_path: Path) -> dict | None:
    if not sweep_path.exists():
        return None
    sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
    records = sweep.get("records") or []
    n = len(records)
    if n == 0:
        return None
    n_pass = sum(1 for r in records if r.get("finding_confirmed"))
    n_self_term = sum(
        1 for r in records
        if r.get("terminal_reason") in (
            "submit_finding", "give_up", "system_cascade_pass", "system_cascade_then_give_up"
        )
    )
    n_recall_hit = sum(1 for r in records if r.get("recall_hit"))
    avg_distinct = sum(r.get("distinct_tool_count", 0) for r in records) / n
    cost = sum(r.get("case_usd", 0.0) for r in records)
    n_cascade_fired = sum(1 for r in records if r.get("cascade_invocations", 0) > 0)
    n_system_forced = sum(1 for r in records if r.get("cascade_was_system_forced"))
    return {
        "n": n,
        "pass": n_pass,
        "self_term": n_self_term,
        "recall_hit": n_recall_hit,
        "avg_distinct_tools": round(avg_distinct, 2),
        "cost": round(cost, 4),
        "cascade_fired": n_cascade_fired,
        "system_forced": n_system_forced,
    }


def main() -> int:
    REPO_ROOT = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--baseline-json",
        default=str(REPO_ROOT / "data" / "evaluation" / "react_5b_5-baseline.json"),
    )
    ap.add_argument(
        "--tool-json",
        default=str(REPO_ROOT / "data" / "evaluation" / "react_5b_5b-tool.json"),
    )
    ap.add_argument(
        "--mandate-json",
        default=str(REPO_ROOT / "data" / "evaluation" / "react_5b_5b-mandate.json"),
    )
    ap.add_argument("--pass-threshold", type=int, default=5)
    ap.add_argument("--ac1-threshold", type=int, default=7)
    ap.add_argument("--cost-cap", type=float, default=0.70)
    ap.add_argument(
        "--out",
        default=str(REPO_ROOT / "data" / "evaluation" / "day5b_gate_verdict.md"),
    )
    args = ap.parse_args()

    arms = {
        "5-baseline": _arm_metrics(Path(args.baseline_json)),
        "5b-tool": _arm_metrics(Path(args.tool_json)),
        "5b-mandate": _arm_metrics(Path(args.mandate_json)),
    }

    missing = [k for k, v in arms.items() if v is None]
    if missing:
        print(f"ERROR: missing arms (sweep didn't run or empty): {missing}",
              file=sys.stderr)
        return 1

    total_cost = sum(a["cost"] for a in arms.values())

    # Bar 1: cost
    cost_pass = total_cost <= args.cost_cap

    # Bar 2: at least one of {5b-tool, 5b-mandate} has pass ≥ threshold AND AC1 ≥ threshold
    winning_arms = []
    for name in ("5b-tool", "5b-mandate"):
        a = arms[name]
        if a["pass"] >= args.pass_threshold and a["self_term"] >= args.ac1_threshold:
            winning_arms.append(name)
    bar2_pass = len(winning_arms) > 0

    overall_pass = cost_pass and bar2_pass
    chosen_narrative = (
        ".omc/plans/day-5b-honest-framing.md" if overall_pass
        else ".omc/plans/day-D-pivot.md"
    )

    # ---- Render verdict ----
    lines = [
        "# Day-5b Acceptance Gate Verdict",
        "",
        f"**Decision: {'SHIP day-5b-honest-framing.md' if overall_pass else 'SHIP day-D-pivot.md'}**",
        "",
        f"Total cost across 3 arms: **${total_cost:.4f}** (cap: ${args.cost_cap}) "
        f"→ {'✅' if cost_pass else '❌'}",
        "",
        f"Lift criterion: at least one of (5b-tool, 5b-mandate) has "
        f"`pass ≥ {args.pass_threshold}` AND `self_term ≥ {args.ac1_threshold}`",
        f"  Winning arms: {winning_arms or '(none — pivot)'}",
        f"  → {'✅' if bar2_pass else '❌'}",
        "",
        "## Per-arm scoreboard",
        "",
        "| Arm | n | pass | self_term | recall@1 | tools/case | cascade_fired | sys_forced | cost |",
        "|-----|---|------|-----------|----------|------------|---------------|------------|------|",
    ]
    for name in ("5-baseline", "5b-tool", "5b-mandate"):
        a = arms[name]
        lines.append(
            f"| {name} | {a['n']} | {a['pass']} | {a['self_term']} | "
            f"{a['recall_hit']} | {a['avg_distinct_tools']} | "
            f"{a['cascade_fired']} | {a['system_forced']} | ${a['cost']:.4f} |"
        )
    lines.append("")
    lines.append(f"## Chosen narrative: `{chosen_narrative}`")
    lines.append("")
    lines.append("**This is the LAST post-hoc round on n=10.** No further "
                 "architecture changes on this smoke set without a fresh "
                 "held-out corpus.")
    lines.append("")

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")

    # ---- Console digest ----
    print("\n" + "=" * 70)
    print(f"  Day-5b Acceptance Gate")
    print(f"  Total cost: ${total_cost:.4f}  Cost gate: {'✅' if cost_pass else '❌'}")
    for name in ("5-baseline", "5b-tool", "5b-mandate"):
        a = arms[name]
        marker = "✅" if name in winning_arms else ("—" if name == "5-baseline" else "❌")
        print(f"  {marker} {name:14s} pass={a['pass']}/{a['n']}  self_term={a['self_term']}  "
              f"cascade={a['cascade_fired']}  ${a['cost']:.4f}")
    print()
    print(f"  Decision: SHIP {chosen_narrative}")
    print(f"  Verdict written → {args.out}")
    return 0 if overall_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
