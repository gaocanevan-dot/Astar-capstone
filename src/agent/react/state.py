"""Per-case agent state for the ReAct loop.

Tracks running cost (for $0.30 per-case ceiling), malformed-tool-call streak
(for 3-strike circuit breaker), tools called (for AC2 evidence), and
intermediate observations (for trace export).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.state import AuditAnnotations, empty_annotations


@dataclass
class AgentState:
    """In-flight state of a single agent run on one case."""

    case_id: str
    contract_name: str
    annotations: AuditAnnotations = field(default_factory=lambda: dict(empty_annotations()))

    # R8 budget guard
    case_usd: float = 0.0

    # R8 malformed circuit breaker
    malformed_streak: int = 0

    # AC2 evidence — distinct tool diversity
    tools_called: list[str] = field(default_factory=list)

    # AC5b evidence — count of `recall_self_lesson` calls that returned ≥1 result
    recall_self_lesson_nonempty: int = 0

    # Day-5b AC9 mechanical — count of `try_next_candidate` invocations.
    # Counted whether the call comes from the agent (tool) or the system
    # (intercept after give_up under 5b-mandate). The mechanical AC9 verifier
    # divides this against `forge_calls_this_case` × first-fail to detect
    # whether cascade fired when it should have.
    cascade_invocations: int = 0
    cascade_was_system_forced: bool = False  # True iff system-intercept path

    # Terminal verdict from the agent itself (submit_finding / give_up payloads)
    submitted_target: str = ""
    submitted_evidence: str = ""
    submitted_hypothesis: str = ""
    given_up_reason: str = ""

    # If the agent ever ran forge during this case, the most recent verdict
    # (mirrors PipelineResult.execution_result for downstream comparison)
    last_forge_verdict: str = ""
    # Day-5b — first forge verdict (NEVER overwritten after first forge call).
    # Used by AC9 verifier to detect "cascade was needed" without inspecting
    # the full trace JSON.
    first_forge_verdict: str = ""

    def distinct_tool_count(self) -> int:
        return len(set(self.tools_called))
