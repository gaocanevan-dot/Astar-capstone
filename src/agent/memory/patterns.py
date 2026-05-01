"""Anti-pattern store — replaces the old `case-level` RAG with pattern-level
retrieval. Indexed once at bootstrap from the curated rag corpus + any
agent-discovered patterns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agent.memory.store import MemoryEmbeddingIndex


class PatternStore:
    """Read-mostly anti-pattern memory (writes only at bootstrap).

    Each entry: {
        "id": "MISSING_MOD_SETTER",
        "name": "Missing modifier on state-changing setter",
        "description": "...",
        "indicators": ["external visibility", "writes state", "no onlyOwner"],
        "exploit_template": "vm.prank(attacker); target.setOwner(attacker);",
        "embedding_text": "<concat of name + description + indicators>"
    }
    """

    def __init__(
        self,
        jsonl_path: Path,
        cache_path: Optional[Path] = None,
        embedder_fn=None,
    ):
        self.index = MemoryEmbeddingIndex(jsonl_path, cache_path, embedder_fn)

    def add_pattern(self, pattern: dict) -> str:
        if "embedding_text" not in pattern:
            pattern = dict(pattern)
            pattern["embedding_text"] = _build_embedding_text(pattern)
        return self.index.append(pattern)

    def query(self, q: str, top_k: int = 3) -> list[dict]:
        results = self.index.query(q, top_k=top_k)
        return [
            {
                "id": payload.get("id", ""),
                "name": payload.get("name", ""),
                "description": payload.get("description", ""),
                "indicators": payload.get("indicators", []),
                "exploit_template": payload.get("exploit_template", ""),
                "score": round(score, 3),
            }
            for score, payload in results
        ]

    def __len__(self) -> int:
        return len(self.index)


def _build_embedding_text(pattern: dict[str, Any]) -> str:
    parts = []
    if pattern.get("name"):
        parts.append(pattern["name"])
    if pattern.get("description"):
        parts.append(pattern["description"])
    inds = pattern.get("indicators", [])
    if inds:
        parts.append("indicators: " + "; ".join(inds))
    return "\n".join(parts)
