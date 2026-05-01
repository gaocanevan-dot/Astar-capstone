"""ReAct loop driver.

Runs a single case through tool-use iterations until the agent calls
`submit_finding` or `give_up`, or until a R8 guard fires:
- max_iter exhausted (forced give_up synthesis)
- per-case USD ceiling hit
- 3 consecutive malformed/no-tool LLM responses (3-strike circuit breaker)

Public entry: `run_react_agent(case, memory_backend, ...) -> AgentResult`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from agent.adapters.llm import chat_with_tools
from agent.react.prompts import build_system_prompt, format_case_brief
from agent.react.state import AgentState
from agent.react.tools import (
    TERMINAL_TOOLS,
    TOOL_SCHEMAS,
    dispatch_tool,
)
from agent.react.trace import Trace, TraceStep


# Day-5 R8 defaults (mirrors Critic-pruned acceptance bar)
MAX_ITER_DEFAULT = 20
MAX_USD_PER_CASE_DEFAULT = 0.30
MAX_MALFORMED_STREAK_DEFAULT = 3

# gpt-5-mini per-1K rates (overridable via ctor)
DEFAULT_PROMPT_RATE = 0.00025
DEFAULT_COMPLETION_RATE = 0.002


@dataclass
class AgentResult:
    """Outcome of one agent run on one case."""

    case_id: str
    contract_name: str

    terminal_reason: str  # submit_finding | give_up | max_iter | case_budget_exceeded | malformed_circuit_breaker | llm_error
    n_iterations: int
    total_usd: float
    state: AgentState

    trace: Trace

    # Convenience
    finding_confirmed: bool = False
    target_function: str = ""
    last_forge_verdict: str = ""
    distinct_tool_count: int = 0
    recall_self_lesson_nonempty: int = 0

    # Aggregate annotations (token counts etc.)
    annotations: dict[str, Any] = field(default_factory=dict)


def _compute_usd_delta(
    annotations: dict[str, Any],
    prev_prompt: int,
    prev_completion: int,
    prompt_rate: float,
    completion_rate: float,
) -> tuple[float, int, int]:
    cur_p = int(annotations.get("tokens_prompt", 0))
    cur_c = int(annotations.get("tokens_completion", 0))
    delta_p = max(0, cur_p - prev_prompt)
    delta_c = max(0, cur_c - prev_completion)
    delta_usd = (delta_p / 1000.0) * prompt_rate + (delta_c / 1000.0) * completion_rate
    return delta_usd, cur_p, cur_c


def run_react_agent(
    case: dict,
    memory_backend: Optional[Any] = None,
    *,
    max_iter: int = MAX_ITER_DEFAULT,
    max_usd_per_case: float = MAX_USD_PER_CASE_DEFAULT,
    max_malformed_streak: int = MAX_MALFORMED_STREAK_DEFAULT,
    prompt_rate: float = DEFAULT_PROMPT_RATE,
    completion_rate: float = DEFAULT_COMPLETION_RATE,
    chat_with_tools_fn=None,  # injection point for tests
) -> AgentResult:
    """Run the ReAct loop on a single case.

    `memory_backend` is the (yet-to-be-wired) Memory object exposing
    `recall_anti_pattern / recall_similar_cases / recall_self_lesson / save_lesson`.
    During Phase 1 it is None and memory tools no-op cleanly.
    """
    chat_fn = chat_with_tools_fn or chat_with_tools

    state = AgentState(
        case_id=case.get("id", "?"),
        contract_name=case.get("contract_name", "?"),
    )
    trace = Trace.new(case_id=state.case_id, contract_name=state.contract_name)

    history: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt(max_iter=max_iter)},
        {"role": "user", "content": format_case_brief(case)},
    ]

    prev_prompt_tokens = 0
    prev_completion_tokens = 0
    terminal_reason = "max_iter"  # default if no early exit

    for iter_idx in range(1, max_iter + 1):
        # --- Pre-iter R8 guards ---
        if state.case_usd >= max_usd_per_case:
            terminal_reason = "case_budget_exceeded"
            break
        if state.malformed_streak >= max_malformed_streak:
            terminal_reason = "malformed_circuit_breaker"
            break

        # --- Mid-run progression nudges (anti-wandering) ---
        # If by iter 4 we haven't proposed a target, inject a reminder on
        # the user side before the LLM round so it sees explicit pressure.
        if iter_idx == 4 and "propose_target" not in state.tools_called:
            history.append({
                "role": "user",
                "content": (
                    "[iteration nudge] You are at iter 4 and have not yet "
                    "called `propose_target`. Per the iteration schedule, "
                    "your NEXT action MUST be `propose_target` with the "
                    "most suspicious candidate from your earlier "
                    "static_analyze output. Stop inspecting — pick one and "
                    "let run_forge tell you if it's right."
                ),
            })
        if iter_idx == 6 and "run_forge" not in state.tools_called:
            history.append({
                "role": "user",
                "content": (
                    "[iteration nudge] You are at iter 6 and have not yet "
                    "called `run_forge`. If you've called `write_poc`, "
                    "execute it now. Otherwise, your next action MUST be "
                    "`write_poc` (followed by `run_forge` next iter)."
                ),
            })
        if iter_idx >= max_iter - 2 and not (
            "submit_finding" in state.tools_called
            or "give_up" in state.tools_called
        ):
            # Final 2 iters and still no terminal tool called
            history.append({
                "role": "user",
                "content": (
                    f"[final nudge] You have only {max_iter - iter_idx + 1} "
                    "iterations left and have not yet terminated. Either "
                    "submit_finding (if any forge run passed) or give_up "
                    "with an honest reason. Do this NOW."
                ),
            })

        # --- LLM round trip ---
        try:
            resp = chat_fn(history, TOOL_SCHEMAS, state.annotations)
        except Exception as exc:
            terminal_reason = f"llm_error:{type(exc).__name__}"
            trace.add_step(TraceStep(
                step=iter_idx,
                iso_ts=datetime.now(timezone.utc).isoformat(),
                error=f"llm: {type(exc).__name__}: {exc}",
            ))
            break

        # Cost accounting
        delta_usd, prev_prompt_tokens, prev_completion_tokens = _compute_usd_delta(
            state.annotations,
            prev_prompt_tokens,
            prev_completion_tokens,
            prompt_rate,
            completion_rate,
        )
        state.case_usd += delta_usd

        # Inspect response: tool_calls vs no-tool-call
        tool_calls = resp.get("tool_calls") or []
        assistant_content = resp.get("content") or ""

        if not tool_calls:
            # Soft malformed — model returned text without calling a tool.
            state.malformed_streak += 1
            trace.add_step(TraceStep(
                step=iter_idx,
                iso_ts=datetime.now(timezone.utc).isoformat(),
                thought=assistant_content[:500],
                error="no_tool_call",
                usd_cost_delta=delta_usd,
            ))
            history.append({"role": "assistant", "content": assistant_content})
            history.append({
                "role": "user",
                "content": (
                    "Reminder: you MUST call exactly one tool per turn. "
                    "If you cannot make progress, call `give_up` with a reason. "
                    f"({state.malformed_streak}/{max_malformed_streak} malformed strikes used)"
                ),
            })
            continue

        # Reset malformed streak on a valid tool-call response
        state.malformed_streak = 0

        # Append the assistant message (with tool_calls) to history. We need
        # the raw tool_calls field for OpenAI API protocol.
        history.append({
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": resp.get("raw_tool_calls", tool_calls),
        })

        # Process each tool call (typically 1 per response, but handle batch)
        terminated_in_batch = False
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("arguments", {}) or {}
            tool_call_id = tc.get("id", "")

            obs = dispatch_tool(tool_name, tool_args, case, memory_backend, state)
            state.tools_called.append(tool_name)

            trace.add_step(TraceStep(
                step=iter_idx,
                iso_ts=datetime.now(timezone.utc).isoformat(),
                thought=assistant_content[:500],
                tool_name=tool_name,
                tool_args=tool_args,
                tool_call_id=tool_call_id,
                tool_result=obs,
                usd_cost_delta=delta_usd if tc is tool_calls[0] else 0.0,
            ))

            history.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": obs,
            })

            if tool_name in TERMINAL_TOOLS:
                terminal_reason = tool_name
                terminated_in_batch = True
                break  # don't process further tool_calls in this batch

        if terminated_in_batch:
            break

    # --- Finalize ---
    if terminal_reason == "max_iter":
        # Forced give_up synthesis (Q3 mandate: clean termination)
        state.given_up_reason = (
            f"max_iter={max_iter} reached without self-termination "
            f"(R8 forced give_up synthesis)"
        )

    n_iterations = len([s for s in trace.steps if s.tool_name or s.error == "no_tool_call"])
    trace.terminal_reason = terminal_reason
    trace.total_usd = round(state.case_usd, 4)

    # ---- Auto-save episode to long-term memory (if backend wired) ----
    if memory_backend is not None and hasattr(memory_backend, "save_episode"):
        try:
            if terminal_reason == "submit_finding" and state.last_forge_verdict == "pass":
                lesson = (
                    f"Found bug at {state.submitted_target!r} on contract "
                    f"{state.contract_name!r}: {state.submitted_evidence[:200]}"
                )
            elif terminal_reason == "give_up":
                lesson = f"Gave up on {state.contract_name!r}: {state.given_up_reason[:200]}"
            elif terminal_reason == "max_iter":
                lesson = (
                    f"Hit max_iter on {state.contract_name!r} — "
                    f"explored {state.distinct_tool_count()} distinct tools, "
                    f"no terminal verdict reached"
                )
            else:
                lesson = f"Terminated unclean ({terminal_reason}) on {state.contract_name!r}"
            memory_backend.save_episode(
                case_id=state.case_id,
                contract_name=state.contract_name,
                contract_source=case.get("contract_source", ""),
                tool_sequence=list(state.tools_called),
                terminal_reason=terminal_reason,
                forge_verdict=state.last_forge_verdict,
                lesson=lesson,
                target_function=(
                    state.submitted_target
                    or state.annotations.get("target_function", "")
                ),
            )
        except Exception:  # pragma: no cover - defensive (memory failure ≠ agent failure)
            pass

    finding_confirmed = (
        terminal_reason == "submit_finding"
        and state.last_forge_verdict == "pass"
    )

    return AgentResult(
        case_id=state.case_id,
        contract_name=state.contract_name,
        terminal_reason=terminal_reason,
        n_iterations=n_iterations,
        total_usd=round(state.case_usd, 4),
        state=state,
        trace=trace,
        finding_confirmed=finding_confirmed,
        target_function=state.submitted_target or state.annotations.get("target_function", ""),
        last_forge_verdict=state.last_forge_verdict,
        distinct_tool_count=state.distinct_tool_count(),
        recall_self_lesson_nonempty=state.recall_self_lesson_nonempty,
        annotations=dict(state.annotations),
    )


# CLI entrypoint for the Phase-1+2 ship-gate (1-case dry run)
def _cli_main() -> int:  # pragma: no cover
    import argparse
    import json as _json
    import sys as _sys
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Run ReAct agent on a single smoke case (Phase 1+2 dry-run)")
    ap.add_argument("--case-id", default="ACF-092", help="Smoke case ID (default ACF-092)")
    ap.add_argument(
        "--smoke-set",
        default="data/dataset/smoke_set.json",
        help="Smoke set JSON",
    )
    ap.add_argument("--max-iter", type=int, default=20)
    ap.add_argument("--max-usd", type=float, default=0.30)
    ap.add_argument("--out-dir", default="data/evaluation/react_dryrun")
    args = ap.parse_args()

    smoke = _json.loads(Path(args.smoke_set).read_text(encoding="utf-8"))
    case = next((c for c in smoke.get("cases", []) if c["id"] == args.case_id), None)
    if case is None:
        print(f"ERROR: case {args.case_id!r} not found in {args.smoke_set}", file=_sys.stderr)
        return 1

    print(f"[react-dryrun] case={args.case_id} ({case.get('contract_name')}) max_iter={args.max_iter} max_usd=${args.max_usd}")
    result = run_react_agent(
        case,
        memory_backend=None,  # Phase 1+2: memory not wired yet
        max_iter=args.max_iter,
        max_usd_per_case=args.max_usd,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.case_id}_trace.json").write_text(
        _json.dumps(result.trace.to_json(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / f"{args.case_id}_trace.md").write_text(
        result.trace.to_markdown(), encoding="utf-8"
    )

    print(f"\n[result] terminal={result.terminal_reason} iters={result.n_iterations} cost=${result.total_usd:.4f}")
    print(f"  target_function: {result.target_function!r}")
    print(f"  forge_verdict:   {result.last_forge_verdict!r}")
    print(f"  distinct_tools:  {result.distinct_tool_count}")
    print(f"  trace artifacts → {out_dir}/{args.case_id}_trace.{{json,md}}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli_main())
