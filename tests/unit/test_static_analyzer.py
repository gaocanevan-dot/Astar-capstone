"""Unit tests for static_analyzer regex fallback (Slither skipped — subprocess
would require a working solc chain; regex path is deterministic offline)."""

from agent.adapters.static_analyzer import (
    FunctionFact,
    StaticFacts,
    _regex_fallback,
    analyze,
)


def test_regex_fallback_extracts_functions():
    src = """
    pragma solidity 0.8.20;
    contract X {
        address owner;
        function setOwner(address a) external onlyOwner { owner = a; }
        function mint(address to, uint256 amt) external { balances[to] += amt; }
        function view_only() external view returns (uint256) { return 0; }
    }
    """
    facts = _regex_fallback(src)
    names = {fn.name for fn in facts.functions}
    assert names == {"setOwner", "mint", "view_only"}

    by_name = {fn.name: fn for fn in facts.functions}
    assert by_name["setOwner"].visibility == "external"
    assert "onlyOwner" in by_name["setOwner"].modifiers
    assert by_name["setOwner"].state_changing is True

    assert by_name["mint"].modifiers == []
    assert by_name["mint"].state_changing is True

    assert by_name["view_only"].state_changing is False


def test_visibility_default_public():
    src = "contract X { function f() external {} function g() {} }"
    facts = _regex_fallback(src)
    by_name = {fn.name: fn.visibility for fn in facts.functions}
    assert by_name["f"] == "external"
    # g has no explicit visibility → defaults to public
    assert by_name["g"] == "public"


def test_known_keywords_not_classified_as_modifiers():
    src = "contract X { function f() external view virtual override returns (uint) { return 0; } }"
    facts = _regex_fallback(src)
    by_name = {fn.name: fn.modifiers for fn in facts.functions}
    # external / view / virtual / override / returns should NOT end up in modifiers
    assert all(
        mod not in by_name["f"]
        for mod in ("external", "view", "virtual", "override", "returns")
    )


def test_compact_summary_bounded():
    facts = StaticFacts(
        functions=[
            FunctionFact(f"fn{i}", "external", [], True) for i in range(30)
        ],
        slither_findings=[],
    )
    summary = facts.compact_summary(max_lines=5)
    # 1 header + 5 function lines = 6 total
    assert summary.count("\n") <= 6 + 1


def test_compact_summary_with_slither_findings():
    facts = StaticFacts(
        functions=[FunctionFact("setOwner", "external", ["onlyOwner"], True)],
        slither_findings=[
            {"check": "unprotected-initializer", "description": "initialize without guard"}
        ],
    )
    summary = facts.compact_summary()
    assert "setOwner" in summary
    assert "unprotected-initializer" in summary


def test_empty_facts_summary():
    facts = StaticFacts()
    assert "No static facts" in facts.compact_summary()


def test_analyze_entry_point_does_not_raise():
    # Even if slither is unavailable, analyze must return (falls back to regex)
    src = "pragma solidity 0.8.20; contract X { function f() external {} }"
    facts = analyze(src, "X")
    assert isinstance(facts, StaticFacts)
    assert len(facts.functions) == 1
    assert facts.functions[0].name == "f"
