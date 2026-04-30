"""Unit tests for compute_analyst_recall."""

from agent.eval.metrics import compute_analyst_recall


def _pred(case_id, gt, pred, conf=1.0):
    return {
        "case_id": case_id,
        "ground_truth_function": gt,
        "predicted_function": pred,
        "confidence": conf,
    }


def test_empty_predictions_returns_zero():
    r = compute_analyst_recall([])
    assert r.total == 0
    assert r.hits_strict == 0
    assert r.hits_loose == 0
    assert r.recall_strict == 0.0
    assert r.recall_loose == 0.0


def test_cases_without_ground_truth_are_excluded():
    preds = [
        _pred("A", "", "anything"),
        _pred("B", None, "anything"),
        _pred("C", "setFee", "setFee"),
    ]
    r = compute_analyst_recall(preds)
    assert r.total == 1  # only C is evaluable
    assert r.hits_strict == 1
    assert r.recall_strict == 1.0


def test_strict_exact_match_only():
    preds = [
        _pred("A", "setFee", "setFee"),
        _pred("B", "setFee", "set_fee"),  # different casing/underscore
        _pred("C", "withdraw", "withdraw"),
    ]
    r = compute_analyst_recall(preds)
    assert r.total == 3
    assert r.hits_strict == 2
    assert r.recall_strict == 2 / 3


def test_loose_substring_match():
    preds = [
        _pred("A", "setProtocolFee", "setFee"),  # NOT contiguous ("Protocol" between)
        _pred("B", "setFee", "setProtocolFee"),  # NOT contiguous either way
        _pred("C", "UnauthorizedMint", "Mint"),  # pred IS contiguous substring of GT
        _pred("D", "mint", "UnauthorizedMint"),  # GT IS contiguous substring of pred
        _pred("E", "burn", "mint"),  # no overlap
        _pred("F", "Transfer", "transfer"),  # case differ but lower equal
    ]
    r = compute_analyst_recall(preds)
    assert r.total == 6
    # strict: C/D/F are lower-matches, but strict is raw equality → none hit strict
    assert r.hits_strict == 0
    # loose: C (Mint ⊂ UnauthorizedMint), D (mint ⊂ UnauthorizedMint lowercased),
    #        F (lower equal), NOT A/B/E
    assert r.hits_loose == 3
    assert r.recall_loose == 0.5


def test_empty_prediction_never_hits():
    preds = [
        _pred("A", "setFee", ""),
        _pred("B", "withdraw", ""),
    ]
    r = compute_analyst_recall(preds)
    assert r.total == 2
    assert r.hits_strict == 0
    assert r.hits_loose == 0


def test_per_case_structure_has_flags():
    preds = [_pred("X", "f1", "f1"), _pred("Y", "f2", "f3")]
    r = compute_analyst_recall(preds)
    assert len(r.per_case) == 2
    first = r.per_case[0]
    assert first["case_id"] == "X"
    assert first["strict_hit"] is True
    assert first["loose_hit"] is True
    second = r.per_case[1]
    assert second["strict_hit"] is False
    assert second["loose_hit"] is False


def test_summary_line_format():
    preds = [_pred("A", "setFee", "setFee"), _pred("B", "mint", "burn")]
    r = compute_analyst_recall(preds)
    line = r.summary_line()
    assert "Analyst Recall" in line
    assert "50.00%" in line
    assert "1/2" in line


# ---- Top-k metric tests ----


def _pred_topk(case_id, gt, top1, candidates, conf=1.0):
    return {
        "case_id": case_id,
        "ground_truth_function": gt,
        "predicted_function": top1,
        "candidates": candidates,
        "confidence": conf,
    }


def test_hit_at_k_no_candidates_means_none_returned():
    """When no prediction has `candidates`, recall_at_k should be None (not empty dict)."""
    preds = [_pred("A", "fn", "fn")]  # no 'candidates' key
    r = compute_analyst_recall(preds)
    assert r.recall_at_k is None
    assert r.hits_at_k is None


def test_hit_at_k_basic():
    """hit@1 should equal strict; hit@3 should be >= hit@1."""
    preds = [
        # Top-1 miss, top-3 hit
        _pred_topk("A", "realfn", "wrongfn", ["wrongfn", "otherfn", "realfn"]),
        # Top-1 hit
        _pred_topk("B", "mint", "mint", ["mint", "burn", "transfer"]),
        # Total miss
        _pred_topk("C", "correct", "wrong", ["wrong", "also_wrong", "still_wrong"]),
    ]
    r = compute_analyst_recall(preds, k_values=(1, 2, 3))
    assert r.total == 3
    # hit@1: only B → 1
    assert r.hits_at_k[1] == 1
    # hit@2: B (mint is at idx 0) → 1; A's "realfn" at idx 2, not in top-2 → no
    assert r.hits_at_k[2] == 1
    # hit@3: A (realfn at idx 2) + B (mint at idx 0) → 2
    assert r.hits_at_k[3] == 2
    # hit@k monotone non-decreasing
    assert r.hits_at_k[1] <= r.hits_at_k[2] <= r.hits_at_k[3]


def test_hit_at_k_ignores_cases_without_gt():
    preds = [
        _pred_topk("A", "", "anything", ["anything"]),  # no GT → excluded
        _pred_topk("B", "fn", "fn", ["fn"]),
    ]
    r = compute_analyst_recall(preds)
    assert r.total == 1
    assert r.hits_at_k[1] == 1


def test_hit_at_k_empty_candidates():
    preds = [
        _pred_topk("A", "fn", "", []),  # analyst abstained, empty candidates
        _pred_topk("B", "fn2", "fn2", ["fn2"]),
    ]
    r = compute_analyst_recall(preds)
    # A has empty candidates and empty predicted — no hit
    assert r.hits_at_k[1] == 1  # only B
    assert r.hits_at_k[3] == 1


def test_summary_line_includes_hit_at_k_when_candidates_present():
    preds = [
        _pred_topk("A", "fn", "miss", ["miss", "also_miss", "fn"]),
    ]
    r = compute_analyst_recall(preds)
    line = r.summary_line()
    assert "hit@1" in line
    assert "hit@3" in line
    # hit@3 should show 100.00% since the only case's GT is at index 2
    assert "hit@3=100.00%" in line


def test_hit_at_k_per_case_flags():
    preds = [_pred_topk("A", "fn", "wrong", ["wrong", "fn", "other"])]
    r = compute_analyst_recall(preds)
    pc = r.per_case[0]
    assert pc["hit_at_1"] is False
    assert pc["hit_at_2"] is True
    assert pc["hit_at_3"] is True
