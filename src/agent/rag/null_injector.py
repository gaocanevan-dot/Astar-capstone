"""No-op injector — for baseline arms and zero-shot reference."""
from __future__ import annotations

from typing import Any, Mapping

from agent.rag.base import RAGInjector


class NullInjector(RAGInjector):
    """Injects nothing. Baseline arm uses this so the loop machinery
    stays uniform across arms (no special-case branching in loop.py)."""

    name = "null"

    def should_inject(self, case: Mapping[str, Any], state: Any, next_tool: str) -> bool:
        return False

    def build_payload(self, case: Mapping[str, Any], memory: Any) -> dict:
        return {"source": "null", "retrieved_ids": [], "rendered": ""}
