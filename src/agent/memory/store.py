"""Generic embedding-backed JSONL store for the agent's long-term memory.

Each store keeps:
- A JSONL file at `<root>/<name>.jsonl` (append-only, human-readable)
- A sidecar `<root>/<name>.embcache.npz` with one embedding per doc

`text-embedding-3-small` ($0.02/1M tokens) is the default. Indexing 100 docs
costs roughly $0.001. Per-query cost ~$0.00002.

This module is import-cheap. Embedding is lazy: first `query()` builds the
index; `save()` invalidates it. Tests can inject a fake embedder.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np


EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536  # text-embedding-3-small dimension


@dataclass
class StoredDoc:
    """One document in a memory store."""

    doc_id: str
    text_for_embedding: str
    payload: dict[str, Any]  # serialized to JSONL


def _openai_embed(texts: list[str]) -> np.ndarray:
    """Default embedder using OpenAI text-embedding-3-small. Returns
    L2-normalized (n_docs, EMBEDDING_DIM) array.
    """
    if not texts:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
    from agent.adapters.llm import get_client

    client = get_client()
    # OpenAI embedding API supports up to 2048 inputs per request
    chunks: list[list[str]] = []
    for i in range(0, len(texts), 256):
        chunks.append(texts[i:i + 256])
    all_vecs: list[np.ndarray] = []
    for chunk in chunks:
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=chunk)
        for d in resp.data:
            v = np.asarray(d.embedding, dtype=np.float32)
            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n
            all_vecs.append(v)
    return np.stack(all_vecs, axis=0)


class MemoryEmbeddingIndex:
    """JSONL-backed, embedding-indexed document store.

    `embedder_fn(texts) -> np.ndarray` is injectable for tests. Production
    uses the OpenAI embedding API via the lazy `_openai_embed` import above.
    """

    def __init__(
        self,
        jsonl_path: Path,
        cache_path: Optional[Path] = None,
        embedder_fn: Optional[Callable[[list[str]], np.ndarray]] = None,
    ):
        self.jsonl_path = Path(jsonl_path)
        self.cache_path = Path(cache_path) if cache_path else self.jsonl_path.with_suffix(".embcache.npz")
        self._embedder = embedder_fn or _openai_embed
        self._docs: list[StoredDoc] = []
        self._matrix: Optional[np.ndarray] = None  # shape (n_docs, dim)
        self._dirty = False  # True if docs added since last index build
        self._loaded = False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._docs = []
        if self.jsonl_path.exists():
            for line in self.jsonl_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                doc_id = payload.get("id") or payload.get("doc_id") or ""
                text = payload.get("embedding_text") or payload.get("text", "")
                self._docs.append(StoredDoc(doc_id=doc_id, text_for_embedding=text, payload=payload))
        self._loaded = True

    def append(self, doc: dict) -> str:
        """Append a doc to the JSONL. Caller must ensure `id` and
        `embedding_text` keys are present (or compatible field names)."""
        self._ensure_loaded()
        doc_id = doc.get("id") or doc.get("doc_id") or ""
        text = doc.get("embedding_text") or doc.get("text", "")
        self._docs.append(StoredDoc(doc_id=doc_id, text_for_embedding=text, payload=doc))
        self._dirty = True
        # Also append to file immediately (durability)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        return doc_id

    def all_docs(self) -> list[dict]:
        self._ensure_loaded()
        return [d.payload for d in self._docs]

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._docs)

    # ------------------------------------------------------------------
    # Embedding index
    # ------------------------------------------------------------------

    def _try_load_cache(self) -> bool:
        if not self.cache_path.exists():
            return False
        try:
            data = np.load(self.cache_path, allow_pickle=False)
            ids = data["ids"].tolist()
            matrix = data["matrix"]
        except Exception:
            return False
        # Cache is valid only if doc IDs match (order matters)
        current_ids = [d.doc_id for d in self._docs]
        if list(ids) != current_ids:
            return False
        self._matrix = matrix.astype(np.float32, copy=False)
        return True

    def _save_cache(self) -> None:
        if self._matrix is None:
            return
        ids = np.array([d.doc_id for d in self._docs], dtype=object)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.cache_path, ids=ids, matrix=self._matrix)

    def index(self) -> None:
        """Build (or refresh) the embedding matrix. Skips if cache valid."""
        self._ensure_loaded()
        if not self._docs:
            self._matrix = np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
            return
        if not self._dirty and self._try_load_cache():
            return
        texts = [d.text_for_embedding for d in self._docs]
        self._matrix = self._embedder(texts)
        self._dirty = False
        self._save_cache()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, query_text: str, top_k: int = 3) -> list[tuple[float, dict]]:
        """Cosine-similarity top-k. Returns [(score, payload), ...]."""
        self._ensure_loaded()
        if not self._docs:
            return []
        if self._matrix is None or self._dirty:
            self.index()
        q_vec = self._embedder([query_text])[0]
        # Already L2-normalized in _openai_embed; matrix too. So dot = cosine.
        sims = self._matrix @ q_vec  # (n_docs,)
        # Top-k
        if top_k >= len(sims):
            top_idx = np.argsort(-sims)
        else:
            top_idx = np.argpartition(-sims, top_k)[:top_k]
            top_idx = top_idx[np.argsort(-sims[top_idx])]
        return [(float(sims[i]), self._docs[i].payload) for i in top_idx[:top_k]]
