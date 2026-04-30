"""Unit tests for TfidfRagStore (RAG adapter).

Covers: TF-IDF indexing, cosine retrieval, leave-one-out exclusion.
No external deps (no Chroma, no sentence-transformers) — pure arithmetic.
"""

from agent.adapters.rag import RagCase, TfidfRagStore, format_few_shot_context


def _mk(case_id, fn, snippet):
    return RagCase(
        case_id=case_id,
        contract_name=case_id,
        vulnerable_function=fn,
        hypothesis=f"issue with {fn}",
        contract_snippet=snippet,
    )


def _store(cases):
    s = TfidfRagStore()
    for c in cases:
        s.add(c)
    s.index()
    return s


def test_empty_store_returns_empty_list():
    s = TfidfRagStore()
    s.index()
    assert s.retrieve("any query") == []


def test_retrieve_highest_similarity_first():
    s = _store([
        _mk("c1", "withdraw", "contract Vault { function withdraw() external {} }"),
        _mk("c2", "mint", "contract Token { function mint() external {} }"),
        _mk("c3", "swap", "contract Pool { function swap() external {} }"),
    ])
    r = s.retrieve("contract X { function withdraw() external {} }", top_k=2)
    assert len(r) >= 1
    # c1 should dominate since "withdraw" + "vault" tokens match
    assert r[0].case.case_id == "c1"


def test_loo_excludes_same_id():
    s = _store([
        _mk("c1", "burn", "contract T { function burn() external {} }"),
        _mk("c2", "approve", "contract U { function approve() external {} }"),
    ])
    r = s.retrieve("contract T { function burn() external {} }", top_k=3, exclude_id="c1")
    ids = [x.case.case_id for x in r]
    assert "c1" not in ids


def test_top_k_honored():
    s = _store([
        _mk(f"c{i}", "fn", f"contract C{i} {{ function foo() external {{}} }}")
        for i in range(10)
    ])
    r = s.retrieve("contract X { function foo() external {} }", top_k=3)
    assert len(r) <= 3


def test_zero_score_cases_filtered():
    """Query with zero token overlap should yield no results (cosine=0)."""
    s = _store([
        _mk("c1", "foo", "aaaa bbbb cccc dddd")
    ])
    r = s.retrieve("xxxx yyyy zzzz")
    assert r == []


def test_format_few_shot_empty():
    assert format_few_shot_context([]) == ""


def test_format_few_shot_has_hypothesis_and_function():
    s = _store([
        _mk("c1", "withdraw", "contract Vault { function withdraw() external {} }")
    ])
    r = s.retrieve("contract X { function withdraw() external {} }", top_k=1)
    text = format_few_shot_context(r)
    assert "withdraw" in text
    assert "Example 1" in text
    assert "similarity" in text


def test_len_reports_corpus_size():
    s = _store([_mk("c1", "f", "c c"), _mk("c2", "g", "c c c"), _mk("c3", "h", "c c c c")])
    assert len(s) == 3


def test_load_store_from_predictions(tmp_path):
    """load_store_from_predictions: cross-ref strict-hit predictions with
    eval_set to build an in-memory corpus."""
    import json
    from agent.adapters.rag import load_store_from_predictions

    preds = [
        # strict hit
        {"case_id": "A", "predicted_function": "mint", "ground_truth_function": "mint"},
        # miss
        {"case_id": "B", "predicted_function": "foo", "ground_truth_function": "bar"},
        # empty pred
        {"case_id": "C", "predicted_function": "", "ground_truth_function": "x"},
        # strict hit but not in eval_set (should be skipped gracefully)
        {"case_id": "D", "predicted_function": "burn", "ground_truth_function": "burn"},
    ]
    eval_set = {
        "cases": [
            {
                "id": "A",
                "contract_name": "TokenA",
                "contract_source": "contract TokenA { function mint() external {} }",
                "vulnerable_function": "mint",
                "description": "mint unprotected",
            },
            {
                "id": "B",
                "contract_name": "TokenB",
                "contract_source": "contract TokenB { function swap() external {} }",
                "vulnerable_function": "bar",
            },
        ]
    }
    preds_path = tmp_path / "preds.json"
    eval_path = tmp_path / "eval.json"
    preds_path.write_text(json.dumps(preds), encoding="utf-8")
    eval_path.write_text(json.dumps(eval_set), encoding="utf-8")

    store = load_store_from_predictions(str(preds_path), str(eval_path))
    # Only case A is a strict hit AND present in eval_set → single-member corpus
    assert len(store) == 1
    retrieved = store.retrieve(
        "contract X { function mint() external {} }", top_k=5
    )
    assert len(retrieved) == 1
    assert retrieved[0].case.case_id == "A"
