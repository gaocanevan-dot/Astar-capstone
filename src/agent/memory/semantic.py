"""Self-lesson store — agent-distilled rules of thumb.

Each lesson: (trigger, takeaway, freq, first_seen_iso, last_seen_iso).
Cosine-dedup at 0.92 — if a near-duplicate already exists, increment freq
instead of appending.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent.memory.store import MemoryEmbeddingIndex


# Cosine-dedup threshold (tuned conservative — high enough to allow rephrases)
DEDUP_THRESHOLD = 0.92


class LessonStore:
    """Self-distilled rules of thumb with cosine-dedup."""

    def __init__(
        self,
        jsonl_path: Path,
        cache_path: Optional[Path] = None,
        embedder_fn=None,
        dedup_threshold: float = DEDUP_THRESHOLD,
    ):
        self.index = MemoryEmbeddingIndex(jsonl_path, cache_path, embedder_fn)
        self.dedup_threshold = dedup_threshold

    def save_lesson(
        self,
        trigger: str,
        takeaway: str,
        source_case_id: Optional[str] = None,
    ) -> dict:
        """Append a new lesson, OR if a near-duplicate exists, bump its freq."""
        trigger = (trigger or "").strip()[:200]
        takeaway = (takeaway or "").strip()[:400]
        if not trigger or not takeaway:
            return {"saved": False, "reason": "trigger and takeaway required"}

        embedding_text = trigger + " | " + takeaway

        # Dedup check (only if existing docs)
        if len(self.index) > 0:
            existing = self.index.query(embedding_text, top_k=1)
            if existing:
                score, payload = existing[0]
                if score >= self.dedup_threshold:
                    # Bump the existing lesson's freq + last_seen
                    return self._bump_existing(payload, source_case_id)

        # New lesson
        now_iso = datetime.now(timezone.utc).isoformat()
        lesson_id = f"lesson_{len(self.index) + 1:04d}"
        lesson = {
            "id": lesson_id,
            "trigger": trigger,
            "takeaway": takeaway,
            "freq": 1,
            "first_seen_iso": now_iso,
            "last_seen_iso": now_iso,
            "source_case_ids": [source_case_id] if source_case_id else [],
            "embedding_text": embedding_text,
        }
        self.index.append(lesson)
        return {"saved": True, "deduplicated": False, "lesson_id": lesson_id, "freq": 1}

    def _bump_existing(self, payload: dict, source_case_id: Optional[str]) -> dict:
        """A near-duplicate already exists; increment freq + update last_seen.

        Note: `payload` is the SAME object reference as the matching doc in
        `self.index._docs[*].payload` (query returns the underlying dict, not
        a copy). So we capture the new freq BEFORE mutating to avoid the
        return value double-counting.

        Simple impl rewrites the JSONL on bump. For a ~100-lesson corpus on
        capstone scope, this is cheap.
        """
        all_docs = self.index.all_docs()
        target_id = payload.get("id")
        now_iso = datetime.now(timezone.utc).isoformat()
        new_freq = int(payload.get("freq", 1)) + 1  # capture before mutation
        updated = False
        for doc in all_docs:
            if doc.get("id") == target_id:
                doc["freq"] = new_freq
                doc["last_seen_iso"] = now_iso
                if source_case_id and source_case_id not in (doc.get("source_case_ids") or []):
                    doc.setdefault("source_case_ids", []).append(source_case_id)
                updated = True
                break

        if updated:
            # Rewrite jsonl + invalidate cache
            self.index.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            import json as _json

            with self.index.jsonl_path.open("w", encoding="utf-8") as f:
                for doc in all_docs:
                    f.write(_json.dumps(doc, ensure_ascii=False) + "\n")
            # Clear in-memory state so next query reloads
            self.index._loaded = False
            self.index._dirty = True
            self.index._matrix = None
        return {
            "saved": True,
            "deduplicated": True,
            "lesson_id": target_id,
            "freq": new_freq,
        }

    def query(self, q: str, top_k: int = 3) -> list[dict]:
        results = self.index.query(q, top_k=top_k)
        return [
            {
                "id": payload.get("id", ""),
                "trigger": payload.get("trigger", ""),
                "takeaway": payload.get("takeaway", ""),
                "freq": payload.get("freq", 1),
                "score": round(score, 3),
            }
            for score, payload in results
        ]

    def __len__(self) -> int:
        return len(self.index)
