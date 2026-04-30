"""Unit tests for pydantic Case + EvalSet schema."""

import pytest
from pydantic import ValidationError

from agent.data.schema import Case, EvalSet


def _case(id_, label="vulnerable", source_type="code4rena_bad", **kw):
    base = dict(
        id=id_,
        contract_source="pragma solidity ^0.8.0; contract X {}",
        contract_name="X",
        ground_truth_label=label,
        source_type=source_type,
        buildable=True,
    )
    base.update(kw)
    return Case(**base)


class TestCase:
    def test_minimal_construction(self):
        c = _case("A")
        assert c.id == "A"
        assert c.ground_truth_label == "vulnerable"
        assert c.vulnerable_function is None
        assert c.vulnerability_type == "access_control"
        assert c.severity == "high"
        assert c.buildable is True

    def test_invalid_label_rejected(self):
        with pytest.raises(ValidationError):
            _case("A", label="maybe")

    def test_invalid_source_type_rejected(self):
        with pytest.raises(ValidationError):
            _case("A", source_type="random_source")

    def test_extra_fields_allowed(self):
        # model_config extra="allow" — legacy JSON fields shouldn't break ingest
        c = Case(
            id="A",
            contract_source="...",
            contract_name="X",
            ground_truth_label="vulnerable",
            source_type="code4rena_bad",
            some_legacy_field={"whatever": 1},
        )
        # extra field preserved on model
        assert getattr(c, "some_legacy_field", None) == {"whatever": 1}

    def test_split_field_optional(self):
        c = _case("A")
        assert c.split is None
        c2 = _case("B", split="dev")
        assert c2.split == "dev"


class TestEvalSet:
    def test_count_by_label_mixed(self):
        es = EvalSet(
            cases=[
                _case("A"),
                _case("B"),
                _case("C", label="safe", source_type="oz_safe"),
                _case("D", label="safe", source_type="fixed_code_safe"),
            ]
        )
        counts = es.count_by_label()
        assert counts == {"vulnerable": 2, "safe": 2}

    def test_count_by_label_all_one_side(self):
        es = EvalSet(cases=[_case("A"), _case("B")])
        assert es.count_by_label() == {"vulnerable": 2}

    def test_count_by_source_type_safe_only(self):
        es = EvalSet(
            cases=[
                _case("A"),  # vulnerable → excluded from safe count
                _case("S1", label="safe", source_type="oz_safe"),
                _case("S2", label="safe", source_type="oz_safe"),
                _case("S3", label="safe", source_type="c4_invalid_safe"),
            ]
        )
        counts = es.count_by_source_type("safe")
        assert counts == {"oz_safe": 2, "c4_invalid_safe": 1}

    def test_count_by_source_type_vulnerable(self):
        es = EvalSet(
            cases=[
                _case("A", source_type="code4rena_bad"),
                _case("B", source_type="swc_bad"),
                _case("S", label="safe", source_type="oz_safe"),
            ]
        )
        counts = es.count_by_source_type("vulnerable")
        assert counts == {"code4rena_bad": 1, "swc_bad": 1}

    def test_empty_evalset(self):
        es = EvalSet(cases=[])
        assert es.count_by_label() == {}
        assert es.count_by_source_type("vulnerable") == {}
