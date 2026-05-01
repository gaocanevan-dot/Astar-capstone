"""Structured trace for the ReAct loop — per-step (thought, action,
observation) tuples + auto markdown export for AC8."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TraceStep:
    """One iteration of the ReAct loop."""

    step: int
    iso_ts: str

    # Assistant side (thought + action)
    thought: str = ""  # assistant.message.content (often empty for pure tool calls)
    tool_name: str = ""
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_call_id: str = ""

    # Tool side (observation)
    tool_result: str = ""  # serialized observation back to the model

    # Bookkeeping
    usd_cost_delta: float = 0.0
    error: str = ""


@dataclass
class Trace:
    """Full trace for a single case."""

    case_id: str
    contract_name: str
    started_iso: str
    steps: list[TraceStep] = field(default_factory=list)
    terminal_reason: str = ""  # submit_finding | give_up | max_iter | case_budget | malformed_circuit_breaker | llm_error
    total_usd: float = 0.0

    @classmethod
    def new(cls, case_id: str, contract_name: str) -> "Trace":
        return cls(
            case_id=case_id,
            contract_name=contract_name,
            started_iso=datetime.now(timezone.utc).isoformat(),
            steps=[],
        )

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)

    def to_json(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "contract_name": self.contract_name,
            "started_iso": self.started_iso,
            "terminal_reason": self.terminal_reason,
            "total_usd": round(self.total_usd, 4),
            "n_steps": len(self.steps),
            "steps": [asdict(s) for s in self.steps],
        }

    def to_markdown(self) -> str:
        """Day-5 AC8 — 1-page markdown trace per case."""
        lines: list[str] = [
            f"# Agent Trace — {self.case_id} ({self.contract_name})",
            "",
            f"- Started: `{self.started_iso}`",
            f"- Terminal: **{self.terminal_reason}**",
            f"- Total cost: **${self.total_usd:.4f}**",
            f"- Steps: {len(self.steps)}",
            "",
        ]
        for s in self.steps:
            lines.append(f"## Step {s.step}")
            lines.append("")
            if s.thought:
                lines.append(f"**Thought:** {s.thought.strip()[:600]}")
                lines.append("")
            if s.tool_name:
                args_preview = json.dumps(s.tool_args, ensure_ascii=False)[:400]
                lines.append(f"**Action:** `{s.tool_name}({args_preview})`")
                lines.append("")
            if s.tool_result:
                obs_preview = s.tool_result.strip()[:800]
                lines.append("**Observation:**")
                lines.append("")
                lines.append("```")
                lines.append(obs_preview)
                lines.append("```")
                lines.append("")
            if s.error:
                lines.append(f"**Error:** `{s.error}`")
                lines.append("")
            if s.usd_cost_delta:
                lines.append(f"_cost: +${s.usd_cost_delta:.4f}_")
                lines.append("")
        return "\n".join(lines)
