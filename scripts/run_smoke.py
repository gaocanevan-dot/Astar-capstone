#!/usr/bin/env python3
"""Day-2 T12 — Smoke ablation harness with cost gate.

Runs a 4-arm × 10-case ablation over the smoke set, with two safety knobs:

  --dry-run-3-cases   Run agent-full on the first 3 smoke cases only;
                      measure actual tokens; project to 4×10=40-run USD;
                      then EXIT before the full sweep. This is the cost
                      gate's calibration step.

  --max-usd-cost N    Hard ceiling. Computed projection > N → abort with
                      structured diagnostic. Set to 0 to inspect the
                      projection without ever running the full sweep.

Arms (per ralplan iter4 §2):
  agent-full       cascade + reflection + tool-use + RAG (TF-IDF default)
  no-cascade       single candidate (top-1 only) — cascade disabled
  no-reflection    cascade ON, reflection node bypassed
  no-rag           cascade + reflection + tool-use; RAG disabled

USD projection model (see `_project_usd`):
  - Token counts come from `annotations.tokens_prompt` / `tokens_completion`
    on each `PipelineResult` (already tracked by adapter.llm.invoke_json).
  - Default rate: $0.01/1K prompt tokens, $0.03/1K completion (gpt-4-turbo
    ballpark). Override via `--prompt-rate` / `--completion-rate` per 1K.
  - Projection = (sum_3_cases_tokens / 3) × 40 × rate.

This script is import-safe (no LLM calls at module load). Day-2 ships the
harness + cost-gate logic; the actual full sweep happens on Day 3 when the
user gates the spend.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


ARMS = ("agent-full", "no-cascade", "no-reflection", "no-rag")

# Default per-1K-token pricing (gpt-4-turbo rough). Override via CLI.
DEFAULT_PROMPT_RATE_PER_1K = 0.01
DEFAULT_COMPLETION_RATE_PER_1K = 0.03


def _arm_flags(arm: str) -> dict[str, bool]:
    """Map arm name to feature flags consumed by the pipeline drivers."""
    return {
        "use_cascade": arm in ("agent-full", "no-reflection", "no-rag"),
        "use_reflection": arm in ("agent-full", "no-rag"),
        "use_tools": True,  # tool-use is always on (no arm toggles it)
        "use_rag": arm in ("agent-full", "no-cascade", "no-reflection"),
    }


def _load_smoke_cases(smoke_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(smoke_path.read_text(encoding="utf-8"))
    return list(payload.get("cases", []))


def _project_usd(
    sample_tokens_prompt: int,
    sample_tokens_completion: int,
    sample_size: int,
    full_sweep_runs: int,
    prompt_rate: float,
    completion_rate: float,
) -> dict[str, float]:
    """Linear extrapolation: per-case avg × full sweep size × rate.

    Returns: {avg_prompt_per_case, avg_completion_per_case,
              projected_prompt_total, projected_completion_total,
              projected_usd}.
    """
    if sample_size <= 0:
        return {
            "avg_prompt_per_case": 0.0,
            "avg_completion_per_case": 0.0,
            "projected_prompt_total": 0.0,
            "projected_completion_total": 0.0,
            "projected_usd": 0.0,
        }
    avg_p = sample_tokens_prompt / sample_size
    avg_c = sample_tokens_completion / sample_size
    proj_p = avg_p * full_sweep_runs
    proj_c = avg_c * full_sweep_runs
    usd = (proj_p / 1000.0) * prompt_rate + (proj_c / 1000.0) * completion_rate
    return {
        "avg_prompt_per_case": avg_p,
        "avg_completion_per_case": avg_c,
        "projected_prompt_total": proj_p,
        "projected_completion_total": proj_c,
        "projected_usd": round(usd, 4),
    }


def _run_dry_sample(
    cases: list[dict[str, Any]],
    sample_size: int,
    arm: str,
    max_retries: int,
) -> tuple[int, int, list[dict[str, Any]]]:
    """Run the first `sample_size` cases under the chosen arm via run_pipeline.

    Day-3 W2: arm flags from `_arm_flags(arm)` are now threaded through
    `run_pipeline`'s `use_cascade` / `use_reflection` / `use_tools` params.
    `use_rag` controls whether the default TF-IDF rag store is loaded.

    Returns (sum_prompt_tokens, sum_completion_tokens, per_case_records).
    """
    from agent.graph import run_pipeline  # late import — keeps module load cheap

    flags = _arm_flags(arm)

    # Conditionally load default RAG store. None = no RAG context injected.
    rag_store = None
    if flags["use_rag"]:
        from agent.adapters.rag import load_default_rag_store

        try:
            rag_store = load_default_rag_store()
        except Exception as exc:
            print(
                f"[WARN] use_rag=True but failed to load default rag store: {exc}",
                file=sys.stderr,
            )

    sum_p = 0
    sum_c = 0
    records: list[dict[str, Any]] = []
    for case in cases[:sample_size]:
        r = run_pipeline(
            case_id=case["id"],
            contract_source=case.get("contract_source", ""),
            contract_name=case.get("contract_name", ""),
            max_retries=max_retries,
            verifier_mode=case.get("verifier_mode"),
            rag_store=rag_store,
            use_cascade=flags["use_cascade"],
            use_reflection=flags["use_reflection"],
            use_tools=flags["use_tools"],
        )
        ann = r.annotations or {}
        sum_p += int(ann.get("tokens_prompt", 0))
        sum_c += int(ann.get("tokens_completion", 0))
        records.append(
            {
                "arm": arm,
                "case_id": case["id"],
                "verdict": r.execution_result,
                "tokens_prompt": ann.get("tokens_prompt", 0),
                "tokens_completion": ann.get("tokens_completion", 0),
                "wall_clock_s": r.wall_clock_s,
                "cascade_depth": len(ann.get("cascade_trace", []) or []),
                "reflection_calls": len(ann.get("reflection_trace", []) or []),
            }
        )
    return sum_p, sum_c, records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--smoke-set",
        default=str(REPO_ROOT / "data" / "dataset" / "smoke_set.json"),
    )
    ap.add_argument(
        "--arms",
        default=",".join(ARMS),
        help=f"Comma-sep subset of {ARMS}",
    )
    ap.add_argument(
        "--dry-run-3-cases",
        action="store_true",
        help="Run 3 cases of agent-full only, project full-sweep USD, exit.",
    )
    ap.add_argument(
        "--max-usd-cost",
        type=float,
        default=None,
        help="Hard ceiling. Abort full sweep if projection exceeds this. "
        "Set to 0 to inspect projection without ever running the sweep.",
    )
    ap.add_argument(
        "--prompt-rate",
        type=float,
        default=DEFAULT_PROMPT_RATE_PER_1K,
        help=f"USD per 1K prompt tokens (default {DEFAULT_PROMPT_RATE_PER_1K})",
    )
    ap.add_argument(
        "--completion-rate",
        type=float,
        default=DEFAULT_COMPLETION_RATE_PER_1K,
        help=f"USD per 1K completion tokens (default {DEFAULT_COMPLETION_RATE_PER_1K})",
    )
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--dry-sample-size", type=int, default=3)
    ap.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "data" / "evaluation"),
    )
    args = ap.parse_args()

    smoke_path = Path(args.smoke_set)
    if not smoke_path.exists():
        print(f"ERROR: smoke set not found: {smoke_path}", file=sys.stderr)
        return 1

    cases = _load_smoke_cases(smoke_path)
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    invalid_arms = [a for a in arms if a not in ARMS]
    if invalid_arms:
        print(f"ERROR: unknown arms: {invalid_arms}", file=sys.stderr)
        return 1

    full_sweep_runs = len(arms) * len(cases)
    print(
        f"Smoke set: {len(cases)} cases; arms: {arms}; full-sweep size = "
        f"{full_sweep_runs} runs"
    )

    if args.dry_run_3_cases:
        print(
            f"\n[DRY-RUN] Running first {args.dry_sample_size} cases under "
            f"`agent-full` to calibrate cost projection..."
        )
        t0 = time.time()
        sum_p, sum_c, records = _run_dry_sample(
            cases, args.dry_sample_size, "agent-full", args.max_retries
        )
        elapsed = time.time() - t0
        proj = _project_usd(
            sum_p,
            sum_c,
            args.dry_sample_size,
            full_sweep_runs,
            args.prompt_rate,
            args.completion_rate,
        )
        print(
            f"\n[DRY-RUN] sample_size={args.dry_sample_size} "
            f"sum_prompt={sum_p} sum_completion={sum_c} "
            f"wall_clock={elapsed:.1f}s"
        )
        print(
            f"[PROJECTION] avg/case prompt={proj['avg_prompt_per_case']:.0f} "
            f"completion={proj['avg_completion_per_case']:.0f}"
        )
        print(
            f"[PROJECTION] full_sweep ({full_sweep_runs} runs) total tokens: "
            f"prompt={proj['projected_prompt_total']:.0f} "
            f"completion={proj['projected_completion_total']:.0f}"
        )
        print(
            f"[PROJECTION] projected USD = ${proj['projected_usd']:.4f} "
            f"(rates: ${args.prompt_rate}/1K prompt + "
            f"${args.completion_rate}/1K completion)"
        )

        # Persist dry-run record FIRST — even on gate-abort the user needs
        # the audit trail (token counts, projection, sample records) to
        # debug or re-rate.
        import os as _os

        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        dry_path = out_dir / "smoke_dry_run.json"
        dry_path.write_text(
            json.dumps(
                {
                    "model": _os.environ.get("OPENAI_MODEL", "<default>"),
                    "prompt_rate_per_1k": args.prompt_rate,
                    "completion_rate_per_1k": args.completion_rate,
                    "sample_size": args.dry_sample_size,
                    "wall_clock_s": elapsed,
                    "sample_records": records,
                    "projection": proj,
                    "max_usd_cost": args.max_usd_cost,
                    "arms": arms,
                    "full_sweep_runs": full_sweep_runs,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nDry-run report written to {dry_path}")

        if args.max_usd_cost is not None:
            if proj["projected_usd"] > args.max_usd_cost:
                print(
                    f"\n[GATE-ABORT] projected ${proj['projected_usd']:.4f} > "
                    f"--max-usd-cost ${args.max_usd_cost}",
                    file=sys.stderr,
                )
                return 2
            print(
                f"\n[GATE-PASS] projected ${proj['projected_usd']:.4f} <= "
                f"--max-usd-cost ${args.max_usd_cost}"
            )
        print(
            "\n[DAY-2 STOP] Per ralplan iter4, full 4-arm × 10-case ablation "
            "is Day-3 territory. Re-run without --dry-run-3-cases to execute."
        )
        return 0

    # ---------- FULL SWEEP (Day-3 A) ----------
    print(
        f"\n[FULL-SWEEP] Running {len(arms)} arms × {len(cases)} cases = "
        f"{full_sweep_runs} pipeline runs."
    )
    if args.max_usd_cost is not None:
        print(
            f"[FULL-SWEEP] running-USD ceiling = ${args.max_usd_cost} "
            f"(aborts mid-sweep if hit)"
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results, running_usd, aborted = _run_full_sweep(
        cases=cases,
        arms=arms,
        max_retries=args.max_retries,
        prompt_rate=args.prompt_rate,
        completion_rate=args.completion_rate,
        max_usd_cost=args.max_usd_cost,
        out_dir=out_dir,
    )

    summary_path = out_dir / "smoke_summary.md"
    _aggregate_summary(
        results=results,
        out_path=summary_path,
        running_usd=running_usd,
        aborted=aborted,
    )
    print(f"\nSummary written to {summary_path}")
    print(f"Per-arm JSON: {out_dir}/smoke_<arm>.json")
    print(f"Total spend: ${running_usd:.4f}")
    if aborted:
        print(f"\n[ABORTED] {aborted}", file=sys.stderr)
        return 4
    return 0


# ---------------------------------------------------------------------------
# Day-3 A: full-sweep execution + aggregation
# ---------------------------------------------------------------------------


def _run_full_sweep(
    cases: list[dict[str, Any]],
    arms: list[str],
    max_retries: int,
    prompt_rate: float,
    completion_rate: float,
    max_usd_cost: float | None,
    out_dir: Path,
) -> tuple[dict[str, list[dict[str, Any]]], float, str | None]:
    """Run each arm over all cases. Persist per-arm JSON incrementally.

    Aborts mid-sweep if running USD spend exceeds max_usd_cost. Returns
    (results, running_usd, aborted_reason | None).
    """
    from agent.graph import run_pipeline  # late import

    results: dict[str, list[dict[str, Any]]] = {arm: [] for arm in arms}
    running_usd = 0.0
    aborted: str | None = None

    for arm in arms:
        flags = _arm_flags(arm)
        rag_store = None
        if flags["use_rag"]:
            from agent.adapters.rag import load_default_rag_store

            try:
                rag_store = load_default_rag_store()
            except Exception as exc:
                print(
                    f"[WARN] arm={arm} use_rag=True but failed to load default "
                    f"rag store: {exc}",
                    file=sys.stderr,
                )

        for i, case in enumerate(cases, start=1):
            if max_usd_cost is not None and running_usd >= max_usd_cost:
                aborted = (
                    f"running-USD ${running_usd:.4f} >= ceiling "
                    f"${max_usd_cost} at arm={arm} case={i}/{len(cases)}"
                )
                break

            try:
                r = run_pipeline(
                    case_id=case["id"],
                    contract_source=case.get("contract_source", ""),
                    contract_name=case.get("contract_name", ""),
                    max_retries=max_retries,
                    verifier_mode=case.get("verifier_mode"),
                    rag_store=rag_store,
                    use_cascade=flags["use_cascade"],
                    use_reflection=flags["use_reflection"],
                    use_tools=flags["use_tools"],
                )
            except Exception as exc:
                print(
                    f"  [{arm}] {i}/{len(cases)} {case.get('id','?')}: "
                    f"CRASH {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                results[arm].append(
                    {
                        "arm": arm,
                        "case_id": case.get("id", ""),
                        "verdict": "crash",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue

            ann = r.annotations or {}
            tp = int(ann.get("tokens_prompt", 0))
            tc = int(ann.get("tokens_completion", 0))
            case_usd = (tp / 1000.0) * prompt_rate + (
                tc / 1000.0
            ) * completion_rate
            running_usd += case_usd

            record = {
                "arm": arm,
                "case_id": case["id"],
                "verdict": r.execution_result,
                "finding_confirmed": r.finding_confirmed,
                "target_function": r.target_function,
                "ground_truth_function": case.get("vulnerable_function", ""),
                "tokens_prompt": tp,
                "tokens_completion": tc,
                "case_usd": round(case_usd, 4),
                "running_usd": round(running_usd, 4),
                "wall_clock_s": r.wall_clock_s,
                "poc_attempts": r.poc_attempts,
                "cascade_depth": len(ann.get("cascade_trace", []) or []),
                "reflection_calls": len(ann.get("reflection_trace", []) or []),
                "abstained": bool(ann.get("abstained", False)),
                "finding_reason": r.finding_reason,
            }
            results[arm].append(record)

            print(
                f"  [{arm}] {i}/{len(cases)} {case['id']}: "
                f"verdict={r.execution_result} depth={record['cascade_depth']} "
                f"refl={record['reflection_calls']} ${case_usd:.4f} "
                f"(running ${running_usd:.4f})",
                flush=True,
            )

            # Persist incrementally so a crash doesn't lose progress.
            arm_path = out_dir / f"smoke_{arm}.json"
            arm_path.write_text(
                json.dumps(results[arm], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        if aborted:
            break

    return results, running_usd, aborted


def _aggregate_summary(
    results: dict[str, list[dict[str, Any]]],
    out_path: Path,
    running_usd: float,
    aborted: str | None,
) -> None:
    """Write summary.md with per-arm Recall@1, verdict counts, CVR, ablation."""

    def _is_recall_hit(predicted: str, gt: str) -> bool:
        if not predicted or not gt:
            return False
        p = predicted.lower().strip()
        g = gt.lower().strip()
        return p == g or p in g or g in p

    arm_stats: dict[str, dict[str, Any]] = {}
    for arm, recs in results.items():
        n = len(recs)
        verdicts = {
            "pass": 0,
            "fail_revert_ac": 0,
            "fail_error_compile": 0,
            "fail_error_runtime": 0,
            "abstain": 0,
            "skipped": 0,
            "crash": 0,
        }
        recall_at_1 = 0
        cascade_advance = 0  # count of records with cascade_depth > 1
        for r in recs:
            v = r.get("verdict", "")
            verdicts[v] = verdicts.get(v, 0) + 1
            if _is_recall_hit(
                r.get("target_function", ""), r.get("ground_truth_function", "")
            ):
                recall_at_1 += 1
            if (r.get("cascade_depth") or 0) > 1:
                cascade_advance += 1

        denom = (
            verdicts["pass"]
            + verdicts["fail_revert_ac"]
            + verdicts["fail_error_runtime"]
        )
        cvr = verdicts["pass"] / denom if denom else None
        arm_stats[arm] = {
            "n": n,
            "recall_at_1": recall_at_1,
            "verdict_counts": verdicts,
            "confirmed_vulnerability_rate": cvr,
            "cascade_advance_count": cascade_advance,
            "total_usd": round(sum(r.get("case_usd", 0.0) for r in recs), 4),
        }

    lines: list[str] = [
        "# Smoke Ablation Summary",
        "",
        "Day-3 A — full 4-arm × 10-case sweep on the C5/Repair smoke set.",
        "",
    ]
    if aborted:
        lines.append(f"> **⚠️ ABORTED**: {aborted}")
        lines.append("")
    lines.append(f"- Total wall spend: **${running_usd:.4f}**")
    lines.append("")
    lines.append("## Per-arm metrics")
    lines.append("")
    lines.append(
        "| Arm | n | Recall@1 | pass | revert_ac | err_compile | err_runtime "
        "| abstain | skipped | crash | cascade>1 | CVR | USD |"
    )
    lines.append(
        "|-----|---|----------|------|-----------|-------------|-------------|---------|---------|-------|----------|-----|-----|"
    )
    for arm, s in arm_stats.items():
        v = s["verdict_counts"]
        cvr_str = (
            f"{s['confirmed_vulnerability_rate']:.2f}"
            if s["confirmed_vulnerability_rate"] is not None
            else "n/a"
        )
        lines.append(
            f"| {arm} | {s['n']} | {s['recall_at_1']}/{s['n']} | {v['pass']} | "
            f"{v['fail_revert_ac']} | {v['fail_error_compile']} | "
            f"{v['fail_error_runtime']} | {v['abstain']} | {v['skipped']} | "
            f"{v['crash']} | {s['cascade_advance_count']} | {cvr_str} | "
            f"${s['total_usd']:.4f} |"
        )
    lines.append("")

    # Per-arm detail tables
    for arm, recs in results.items():
        lines.append(f"## `{arm}` per-case detail")
        lines.append("")
        lines.append(
            "| case_id | gt fn | predicted | verdict | depth | refl | USD | finding_reason |"
        )
        lines.append(
            "|---------|-------|-----------|---------|-------|------|-----|----------------|"
        )
        for r in recs:
            reason = (r.get("finding_reason") or r.get("error") or "")[:80]
            lines.append(
                f"| {r.get('case_id','?')} | "
                f"`{r.get('ground_truth_function','')}` | "
                f"`{r.get('target_function','')}` | "
                f"{r.get('verdict','?')} | "
                f"{r.get('cascade_depth','-')} | "
                f"{r.get('reflection_calls','-')} | "
                f"${r.get('case_usd', 0):.4f} | "
                f"{reason} |"
            )
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
