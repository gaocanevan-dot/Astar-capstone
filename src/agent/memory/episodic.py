"""Episodic memory — agent's own past audits.

Each episode = (case_id, contract signature, tool sequence, final verdict,
distilled lesson). Auto-written at the end of every agent run.

Retrieval: by contract signature (LOC + n_funcs + import_kind) → similar
past cases. Embedding text is a compact stringified signature.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agent.memory.store import MemoryEmbeddingIndex


class EpisodicStore:
    """Append-only episodic memory of agent's prior runs."""

    def __init__(
        self,
        jsonl_path: Path,
        cache_path: Optional[Path] = None,
        embedder_fn=None,
    ):
        self.index = MemoryEmbeddingIndex(jsonl_path, cache_path, embedder_fn)

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
        loc = (contract_source or "").count("\n") + 1 if contract_source else 0
        episode = {
            "id": f"{case_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "case_id": case_id,
            "contract_name": contract_name,
            "contract_signature": _signature(contract_source, contract_name),
            "loc": loc,
            "tool_sequence": tool_sequence,
            "terminal_reason": terminal_reason,
            "forge_verdict": forge_verdict,
            "target_function": target_function,
            "final_lesson": lesson,
            "iso_ts": datetime.now(timezone.utc).isoformat(),
            "embedding_text": _signature(contract_source, contract_name) + "\nlesson: " + (lesson or ""),
        }
        return self.index.append(episode)

    def query(self, case: dict, top_k: int = 3) -> list[dict]:
        sig = _signature(case.get("contract_source", ""), case.get("contract_name", ""))
        results = self.index.query(sig, top_k=top_k)
        return [
            {
                "case_id": payload.get("case_id", ""),
                "contract_name": payload.get("contract_name", ""),
                "terminal_reason": payload.get("terminal_reason", ""),
                "forge_verdict": payload.get("forge_verdict", ""),
                "target_function": payload.get("target_function", ""),
                "lesson": payload.get("final_lesson", ""),
                "score": round(score, 3),
            }
            for score, payload in results
        ]

    def __len__(self) -> int:
        return len(self.index)


def _signature(contract_source: str, contract_name: str) -> str:
    """Compact signature for episodic similarity."""
    if not contract_source:
        return contract_name or ""
    src = contract_source
    loc = src.count("\n") + 1
    has_oz = "@openzeppelin" in src
    has_solady = "solady/" in src
    has_sibling = "../" in src
    n_external = sum(src.count(f"function ") for _ in [0])  # rough fn count proxy
    n_external = src.count("function ")
    return (
        f"contract={contract_name} loc={loc} n_funcs={n_external} "
        f"has_oz={has_oz} has_solady={has_solady} has_sibling={has_sibling}"
    )
