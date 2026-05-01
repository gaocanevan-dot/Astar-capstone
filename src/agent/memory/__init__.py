"""Day-5 long-term memory layer.

Three stores:
- `PatternStore`     — anti-patterns (semantic, curated + agent-extended)
- `EpisodicStore`    — agent's own past audit traces
- `LessonStore`      — agent-distilled rules of thumb (with cosine-dedup)

Public facade: `Memory` class with the 4 tool-facing methods that
`agent.react.tools` expects:
    - recall_anti_pattern(query, top_k)
    - recall_similar_cases(case, top_k)
    - recall_self_lesson(query, top_k)
    - save_lesson(trigger, takeaway, source_case_id)

Plus internal:
    - save_episode(case_id, ...) — auto-called by the agent loop on terminate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agent.memory.episodic import EpisodicStore
from agent.memory.patterns import PatternStore
from agent.memory.semantic import LessonStore
from agent.memory.store import MemoryEmbeddingIndex

__all__ = [
    "Memory",
    "PatternStore",
    "EpisodicStore",
    "LessonStore",
    "MemoryEmbeddingIndex",
]


class Memory:
    """Facade tying the three stores together for the ReAct agent."""

    def __init__(
        self,
        root: Path,
        embedder_fn=None,
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.patterns = PatternStore(
            self.root / "anti_patterns.jsonl",
            embedder_fn=embedder_fn,
        )
        self.episodic = EpisodicStore(
            self.root / "episodic.jsonl",
            embedder_fn=embedder_fn,
        )
        self.lessons = LessonStore(
            self.root / "self_lessons.jsonl",
            embedder_fn=embedder_fn,
        )

    # ---- Tool-facing API (called from agent.react.tools) ----

    def recall_anti_pattern(self, query: str, top_k: int = 3) -> list[dict]:
        return self.patterns.query(query, top_k=top_k)

    def recall_similar_cases(self, case: dict, top_k: int = 3) -> list[dict]:
        return self.episodic.query(case, top_k=top_k)

    def recall_self_lesson(self, query: str, top_k: int = 3) -> list[dict]:
        return self.lessons.query(query, top_k=top_k)

    def save_lesson(
        self,
        trigger: str,
        takeaway: str,
        source_case_id: Optional[str] = None,
    ) -> dict:
        return self.lessons.save_lesson(trigger, takeaway, source_case_id=source_case_id)

    def save_episode(
        self,
        *,
        case_id: str,
        contract_name: str,
        contract_source: str,
        tool_sequence: list[str],
        terminal_reason: str,
        forge_verdict: str,
        lesson: str,
        target_function: str = "",
    ) -> str:
        return self.episodic.save_episode(
            case_id=case_id,
            contract_name=contract_name,
            contract_source=contract_source,
            tool_sequence=tool_sequence,
            terminal_reason=terminal_reason,
            forge_verdict=forge_verdict,
            lesson=lesson,
            target_function=target_function,
        )

    def stats(self) -> dict[str, Any]:
        return {
            "n_patterns": len(self.patterns),
            "n_episodes": len(self.episodic),
            "n_lessons": len(self.lessons),
        }
