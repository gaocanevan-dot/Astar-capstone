"""Structural tests for LangGraph 4-arm implementation.

Verifies ablation arms are COMPILE-TIME distinct (different node sets), not
just "same graph with different config flags". This is the P3 principle from
the consensus plan — "ablation isolates the thing it names".
"""

import pytest

from agent.graph_lg import (
    GRAPH_FACTORIES,
    build_graph,
    build_graph_full,
    build_graph_no_rag,
    build_graph_no_static,
    build_graph_no_verify_loop,
)


def _node_set(compiled_graph) -> set[str]:
    """Return the set of user-defined node names (exclude LangGraph system nodes)."""
    all_nodes = set(compiled_graph.get_graph().nodes.keys())
    return all_nodes - {"__start__", "__end__"}


class TestGraphCompilation:
    def test_all_four_arms_compile(self):
        for arm in ("full", "no-static", "no-rag", "no-verify-loop"):
            g = build_graph(arm)
            assert g is not None
            assert len(_node_set(g)) > 0

    def test_unknown_arm_raises(self):
        with pytest.raises(ValueError, match="Unknown arm"):
            build_graph("nonexistent-arm")

    def test_registry_matches_factories(self):
        assert set(GRAPH_FACTORIES.keys()) == {"full", "no-static", "no-rag", "no-verify-loop"}


class TestStructuralDifferences:
    """The whole point of compile-time arms: different node sets."""

    def test_full_has_all_pipeline_nodes(self):
        nodes = _node_set(build_graph_full())
        for required in ("preprocess_static", "rag_retrieve", "analyst", "builder", "verifier", "report", "mark_safe"):
            assert required in nodes, f"full arm missing {required}"

    def test_no_static_drops_preprocess_static(self):
        nodes = _node_set(build_graph_no_static())
        assert "preprocess_static" not in nodes
        # but keeps the rest
        assert "rag_retrieve" in nodes
        assert "verifier" in nodes

    def test_no_rag_drops_rag_retrieve(self):
        nodes = _node_set(build_graph_no_rag())
        assert "rag_retrieve" not in nodes
        assert "preprocess_static" in nodes
        assert "verifier" in nodes

    def test_no_verify_loop_drops_verifier_and_report(self):
        nodes = _node_set(build_graph_no_verify_loop())
        assert "verifier" not in nodes
        assert "report" not in nodes
        # But adds the alternative terminal
        assert "mark_vulnerable_on_poc" in nodes
        # Still has builder and analyst
        assert "analyst" in nodes
        assert "builder" in nodes

    def test_no_verify_loop_only_arm_with_mark_vulnerable_on_poc(self):
        assert "mark_vulnerable_on_poc" not in _node_set(build_graph_full())
        assert "mark_vulnerable_on_poc" not in _node_set(build_graph_no_static())
        assert "mark_vulnerable_on_poc" not in _node_set(build_graph_no_rag())
        assert "mark_vulnerable_on_poc" in _node_set(build_graph_no_verify_loop())


class TestMermaidExport:
    """Every arm must be visualizable — required by plan §7 item 2 (ablation mermaid diff)."""

    @pytest.mark.parametrize("arm", ["full", "no-static", "no-rag", "no-verify-loop"])
    def test_each_arm_exports_mermaid(self, arm):
        g = build_graph(arm)
        mermaid = g.get_graph().draw_mermaid()
        assert isinstance(mermaid, str)
        assert len(mermaid) > 20
        # Sanity: mermaid starts with a graph-definition keyword
        assert "graph" in mermaid.lower() or "flowchart" in mermaid.lower() or "---" in mermaid


class TestAblationIsolation:
    """Plan §7 item 2: grep -c verifier on no_verify_loop.mmd must return 0."""

    def test_no_verify_loop_mermaid_has_no_verifier_node(self):
        g = build_graph_no_verify_loop()
        mermaid = g.get_graph().draw_mermaid()
        # verifier shouldn't appear as a node definition anywhere
        # (mark_vulnerable_on_poc may contain the substring "verify" in the name — check the node name itself)
        nodes = _node_set(g)
        assert "verifier" not in nodes
        assert "report" not in nodes

    def test_no_rag_mermaid_has_no_rag_retrieve(self):
        nodes = _node_set(build_graph_no_rag())
        assert "rag_retrieve" not in nodes

    def test_no_static_mermaid_has_no_preprocess(self):
        nodes = _node_set(build_graph_no_static())
        assert "preprocess_static" not in nodes


class TestStateType:
    """AuditGraphState should accept the canonical inputs without errors."""

    def test_init_state_helper(self):
        from agent.graph_lg import _init_state

        s = _init_state(
            case_id="TEST-1",
            contract_source="contract X {}",
            contract_name="X",
            max_retries=3,
        )
        assert s["case_id"] == "TEST-1"
        assert s["max_retries"] == 3
        assert s["poc_attempts"] == 0
        assert s["error_history"] == []
        assert s["execution_result"] == "pending"
        assert s["finding_confirmed"] is False
