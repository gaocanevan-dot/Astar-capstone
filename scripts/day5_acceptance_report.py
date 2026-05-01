#!/usr/bin/env python3
"""Day-5 — final acceptance report + R7 fallback decision tree.

Reads the sweep aggregate JSON, evaluates AC1-AC8 (Q3-aware bar with
AC6 dropped per Critic), and emits:
- A boolean PASS/FAIL per AC
- An overall Q3 demo verdict ("ship as primary" vs "ship via R7 fallback")
- A capstone-ready summary block (markdown)

Q3 working demo = AC1 (≥7/10 self-term) AND AC2 (≥3 distinct tools/case)
                  AND AC8 (per-case markdown trace).

R7 fallback triggers if:
  - AC1 < 7/10 (self-termination broken), OR
  - AC2 < 3 (tool diversity collapsed), OR
  - AC7 budget breached (>$2.50)
In any of those, demo presents Day-4 pipeline (smoke_agent-full.json) as
primary and ReAct artifact as comparison/prototype only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Windows console (cp936/GBK) can't render ✅/❌; force UTF-8 if available.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    REPO_ROOT = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--sweep-json",
        default=str(REPO_ROOT / "data" / "evaluation" / "react_sweep_run1.json"),
    )
    ap.add_argument(
        "--day4-baseline",
        default=str(REPO_ROOT / "data" / "evaluation" / "smoke_agent-full.json"),
    )
    ap.add_argument(
        "--zero-shot-baseline",
        default=str(REPO_ROOT / "data" / "evaluation" / "smoke_gpt-zeroshot-e2e.json"),
    )
    ap.add_argument(
        "--out",
        default=str(REPO_ROOT / "data" / "evaluation" / "day5_acceptance_report.md"),
    )
    ap.add_argument("--ac1-threshold", type=int, default=7)
    ap.add_argument("--ac2-threshold", type=float, default=3.0)
    ap.add_argument("--ac5b-threshold", type=int, default=2)
    ap.add_argument("--ac7-cost-cap", type=float, default=2.50)
    args = ap.parse_args()

    sweep_path = Path(args.sweep_json)
    if not sweep_path.exists():
        print(f"ERROR: sweep file not found: {sweep_path}", file=sys.stderr)
        return 1

    sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
    records = sweep.get("records") or []
    n_cases = len(records)
    if n_cases == 0:
        print("ERROR: no cases in sweep JSON", file=sys.stderr)
        return 1

    # ---- Compute AC verdicts ----
    n_self_term = sum(1 for r in records if r.get("self_terminated"))
    avg_distinct = sum(r.get("distinct_tool_count", 0) for r in records) / n_cases
    n_episodic_lessons = sum(
        1 for r in records if r.get("terminal_reason") in ("submit_finding", "give_up")
    )
    n_recall_nonempty_cases = sum(
        1 for r in records if r.get("recall_self_lesson_nonempty", 0) > 0
    )
    total_usd = (
        sweep.get("summary", {}).get("running_usd")
        or sum(r.get("case_usd", 0.0) for r in records)
    )
    traces_dir = Path(args.sweep_json).parent / "react_traces"
    n_trace_md = (
        len(list(traces_dir.glob("*_trace.md"))) if traces_dir.exists() else 0
    )

    n_pass = sum(1 for r in records if r.get("finding_confirmed"))
    n_recall_hit = sum(1 for r in records if r.get("recall_hit"))

    ac_verdicts = {
        "AC1_self_terminate": (
            n_self_term >= args.ac1_threshold,
            f"{n_self_term}/{n_cases} (need >={args.ac1_threshold})",
        ),
        "AC2_distinct_tools": (
            avg_distinct >= args.ac2_threshold,
            f"avg {avg_distinct:.2f} (need >={args.ac2_threshold})",
        ),
        "AC3_episodic_lessons": (
            n_episodic_lessons >= max(int(n_cases * 0.7), 1),
            f"{n_episodic_lessons}/{n_cases} (≥70%)",
        ),
        "AC4_unique_lessons": (
            True,  # depends on memory state — informational
            "deferred to memory store inspection",
        ),
        "AC5b_recall_nonempty": (
            n_recall_nonempty_cases >= args.ac5b_threshold,
            f"{n_recall_nonempty_cases}/{n_cases} (need >={args.ac5b_threshold})",
        ),
        "AC7_budget": (
            total_usd <= args.ac7_cost_cap,
            f"${total_usd:.4f} <= ${args.ac7_cost_cap}",
        ),
        "AC8_traces": (
            n_trace_md >= n_cases,
            f"{n_trace_md}/{n_cases} markdown traces",
        ),
    }

    # ---- Q3 demo verdict (R7 fallback decision) ----
    q3_blockers: list[str] = []
    if not ac_verdicts["AC1_self_terminate"][0]:
        q3_blockers.append("AC1 (self-termination)")
    if not ac_verdicts["AC2_distinct_tools"][0]:
        q3_blockers.append("AC2 (tool diversity)")
    if not ac_verdicts["AC8_traces"][0]:
        q3_blockers.append("AC8 (trace artifacts)")
    # AC7 budget blocker is independent of demo quality
    if not ac_verdicts["AC7_budget"][0]:
        q3_blockers.append("AC7 (budget)")

    if not q3_blockers:
        q3_verdict = "✅ Q3 met — ship ReAct agent as primary demo"
        r7_active = False
    else:
        q3_verdict = f"⚠️ R7 fallback active — Q3 blocked by: {', '.join(q3_blockers)}"
        r7_active = True

    # ---- Day-3 / Day-4 cross reference ----
    pass_summary_lines = [f"- ReAct sweep pass count: **{n_pass}/{n_cases}**"]
    if Path(args.day4_baseline).exists():
        d4 = json.loads(Path(args.day4_baseline).read_text(encoding="utf-8"))
        d4_records = d4 if isinstance(d4, list) else d4.get("records") or []
        d4_pass = sum(1 for r in d4_records if r.get("verdict") == "pass")
        pass_summary_lines.append(f"- Day-4 pipeline pass count: **{d4_pass}/{len(d4_records)}**")
    if Path(args.zero_shot_baseline).exists():
        zs = json.loads(Path(args.zero_shot_baseline).read_text(encoding="utf-8"))
        zs_records = zs if isinstance(zs, list) else zs.get("records") or []
        zs_pass = sum(1 for r in zs_records if r.get("verdict") == "pass")
        pass_summary_lines.append(f"- Zero-shot e2e baseline: **{zs_pass}/{len(zs_records)}**")

    # ---- Markdown report ----
    lines = [
        "# Day-5 Acceptance Report — ReAct Agent + Long-Term Memory",
        "",
        f"**Q3 Verdict**: {q3_verdict}",
        "",
        "## Acceptance criteria (Q3-aware bar; AC6 dropped per Critic)",
        "",
        "| AC | Criterion | Result | Verdict |",
        "|----|-----------|--------|---------|",
    ]
    for k, (ok, detail) in ac_verdicts.items():
        marker = "✅" if ok else "❌"
        lines.append(f"| {k} | {detail} | {marker} |")
    lines.extend([
        "",
        "## Pass count (informational, AC6 dropped)",
        "",
    ])
    lines.extend(pass_summary_lines)
    lines.extend([
        "",
        f"- Recall@1 (informational): {n_recall_hit}/{n_cases}",
        "",
        "## R7 Fallback Decision",
        "",
    ])

    if r7_active:
        lines.extend([
            "**R7 fallback ACTIVE.** Demo ships from Day-4 pipeline artifact ",
            "(`data/evaluation/smoke_agent-full.json`, 6/10 pass) as primary.",
            "ReAct sweep retained as comparison/prototype track.",
            "",
            f"Blockers: {', '.join(q3_blockers)}.",
            "",
            "Capstone narrative angle: pipeline + agent prototype (not replacement).",
        ])
    else:
        lines.extend([
            "**R7 NOT triggered.** ReAct agent ships as primary demo. ",
            "Day-4 pipeline retained as Day-4 baseline reference.",
            "",
            "Capstone narrative angle: agent replaces pipeline as primary, ",
            "with Day-3/4 progression preserved as ablation history.",
        ])

    lines.extend([
        "",
        "## Per-case detail",
        "",
        "| case | gt | predicted | terminal | iters | tools | verdict | recall | $ |",
        "|------|----|-----------|----------|-------|-------|---------|--------|---|",
    ])
    for r in records:
        lines.append(
            f"| {r.get('case_id','?')} | "
            f"`{r.get('ground_truth_function','')}` | "
            f"`{r.get('predicted_function','')}` | "
            f"{r.get('terminal_reason','?')} | "
            f"{r.get('n_iterations','-')} | "
            f"{r.get('distinct_tool_count','-')} | "
            f"{r.get('forge_verdict') or '-'} | "
            f"{'✓' if r.get('recall_hit') else '✗'} | "
            f"${r.get('case_usd', 0):.4f} |"
        )

    lines.extend([
        "",
        "## Files referenced",
        "",
        f"- Sweep aggregate: `{Path(args.sweep_json).relative_to(REPO_ROOT)}`",
        f"- Per-case traces: `{traces_dir.relative_to(REPO_ROOT)}/`",
        f"- Day-4 baseline: `{Path(args.day4_baseline).relative_to(REPO_ROOT)}`",
        f"- Zero-shot baseline: `{Path(args.zero_shot_baseline).relative_to(REPO_ROOT)}`",
        "- Disclosure: `.omc/plans/day4-routing-reversal-disclosure.md` (Day-4 lineage)",
        "",
    ])

    out_path = Path(args.out)
    out_path.write_text("\n".join(lines), encoding="utf-8")

    # ---- Console digest ----
    print("\n" + "=" * 60)
    print(f"  Day-5 Acceptance Report")
    print(f"  Cases: {n_cases}  spend: ${total_usd:.4f}")
    print()
    for k, (ok, detail) in ac_verdicts.items():
        m = "✅" if ok else "❌"
        print(f"  {m} {k:30s} {detail}")
    print()
    print(f"  Q3: {q3_verdict}")
    print()
    print(f"  Report → {out_path}")
    return 0 if not r7_active else 2


if __name__ == "__main__":
    raise SystemExit(main())
