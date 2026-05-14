"""Unit tests for scripts.mcc.case_loader + extract_closure (MCC Day 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.mcc import case_loader, extract_closure as ec


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------- case_loader ----------------


def test_load_case_acf_001_has_target_and_project_root():
    ci = case_loader.load_case("ACF-001")
    assert ci.incident_id == "ACF-001"
    assert ci.case_id == "ACF-001"
    assert ci.target_file.is_file()
    assert ci.project_root.is_dir()
    assert ci.target_file.parent == ci.project_root
    assert ci.contract_name  # non-empty
    assert ci.vulnerable_function  # GT exists


def test_load_case_pragma_extracted():
    ci = case_loader.load_case("ACF-001")
    # ACF-001 (TBTCSystem) is Solidity 0.5.x
    assert "0.5" in ci.pragma


def test_load_case_c4_suffix_id():
    """C4-126_2 is a multi-row case; loader must look up by `id` (not just incident_id)."""
    ci = case_loader.load_case("C4-126_2")
    assert ci.case_id == "C4-126_2"
    assert ci.incident_id == "C4-126"


def test_load_case_missing_raises():
    with pytest.raises(KeyError):
        case_loader.load_case("NONEXISTENT-999")


def test_load_all_cases_skips_snippet():
    cases = case_loader.load_all_cases(skip_snippet=True)
    types = {c.source_type for c in cases}
    assert "snippet_only" not in types
    assert "c5_local" in types
    assert "c4_local" in types
    assert 150 <= len(cases) <= 200  # 172 in current dataset


# ---------------- extract_closure ----------------


def test_extract_paths_simple_import():
    src = 'import "./Foo.sol";'
    assert ec._extract_import_paths(src) == ["./Foo.sol"]


def test_extract_paths_named_imports():
    src = 'import {A, B as X} from "../Bar.sol";'
    assert ec._extract_import_paths(src) == ["../Bar.sol"]


def test_extract_paths_alias_import():
    src = 'import "./X.sol" as Y;'
    assert ec._extract_import_paths(src) == ["./X.sol"]


def test_extract_paths_star_import():
    src = 'import * as Z from "./X.sol";'
    assert ec._extract_import_paths(src) == ["./X.sol"]


def test_extract_paths_multiple():
    src = '''
import "./A.sol";
import {B} from "./B.sol";
import "@openzeppelin/contracts/X.sol";
'''
    assert ec._extract_import_paths(src) == [
        "./A.sol", "./B.sol", "@openzeppelin/contracts/X.sol",
    ]


def test_is_vendored_classification():
    assert ec._is_vendored("@openzeppelin/contracts/X.sol")
    assert ec._is_vendored("solady/utils/X.sol")
    assert ec._is_vendored("forge-std/Test.sol")
    assert not ec._is_vendored("./Foo.sol")
    assert not ec._is_vendored("src/X.sol")


def test_closure_target_within_budget_for_acf_001():
    ci = case_loader.load_case("ACF-001")
    cr = ec.extract_closure(ci.target_file, ci.project_root)
    assert cr.target_relpath == ci.target_file.name
    assert cr.size >= 1
    assert cr.within_budget  # 1 <= 10


def test_closure_max_files_enforced():
    """Synthetic test: artificially low budget triggers truncation."""
    ci = case_loader.load_case("ACF-001")
    cr = ec.extract_closure(ci.target_file, ci.project_root, max_files=1)
    assert cr.size <= 2  # may exceed by 1 (the file that triggers overflow)


def test_closure_aggregate_172_cases_mostly_within_budget():
    cases = case_loader.load_all_cases()
    within = 0
    total = 0
    for ci in cases:
        try:
            cr = ec.extract_closure(ci.target_file, ci.project_root)
        except FileNotFoundError:
            continue
        total += 1
        if cr.within_budget:
            within += 1
    assert total >= 150
    assert within / total >= 0.90  # Day-2 acceptance gate: >=90%


# ---------------- ClosureResult shape ----------------


def test_closure_result_serializable():
    """Driver scripts depend on asdict(ClosureResult) being JSON-safe."""
    import json
    from dataclasses import asdict

    ci = case_loader.load_case("ACF-001")
    cr = ec.extract_closure(ci.target_file, ci.project_root)
    blob = json.dumps(asdict(cr), default=str)
    assert "target_relpath" in blob
    assert "within_budget" in blob
