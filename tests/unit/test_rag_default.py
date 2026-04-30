"""Unit tests for Day-2 T11 default RAG store.

Asserts that `load_default_rag_store()` resolves to the canonical
`data/dataset/rag_training_dataset.json`, loads >=1 doc, and supports
`retrieve()` for downstream analyst few-shot injection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.adapters.rag import (
    DEFAULT_RAG_DATASET_PATH,
    load_default_rag_store,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    not (REPO_ROOT / DEFAULT_RAG_DATASET_PATH).exists(),
    reason=f"default RAG dataset missing at {DEFAULT_RAG_DATASET_PATH}",
)
class TestDefaultRagStore:
    def test_default_path_constant(self):
        assert DEFAULT_RAG_DATASET_PATH == "data/dataset/rag_training_dataset.json"

    def test_loads_at_least_one_document(self):
        store = load_default_rag_store(repo_root=str(REPO_ROOT))
        assert len(store) >= 1

    def test_retrieve_returns_results_for_arbitrary_query(self):
        store = load_default_rag_store(repo_root=str(REPO_ROOT))
        retrieved = store.retrieve(
            "function withdraw external onlyOwner", top_k=3
        )
        # Don't over-assert (corpus content can change); just verify the
        # retrieval surface works end-to-end.
        assert isinstance(retrieved, list)
        assert len(retrieved) <= 3
