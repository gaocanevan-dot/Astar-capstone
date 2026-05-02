"""Abstract RAG injector interface.

Designed for swap-in ablation. Day-6 ships AntiPatternInjector;
Day-7+ adds EpisodicInjector, HybridInjector, etc. without touching
loop.py — the loop only sees this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class RAGInjector(ABC):
    """System-mediated RAG content injector.

    Concrete subclasses decide WHEN to fire (`should_inject`) and WHAT
    to inject (`build_payload`). The loop is responsible for actually
    appending the synthetic messages to the conversation.

    Per AC15 (honest naming), every payload must carry a `source` field
    identifying it as system-injected, so post-hoc trace audit can
    distinguish from organic agent tool calls.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier for telemetry, narrative, and AC15 audit."""

    @abstractmethod
    def should_inject(
        self,
        case: Mapping[str, Any],
        state: Any,
        next_tool: str,
    ) -> bool:
        """Decide whether to fire injection at the current loop step.

        Args:
            case: the current case dict
            state: AgentState (must expose `rag_injection_fired` if used)
            next_tool: name of the LLM-proposed next tool call

        Returns:
            True iff this injector wants to insert content before the
            next LLM call. Loop calls `build_payload` only if True.
        """

    @abstractmethod
    def build_payload(
        self,
        case: Mapping[str, Any],
        memory: Any,
    ) -> dict:
        """Construct the synthetic injection payload.

        Returns a dict with at minimum:
            - source: str (e.g. "system_injection_at_propose") — per AC15
            - retrieved_ids: list[str] — for AC11 retrieval-quality verifier
            - rendered: str — the human-readable text shown to the LLM

        Loop appends this as a synthetic tool-result message before the
        next LLM call.
        """
