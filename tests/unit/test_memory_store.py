"""Day-5 S2 — memory backend tests.

Mocks the embedder so tests are deterministic and zero-cost.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from agent.memory import Memory
from agent.memory.episodic import EpisodicStore
from agent.memory.patterns import PatternStore
from agent.memory.semantic import LessonStore
from agent.memory.store import EMBEDDING_DIM, MemoryEmbeddingIndex


def make_fake_embedder(text_to_vec_map: dict[str, list[float]] | None = None):
    """Returns embedder_fn that gives deterministic vectors per text.

    Default behaviour: hash-based vector that's stable across runs but
    distinguishes different inputs.
    """
    def _embed(texts):
        if not texts:
            return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
        out = np.zeros((len(texts), EMBEDDING_DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            if text_to_vec_map and t in text_to_vec_map:
                v = np.asarray(text_to_vec_map[t], dtype=np.float32)
                if v.shape[0] != EMBEDDING_DIM:
                    # Pad/truncate
                    full = np.zeros(EMBEDDING_DIM, dtype=np.float32)
                    full[: min(v.shape[0], EMBEDDING_DIM)] = v[: min(v.shape[0], EMBEDDING_DIM)]
                    v = full
            else:
                # Hash-based default
                rng = np.random.default_rng(hash(t) % (2**32))
                v = rng.standard_normal(EMBEDDING_DIM).astype(np.float32)
            n = float(np.linalg.norm(v))
            if n > 0:
                v = v / n
            out[i] = v
        return out

    return _embed


# ---------------------------------------------------------------------------
# MemoryEmbeddingIndex
# ---------------------------------------------------------------------------


class TestMemoryEmbeddingIndex:
    def test_append_and_query_roundtrip(self, tmp_path: Path):
        idx = MemoryEmbeddingIndex(
            tmp_path / "store.jsonl", embedder_fn=make_fake_embedder()
        )
        idx.append({"id": "a", "embedding_text": "hello world"})
        idx.append({"id": "b", "embedding_text": "different content"})
        idx.append({"id": "c", "embedding_text": "another doc"})
        results = idx.query("hello world", top_k=2)
        assert len(results) == 2
        # Best match should be "a" (exact text match)
        scores = {r[1]["id"]: r[0] for r in results}
        assert scores["a"] > scores.get("b", 0)

    def test_empty_store_returns_empty_query(self, tmp_path: Path):
        idx = MemoryEmbeddingIndex(
            tmp_path / "store.jsonl", embedder_fn=make_fake_embedder()
        )
        assert idx.query("anything") == []

    def test_jsonl_persistence(self, tmp_path: Path):
        path = tmp_path / "store.jsonl"
        idx = MemoryEmbeddingIndex(path, embedder_fn=make_fake_embedder())
        idx.append({"id": "x", "embedding_text": "first"})
        idx.append({"id": "y", "embedding_text": "second"})

        # Reload from a fresh instance
        idx2 = MemoryEmbeddingIndex(path, embedder_fn=make_fake_embedder())
        assert len(idx2) == 2
        assert {d["id"] for d in idx2.all_docs()} == {"x", "y"}

    def test_cache_invalidation_on_append(self, tmp_path: Path):
        idx = MemoryEmbeddingIndex(
            tmp_path / "store.jsonl", embedder_fn=make_fake_embedder()
        )
        idx.append({"id": "a", "embedding_text": "first"})
        # Build the index
        _ = idx.query("first", top_k=1)
        # Append a new doc — should invalidate
        idx.append({"id": "b", "embedding_text": "second"})
        # Query should now reflect both docs
        results = idx.query("second", top_k=2)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# PatternStore
# ---------------------------------------------------------------------------


class TestPatternStore:
    def test_add_and_query_pattern(self, tmp_path: Path):
        ps = PatternStore(tmp_path / "patterns.jsonl", embedder_fn=make_fake_embedder())
        ps.add_pattern({
            "id": "MISSING_MOD",
            "name": "Missing modifier on setter",
            "description": "External setter without onlyOwner",
            "indicators": ["external", "writes state"],
        })
        ps.add_pattern({
            "id": "REENTRANCY",
            "name": "Reentrancy on withdraw",
            "description": "External call before state update",
            "indicators": ["call", "before state"],
        })
        results = ps.query("missing modifier setter")
        assert len(results) >= 1
        assert results[0]["id"] in {"MISSING_MOD", "REENTRANCY"}
        assert "score" in results[0]

    def test_auto_builds_embedding_text(self, tmp_path: Path):
        ps = PatternStore(tmp_path / "p.jsonl", embedder_fn=make_fake_embedder())
        ps.add_pattern({"id": "X", "name": "X name", "description": "X desc"})
        # Should not crash on query (embedding_text was auto-built)
        results = ps.query("anything", top_k=1)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# EpisodicStore
# ---------------------------------------------------------------------------


class TestEpisodicStore:
    def test_save_and_query_episode(self, tmp_path: Path):
        es = EpisodicStore(tmp_path / "ep.jsonl", embedder_fn=make_fake_embedder())
        es.save_episode(
            case_id="ACF-1",
            contract_name="Foo",
            contract_source="contract Foo {\n function bar() external {} \n}",
            tool_sequence=["list_functions", "write_poc", "run_forge"],
            terminal_reason="submit_finding",
            forge_verdict="pass",
            lesson="bar lacked onlyOwner",
            target_function="bar",
        )
        es.save_episode(
            case_id="ACF-2",
            contract_name="Baz",
            contract_source="contract Baz {\n function qux() external {} \n}",
            tool_sequence=["give_up"],
            terminal_reason="give_up",
            forge_verdict="",
            lesson="too many imports",
        )
        results = es.query({"contract_source": "contract Foo {\n }", "contract_name": "Foo"}, top_k=2)
        assert len(results) >= 1
        case_ids = {r["case_id"] for r in results}
        assert "ACF-1" in case_ids


# ---------------------------------------------------------------------------
# LessonStore
# ---------------------------------------------------------------------------


class TestLessonStore:
    def test_save_new_lesson(self, tmp_path: Path):
        ls = LessonStore(tmp_path / "l.jsonl", embedder_fn=make_fake_embedder())
        result = ls.save_lesson("trigger A", "takeaway A", source_case_id="C-1")
        assert result["saved"] is True
        assert result["deduplicated"] is False
        assert len(ls) == 1

    def test_dedup_bumps_freq_on_near_duplicate(self, tmp_path: Path):
        # Force two near-duplicate lessons to embed identically via fake embedder
        text_a = "trigger A | takeaway A"
        # Hash collision via shared map
        same_vec = [1.0] + [0.0] * (EMBEDDING_DIM - 1)
        embedder = make_fake_embedder({text_a: same_vec, "trigger A2 | takeaway A": same_vec})
        ls = LessonStore(tmp_path / "l.jsonl", embedder_fn=embedder, dedup_threshold=0.5)
        ls.save_lesson("trigger A", "takeaway A", source_case_id="C-1")
        result = ls.save_lesson("trigger A2", "takeaway A", source_case_id="C-2")
        assert result["deduplicated"] is True
        assert result["freq"] == 2
        assert len(ls) == 1  # still one lesson, just bumped

    def test_save_lesson_rejects_empty(self, tmp_path: Path):
        ls = LessonStore(tmp_path / "l.jsonl", embedder_fn=make_fake_embedder())
        result = ls.save_lesson("", "takeaway")
        assert result["saved"] is False


# ---------------------------------------------------------------------------
# Memory facade
# ---------------------------------------------------------------------------


class TestMemoryFacade:
    def test_facade_routes_to_correct_stores(self, tmp_path: Path):
        mem = Memory(tmp_path / "memory", embedder_fn=make_fake_embedder())
        mem.patterns.add_pattern({"id": "P1", "name": "p1", "description": "missing modifier setter"})
        mem.save_lesson("trigger", "takeaway", source_case_id="C-1")
        mem.save_episode(
            case_id="C-1",
            contract_name="Foo",
            contract_source="contract Foo {}",
            tool_sequence=["a", "b"],
            terminal_reason="submit_finding",
            forge_verdict="pass",
            lesson="fixed",
        )

        stats = mem.stats()
        assert stats["n_patterns"] == 1
        assert stats["n_lessons"] == 1
        assert stats["n_episodes"] == 1

        # Verify recall paths
        ap = mem.recall_anti_pattern("missing modifier")
        assert len(ap) == 1
        sl = mem.recall_self_lesson("trigger")
        assert len(sl) == 1
        sc = mem.recall_similar_cases({"contract_source": "contract Foo {}", "contract_name": "Foo"})
        assert len(sc) == 1
