"""Lightweight RAG retriever — TF-IDF cosine similarity over a corpus of
known-good cases. Supports leave-one-out by case_id.

Deliberately NOT using Chroma/sentence-transformers for this baseline —
TF-IDF on Solidity tokens is fast, deterministic, and dependency-light.
Upgrade path is a single-class swap.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable


_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tokenize(text: str) -> list[str]:
    """Split Solidity source into lowercased identifier tokens."""
    return [tok.lower() for tok in _TOKEN_RE.findall(text or "")]


@dataclass
class RagCase:
    case_id: str
    contract_name: str
    vulnerable_function: str
    hypothesis: str
    contract_snippet: str  # truncated source for few-shot context
    _tokens: list[str] = field(default_factory=list, repr=False)
    _tf: Counter = field(default_factory=Counter, repr=False)


@dataclass
class RetrievedCase:
    case: RagCase
    score: float


class TfidfRagStore:
    """In-memory TF-IDF retriever. Call `index()` once after adding cases."""

    def __init__(self):
        self._cases: list[RagCase] = []
        self._idf: dict[str, float] = {}
        self._indexed = False

    def add(self, case: RagCase) -> None:
        case._tokens = _tokenize(case.contract_snippet + " " + case.hypothesis)
        case._tf = Counter(case._tokens)
        self._cases.append(case)
        self._indexed = False

    def index(self) -> None:
        df: Counter[str] = Counter()
        for case in self._cases:
            df.update(set(case._tokens))
        n = len(self._cases) or 1
        self._idf = {term: math.log((n + 1) / (freq + 1)) + 1 for term, freq in df.items()}
        self._indexed = True

    def _tfidf_vec(self, tokens: Iterable[str]) -> dict[str, float]:
        tf = Counter(tokens)
        return {t: c * self._idf.get(t, 1.0) for t, c in tf.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        dot = sum(a[t] * b[t] for t in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def retrieve(
        self,
        query_source: str,
        top_k: int = 3,
        exclude_id: str | None = None,
    ) -> list[RetrievedCase]:
        """Return top_k cases by cosine similarity. `exclude_id` implements
        leave-one-out for self-evaluation."""
        if not self._indexed:
            self.index()
        query_tokens = _tokenize(query_source)
        qvec = self._tfidf_vec(query_tokens)
        scored: list[RetrievedCase] = []
        for case in self._cases:
            if exclude_id and case.case_id == exclude_id:
                continue
            cvec = self._tfidf_vec(case._tokens)
            score = self._cosine(qvec, cvec)
            if score > 0:
                scored.append(RetrievedCase(case=case, score=score))
        scored.sort(key=lambda x: -x.score)
        return scored[:top_k]

    def __len__(self) -> int:
        return len(self._cases)


def load_store_from_predictions(
    predictions_path: str,
    eval_set_path: str = "data/dataset/eval_set.json",
) -> TfidfRagStore:
    """Build a store from a prior run's strict-hit cases.

    Cross-references `single_agent_predictions.json` (has predicted / GT) with
    `eval_set.json` (has source) to assemble RagCase objects.
    """
    import json
    from pathlib import Path

    preds = json.loads(Path(predictions_path).read_text(encoding="utf-8"))
    hit_ids = {
        p["case_id"]
        for p in preds
        if (p.get("predicted_function") or "")
        and p["predicted_function"] == (p.get("ground_truth_function") or "")
    }

    eval_data = json.loads(Path(eval_set_path).read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in eval_data.get("cases", [])}

    store = TfidfRagStore()
    for case_id in hit_ids:
        c = by_id.get(case_id)
        if not c:
            continue
        store.add(
            RagCase(
                case_id=case_id,
                contract_name=c.get("contract_name", ""),
                vulnerable_function=c.get("vulnerable_function") or "",
                hypothesis=(c.get("description", "") or "")[:500],
                contract_snippet=(c.get("contract_source", "") or "")[:4000],
            )
        )
    store.index()
    return store


# Day-2 T11: canonical RAG dataset path. The 85-doc curated AC pattern
# corpus is the new default; manual hand-authored library (DEF1) is opt-in.
DEFAULT_RAG_DATASET_PATH = "data/dataset/rag_training_dataset.json"


def load_default_rag_store(repo_root: str | None = None) -> TfidfRagStore:
    """Day-2 T11 — load the default TF-IDF RAG store.

    Resolves `DEFAULT_RAG_DATASET_PATH` against `repo_root` (default: cwd).
    Returns an indexed `TfidfRagStore` ready for `.retrieve()`.
    """
    from pathlib import Path

    base = Path(repo_root) if repo_root else Path.cwd()
    path = base / DEFAULT_RAG_DATASET_PATH
    return load_store_from_rag_dataset(str(path))


def load_store_from_rag_dataset(path: str) -> TfidfRagStore:
    """Build a RAG store from a curated dataset file (documents format).

    Expected top-level structure:
        {"metadata": {...}, "documents": [{"id", "content", "metadata": {...}}]}

    Each document becomes one RagCase. LOO remains available via `exclude_id`
    at retrieve time. Used when we want a larger / cleaner RAG corpus than the
    self-training "strict hits" corpus.
    """
    import json
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    docs = data.get("documents", [])
    store = TfidfRagStore()
    for doc in docs:
        meta = doc.get("metadata", {}) or {}
        snippet = (
            (meta.get("code_snippet") or "") + "\n"
            + (doc.get("content") or "")
        )[:4000]
        hypothesis = " ".join(
            p for p in (meta.get("description"), meta.get("missing_check")) if p
        )[:500]
        store.add(
            RagCase(
                case_id=doc.get("id") or meta.get("id") or "",
                contract_name=meta.get("contract_name") or "",
                vulnerable_function=meta.get("function") or meta.get("functions") or "",
                hypothesis=hypothesis,
                contract_snippet=snippet,
            )
        )
    store.index()
    return store


def build_store_from_hits(hits_json: list[dict]) -> TfidfRagStore:
    """Construct a RAG store from run_single_agent_predictions.json entries
    that were strict hits (ground_truth_function matched predicted_function).

    Used by analyst.py when US-008 context injection is enabled.
    """
    store = TfidfRagStore()
    for row in hits_json:
        if not row.get("strict_hit") and not (
            row.get("predicted_function") and row.get("ground_truth_function")
            and row["predicted_function"] == row["ground_truth_function"]
        ):
            continue
        snippet = row.get("contract_source", "")[:4000]
        store.add(
            RagCase(
                case_id=row["case_id"],
                contract_name=row.get("contract_name", ""),
                vulnerable_function=row.get("ground_truth_function", ""),
                hypothesis=row.get("hypothesis", "") or row.get("reasoning", ""),
                contract_snippet=snippet,
            )
        )
    store.index()
    return store


def format_few_shot_context(retrieved: list[RetrievedCase]) -> str:
    """Format retrieved cases as a few-shot prompt section."""
    if not retrieved:
        return ""
    parts = ["# Similar known-vulnerable cases (for reference):"]
    for i, rc in enumerate(retrieved, 1):
        parts.append(
            f"\n## Example {i} (similarity={rc.score:.2f}, project={rc.case.contract_name})"
            f"\nVulnerable function: `{rc.case.vulnerable_function}`"
            f"\nHypothesis: {rc.case.hypothesis}"
        )
    return "\n".join(parts)


# =============================================================================
# Embedding-based RAG (OpenAI text-embedding-3-small)
# =============================================================================

class EmbeddingRagStore:
    """RAG store backed by OpenAI text-embedding-3-small.

    Same external interface as TfidfRagStore (`add`, `index`, `retrieve`,
    `__len__`) so it's a drop-in replacement at call sites.

    Behaviors:
    - Lazy index: first `retrieve()` call triggers `index()` if needed.
    - Disk cache: when `cache_path` is provided, embeddings are saved as
      compressed npz keyed on (model_name, ordered list of case_ids). Re-runs
      with the same corpus skip the API call entirely.
    - Cosine similarity via L2-normalized dot product (vectors stored
      pre-normalized, so retrieval is a single matrix-vector multiply).
    """

    DEFAULT_MODEL = "text-embedding-3-small"
    BATCH_SIZE = 256  # well under OpenAI 2048 limit, friendly to rate limit

    def __init__(
        self,
        model: str | None = None,
        cache_path: str | None = None,
    ):
        self._cases: list[RagCase] = []
        self._vecs = None  # type: ignore[assignment]  # numpy.ndarray (n, dim) once indexed
        self._model = model or self.DEFAULT_MODEL
        self._cache_path = cache_path
        self._client = None
        self._indexed = False

    def add(self, case: RagCase) -> None:
        self._cases.append(case)
        self._indexed = False

    def __len__(self) -> int:
        return len(self._cases)

    def _format_for_embedding(self, case: RagCase) -> str:
        """Concatenate the most retrieval-relevant fields into one input."""
        return (
            f"Contract: {case.contract_name}\n"
            f"Vulnerable function: {case.vulnerable_function}\n"
            f"Hypothesis: {case.hypothesis}\n"
            f"Code:\n{case.contract_snippet}"
        )

    def _get_client(self):
        if self._client is None:
            from agent.adapters.llm import get_client
            self._client = get_client()
        return self._client

    def _try_load_cache(self) -> bool:
        if not self._cache_path:
            return False
        from pathlib import Path
        p = Path(self._cache_path)
        if not p.exists():
            return False
        try:
            import numpy as np
            cached = np.load(p, allow_pickle=False)
            cached_ids = list(cached["ids"])
            cached_model = str(cached["model"].item()) if "model" in cached.files else ""
            cur_ids = [c.case_id for c in self._cases]
            if cached_ids == cur_ids and cached_model == self._model:
                self._vecs = cached["vecs"].astype(np.float32)
                self._indexed = True
                return True
        except Exception:
            pass
        return False

    def _save_cache(self) -> None:
        if not self._cache_path:
            return
        from pathlib import Path
        import numpy as np
        Path(self._cache_path).parent.mkdir(parents=True, exist_ok=True)
        ids = np.array([c.case_id for c in self._cases])
        np.savez_compressed(
            self._cache_path,
            ids=ids,
            vecs=self._vecs,
            model=np.array(self._model),
        )

    def index(self) -> None:
        """Compute (or load cached) embeddings for the corpus."""
        if self._indexed:
            return
        if self._try_load_cache():
            return

        import numpy as np
        client = self._get_client()
        texts = [self._format_for_embedding(c) for c in self._cases]
        all_vecs: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            resp = client.embeddings.create(input=batch, model=self._model)
            all_vecs.extend(d.embedding for d in resp.data)
        vecs = np.array(all_vecs, dtype=np.float32)
        # L2-normalize so retrieval can use plain dot product as cosine
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._vecs = vecs / norms
        self._indexed = True
        self._save_cache()

    def retrieve(
        self,
        query_source: str,
        top_k: int = 3,
        exclude_id: str | None = None,
        min_score: float = 0.0,
    ) -> list[RetrievedCase]:
        """Return top_k cases by cosine similarity. `exclude_id` implements
        leave-one-out for self-evaluation. `min_score` gates out low-relevance
        retrievals (set > 0 to enable confidence-gated RAG)."""
        if not self._indexed:
            self.index()
        if self._vecs is None or len(self._cases) == 0:
            return []

        import numpy as np
        client = self._get_client()
        # Embed the query (truncate to keep within context if huge)
        q_text = f"Code:\n{query_source[:8000]}"
        resp = client.embeddings.create(input=[q_text], model=self._model)
        q_vec = np.array(resp.data[0].embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []
        q_vec = q_vec / q_norm

        sims = self._vecs @ q_vec  # (n,)
        # Apply leave-one-out
        if exclude_id:
            for i, c in enumerate(self._cases):
                if c.case_id == exclude_id:
                    sims[i] = -1.0
        # Take top-k by similarity
        idx = np.argsort(-sims)[:top_k]
        return [
            RetrievedCase(case=self._cases[i], score=float(sims[i]))
            for i in idx
            if sims[i] >= min_score
        ]


def load_embedding_store_from_rag_dataset(
    path: str,
    model: str | None = None,
    cache_path: str | None = None,
) -> EmbeddingRagStore:
    """Build an embedding-backed RAG store from the curated dataset (documents
    format). Same input format as `load_store_from_rag_dataset`.
    """
    import json
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    docs = data.get("documents", [])
    # Default cache path co-located with dataset for easy reuse
    if cache_path is None:
        ds_path = Path(path)
        cache_path = str(ds_path.parent / f".{ds_path.stem}.embcache.npz")
    store = EmbeddingRagStore(model=model, cache_path=cache_path)
    for doc in docs:
        meta = doc.get("metadata", {}) or {}
        snippet = (
            (meta.get("code_snippet") or "") + "\n" + (doc.get("content") or "")
        )[:4000]
        hypothesis = " ".join(
            p for p in (meta.get("description"), meta.get("missing_check")) if p
        )[:500]
        store.add(
            RagCase(
                case_id=doc.get("id") or meta.get("id") or "",
                contract_name=meta.get("contract_name") or "",
                vulnerable_function=meta.get("function") or meta.get("functions") or "",
                hypothesis=hypothesis,
                contract_snippet=snippet,
            )
        )
    return store
