#!/usr/bin/env python3
"""Day-5 S5 — batch ReAct agent sweep over the smoke set.

Wraps `agent.react.loop.run_react_agent` for multi-case execution with:
- Long-term memory backend wired (Memory at data/agent_memory/)
- Per-case R8 guards (max_iter=20, max_usd=0.30, malformed_streak=3)
- Sweep-level cost ceiling (default $2.20 — leaves $1.55 buffer in $5 cap)
- Incremental persistence (per-case JSON + markdown trace as we go)
- Stop rule: abort sweep if running_usd > ceiling
- AC1-AC8 metrics aggregation at end

Outputs:
- data/evaluation/react_traces/<case_id>_trace.{json,md}   (per-case)
- data/evaluation/react_sweep_run1.json                     (aggregate)
- data/evaluation/react_sweep_run1_summary.md               (human-readable)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from agent.memory import Memory  # noqa: E402
from agent.react import run_react_agent  # noqa: E402


def _loose_recall_hit(predicted: str, gt: str) -> bool:
    if not predicted or not gt:
        return False
    p = predicted.lower().strip()
    g = gt.lower().strip()
    return p == g or p in g or g in p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--smoke-set",
        default=str(REPO_ROOT / "data" / "dataset" / "smoke_set.json"),
    )
    ap.add_argument(
        "--memory-root",
        default=str(REPO_ROOT / "data" / "agent_memory"),
    )
    ap.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "data" / "evaluation"),
    )
    ap.add_argument("--max-iter", type=int, default=20)
    ap.add_argument("--max-usd-per-case", type=float, default=0.30)
    ap.add_argument(
        "--max-usd-sweep",
        type=float,
        default=2.20,
        help="Sweep-level abort ceiling (Day-5 AC7).",
    )
    ap.add_argument("--limit", type=int, default=None, help="Limit to first N cases (debug).")
    ap.add_argument(
        "--out-name",
        default="react_sweep_run1",
        help="Stem for output JSON + markdown summary.",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Read existing aggregate JSON; skip case_ids already recorded. "
            "Use after a crash/timeout to continue without re-burning budget "
            "on completed cases. New runs append to existing records."
        ),
    )
    ap.add_argument(
        "--only-cases",
        default=None,
        help="Comma-separated list of case_ids to run (overrides --limit). "
             "Useful for targeted re-runs.",
    )
    ap.add_argument(
        "--mode",
        choices=["5-baseline", "5b-tool", "5b-mandate"],
        default=None,
        help=(
            "Day-5b 3-arm experiment mode. "
            "5-baseline: no cascade tool (Day-5 replay). "
            "5b-tool: try_next_candidate exposed, no MUST mandate. "
            "5b-mandate: cascade tool + prompt MUST + system intercept fallback."
        ),
    )
    args = ap.parse_args()

    # Auto-namespace output when mode is set so 3 arms don't clobber each other
    if args.mode and args.out_name == "react_sweep_run1":
        args.out_name = f"react_5b_{args.mode}"

    smoke = json.loads(Path(args.smoke_set).read_text(encoding="utf-8"))
    cases = smoke.get("cases", [])
    if args.limit:
        cases = cases[: args.limit]

    # Resume support: load existing aggregate to skip completed case_ids.
    out_dir = Path(args.out_dir)
    aggregate_path = out_dir / f"{args.out_name}.json"
    existing_records: list[dict] = []
    skip_ids: set[str] = set()
    if args.resume and aggregate_path.exists():
        try:
            prev = json.loads(aggregate_path.read_text(encoding="utf-8"))
            existing_records = prev.get("records") or []
            skip_ids = {r["case_id"] for r in existing_records if "case_id" in r}
            print(f"[react-sweep] [resume] loaded {len(existing_records)} prior records "
                  f"from {aggregate_path}, skipping {len(skip_ids)} case_ids")
        except Exception as exc:
            print(f"[react-sweep] [resume] WARN: failed to read prior aggregate: {exc}")

    # --only-cases overrides any other filter
    if args.only_cases:
        wanted = {c.strip() for c in args.only_cases.split(",") if c.strip()}
        cases = [c for c in cases if c.get("id") in wanted]
        print(f"[react-sweep] --only-cases filter: {sorted(wanted)} → {len(cases)} cases")
    elif skip_ids:
        cases = [c for c in cases if c.get("id") not in skip_ids]

    print(f"[react-sweep] running {len(cases)} cases  max_iter={args.max_iter} "
          f"max_usd_per_case=${args.max_usd_per_case} sweep_cap=${args.max_usd_sweep}")

    mem = Memory(Path(args.memory_root))
    print(f"[react-sweep] memory loaded: {mem.stats()}")

    traces_dir = out_dir / "react_traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    # Carry over prior records (resume) so aggregate stays cumulative.
    records: list[dict] = list(existing_records)
    running_usd = sum(r.get("case_usd", 0.0) for r in existing_records)
    aborted = None
    if existing_records:
        print(f"[react-sweep] [resume] starting running_usd=${running_usd:.4f} "
              f"(carried from {len(existing_records)} prior records)")

    for i, case in enumerate(cases, start=1):
        if running_usd >= args.max_usd_sweep:
            aborted = (
                f"sweep ceiling ${args.max_usd_sweep} hit after case {i-1}/"
                f"{len(cases)} (running_usd=${running_usd:.4f})"
            )
            print(f"\n[react-sweep] [ABORT] {aborted}")
            break

        cid = case["id"]
        cname = case.get("contract_name", "?")
        gt = case.get("vulnerable_function", "") or ""
        print(f"\n  [{i}/{len(cases)}] {cid} ({cname}) ...")

        try:
            result = run_react_agent(
                case,
                memory_backend=mem,
                max_iter=args.max_iter,
                max_usd_per_case=args.max_usd_per_case,
                mode=args.mode,
            )
        except Exception as exc:
            print(f"    CRASH: {type(exc).__name__}: {exc}")
            records.append({
                "case_id": cid,
                "contract_name": cname,
                "verdict": "crash",
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        running_usd += result.total_usd

        # Persist per-case trace
        trace_json_path = traces_dir / f"{cid}_trace.json"
        trace_md_path = traces_dir / f"{cid}_trace.md"
        trace_json_path.write_text(
            json.dumps(result.trace.to_json(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        trace_md_path.write_text(result.trace.to_markdown(), encoding="utf-8")

        recall_hit = _loose_recall_hit(result.target_function, gt)

        rec = {
            "case_id": cid,
            "contract_name": cname,
            "ground_truth_function": gt,
            "predicted_function": result.target_function,
            "recall_hit": recall_hit,
            "terminal_reason": result.terminal_reason,
            "self_terminated": result.terminal_reason
                in ("submit_finding", "give_up", "system_cascade_pass", "system_cascade_then_give_up"),
            "finding_confirmed": result.finding_confirmed,
            "forge_verdict": result.last_forge_verdict,
            "n_iterations": result.n_iterations,
            "distinct_tool_count": result.distinct_tool_count,
            "tools_called": list(result.state.tools_called),
            "recall_self_lesson_nonempty": result.recall_self_lesson_nonempty,
            # Day-5b mechanical AC9 fields
            "cascade_invocations": result.state.cascade_invocations,
            "cascade_was_system_forced": result.state.cascade_was_system_forced,
            "first_forge_verdict": result.state.first_forge_verdict,
            "mode": args.mode or "default",
            "case_usd": result.total_usd,
            "running_usd": round(running_usd, 4),
            "tokens_prompt": int(result.annotations.get("tokens_prompt", 0)),
            "tokens_completion": int(result.annotations.get("tokens_completion", 0)),
        }
        records.append(rec)

        # Print 1-line per-case status
        marker = (
            "✅" if result.finding_confirmed
            else ("🤷" if result.terminal_reason == "give_up" else "⚠️")
        )
        print(
            f"    {marker} terminal={result.terminal_reason} "
            f"iters={result.n_iterations} tools={result.distinct_tool_count} "
            f"verdict={result.last_forge_verdict or '-'} "
            f"recall={'✓' if recall_hit else '✗'} "
            f"${result.total_usd:.4f} (running ${running_usd:.4f})"
        )

        # Persist aggregate incrementally
        aggregate_path.write_text(
            json.dumps(
                {
                    "n_cases_run": len(records),
                    "n_cases_total": len(cases),
                    "running_usd": round(running_usd, 4),
                    "aborted": aborted,
                    "records": records,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # ---- Aggregate metrics ----
    n = len(records)
    n_self_term = sum(1 for r in records if r.get("self_terminated"))
    n_pass = sum(1 for r in records if r.get("finding_confirmed"))
    n_recall_hit = sum(1 for r in records if r.get("recall_hit"))
    avg_distinct_tools = (
        sum(r.get("distinct_tool_count", 0) for r in records) / n if n else 0
    )
    n_recall_lesson_nonempty = sum(
        1 for r in records if r.get("recall_self_lesson_nonempty", 0) > 0
    )

    summary = {
        "n_cases_run": n,
        "running_usd": round(running_usd, 4),
        "aborted": aborted,
        # AC1
        "ac1_self_terminate": f"{n_self_term}/{n}",
        "ac1_pass": n_self_term >= 7,  # AC1 threshold
        # AC2
        "ac2_avg_distinct_tools": round(avg_distinct_tools, 2),
        "ac2_pass": avg_distinct_tools >= 3,  # AC2 threshold
        # AC5b
        "ac5b_cases_with_lesson_recall": f"{n_recall_lesson_nonempty}/{n}",
        "ac5b_pass": n_recall_lesson_nonempty >= 2,  # AC5b threshold
        # AC7 budget
        "ac7_within_budget": running_usd <= 2.50,
        # Pass count (informational, AC6 dropped per Critic)
        "pass_count": n_pass,
        "recall_at_1": f"{n_recall_hit}/{n}",
        # Memory growth
        "memory_after": mem.stats(),
    }

    # Write summary markdown
    md_lines = [
        f"# Day-5 ReAct Agent Sweep — `{args.out_name}`",
        "",
        f"- Cases run: **{n} / {len(cases)}** {'(ABORTED)' if aborted else ''}",
        f"- Total spend: **${running_usd:.4f}**",
        "",
        "## Acceptance criteria (Q3 mandate)",
        "",
        f"- **AC1** Self-termination: `{summary['ac1_self_terminate']}` "
        f"→ {'✅ PASS' if summary['ac1_pass'] else '❌ FAIL'} (≥7/10 required)",
        f"- **AC2** Avg distinct tools/case: `{summary['ac2_avg_distinct_tools']}` "
        f"→ {'✅ PASS' if summary['ac2_pass'] else '❌ FAIL'} (≥3 required)",
        f"- **AC5b** Cases with non-empty self-lesson recall: "
        f"`{summary['ac5b_cases_with_lesson_recall']}` "
        f"→ {'✅ PASS' if summary['ac5b_pass'] else '❌ FAIL'} (≥2 required)",
        f"- **AC7** Within budget ≤$2.50: "
        f"`${running_usd:.4f}` "
        f"→ {'✅ PASS' if summary['ac7_within_budget'] else '❌ FAIL'}",
        f"- **AC8** Per-case markdown trace: see `{traces_dir.relative_to(REPO_ROOT)}/`",
        "",
        f"_AC6 (pass≥4) DROPPED per Critic; informational pass count = "
        f"**{n_pass}/{n}**, Recall@1 = **{n_recall_hit}/{n}**._",
        "",
        "## Per-case detail",
        "",
        "| case | gt | predicted | terminal | iters | tools | verdict | recall | $ |",
        "|------|----|-----------|----------|-------|-------|---------|--------|---|",
    ]
    for r in records:
        md_lines.append(
            f"| {r['case_id']} | `{r.get('ground_truth_function','')}` | "
            f"`{r.get('predicted_function','')}` | {r.get('terminal_reason','?')} | "
            f"{r.get('n_iterations','-')} | {r.get('distinct_tool_count','-')} | "
            f"{r.get('forge_verdict') or '-'} | "
            f"{'✓' if r.get('recall_hit') else '✗'} | "
            f"${r.get('case_usd', 0):.4f} |"
        )
    if aborted:
        md_lines.append("")
        md_lines.append(f"> ⚠️ **ABORTED**: {aborted}")
    md_lines.append("")

    summary_md_path = out_dir / f"{args.out_name}_summary.md"
    summary_md_path.write_text("\n".join(md_lines), encoding="utf-8")

    # Final aggregate JSON write (with summary block)
    aggregate_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "records": records,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # ---- Console report ----
    print("\n" + "=" * 60)
    print(f"  Sweep complete: {n}/{len(cases)} cases, ${running_usd:.4f} spent")
    print(f"  AC1 self-terminate:   {summary['ac1_self_terminate']}  "
          f"{'✅' if summary['ac1_pass'] else '❌'}")
    print(f"  AC2 avg distinct tools: {summary['ac2_avg_distinct_tools']}  "
          f"{'✅' if summary['ac2_pass'] else '❌'}")
    print(f"  AC5b lesson recall ≥1: {summary['ac5b_cases_with_lesson_recall']}  "
          f"{'✅' if summary['ac5b_pass'] else '❌'}")
    print(f"  AC7 budget:           ${running_usd:.4f} ≤ $2.50  "
          f"{'✅' if summary['ac7_within_budget'] else '❌'}")
    print(f"  pass_count (info):    {n_pass}/{n}")
    print(f"  Recall@1 (info):      {n_recall_hit}/{n}")
    print(f"  Memory after:         {mem.stats()}")
    print(f"\n  Summary → {summary_md_path}")
    print(f"  Aggregate → {aggregate_path}")
    print(f"  Per-case traces → {traces_dir}/")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
