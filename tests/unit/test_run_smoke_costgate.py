"""Unit tests for Day-2 T12 cost-gate projection in `scripts/run_smoke.py`.

Tests the pure projection function in isolation (no LLM calls). The dry-run
execution path (which actually invokes the pipeline on 3 cases) is left to
manual user invocation when their quota allows.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_run_smoke():
    """Import scripts/run_smoke.py as a module without going through the
    repo-installed `agent.scripts` namespace (it isn't packaged that way)."""
    spec = importlib.util.spec_from_file_location(
        "_run_smoke_under_test", REPO_ROOT / "scripts" / "run_smoke.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestProjectUsd:
    def test_basic_projection(self):
        rs = _load_run_smoke()
        p = rs._project_usd(
            sample_tokens_prompt=3000,  # 1000 avg per case × 3
            sample_tokens_completion=600,  # 200 avg per case × 3
            sample_size=3,
            full_sweep_runs=40,
            prompt_rate=0.01,
            completion_rate=0.03,
        )
        # avg prompt = 1000, avg completion = 200
        assert p["avg_prompt_per_case"] == 1000.0
        assert p["avg_completion_per_case"] == 200.0
        # projected: 40 × 1000 = 40,000 prompt; 40 × 200 = 8,000 completion
        assert p["projected_prompt_total"] == 40000.0
        assert p["projected_completion_total"] == 8000.0
        # USD: 40K × $0.01/1K + 8K × $0.03/1K = $0.40 + $0.24 = $0.64
        assert p["projected_usd"] == 0.64

    def test_zero_sample_returns_zeros(self):
        rs = _load_run_smoke()
        p = rs._project_usd(0, 0, 0, 40, 0.01, 0.03)
        assert p["projected_usd"] == 0.0
        assert p["avg_prompt_per_case"] == 0.0

    def test_higher_completion_rate(self):
        rs = _load_run_smoke()
        p = rs._project_usd(
            sample_tokens_prompt=300,
            sample_tokens_completion=900,
            sample_size=3,
            full_sweep_runs=40,
            prompt_rate=0.01,
            completion_rate=0.06,
        )
        # avg prompt 100, avg completion 300
        # full sweep: 4000 prompt, 12000 completion
        # USD: 0.04 + 0.72 = 0.76
        assert p["projected_usd"] == 0.76


class TestArmFlags:
    def test_agent_full_has_all_features(self):
        rs = _load_run_smoke()
        f = rs._arm_flags("agent-full")
        assert f["use_cascade"] is True
        assert f["use_reflection"] is True
        assert f["use_tools"] is True
        assert f["use_rag"] is True

    def test_no_cascade_disables_cascade(self):
        rs = _load_run_smoke()
        f = rs._arm_flags("no-cascade")
        assert f["use_cascade"] is False
        assert f["use_reflection"] is False  # reflection requires cascade
        assert f["use_rag"] is True

    def test_no_reflection_keeps_cascade(self):
        rs = _load_run_smoke()
        f = rs._arm_flags("no-reflection")
        assert f["use_cascade"] is True
        assert f["use_reflection"] is False
        assert f["use_rag"] is True

    def test_no_rag_disables_only_rag(self):
        rs = _load_run_smoke()
        f = rs._arm_flags("no-rag")
        assert f["use_cascade"] is True
        assert f["use_reflection"] is True
        assert f["use_rag"] is False


# ---------------------------------------------------------------------------
# Day-3 A: aggregate_summary markdown
# ---------------------------------------------------------------------------


class TestAggregateSummary:
    """Pure-function markdown render. No LLM calls."""

    def _mk_record(self, arm, case_id, verdict, predicted, gt, depth=1, refl=0, usd=0.001):
        return {
            "arm": arm,
            "case_id": case_id,
            "verdict": verdict,
            "finding_confirmed": verdict == "pass",
            "target_function": predicted,
            "ground_truth_function": gt,
            "tokens_prompt": 1000,
            "tokens_completion": 500,
            "case_usd": usd,
            "running_usd": usd,
            "wall_clock_s": 1.0,
            "poc_attempts": 1,
            "cascade_depth": depth,
            "reflection_calls": refl,
            "abstained": verdict == "abstain",
            "finding_reason": "test",
        }

    def test_summary_renders_recall_and_cvr(self, tmp_path):
        rs = _load_run_smoke()
        results = {
            "agent-full": [
                self._mk_record("agent-full", "X1", "pass", "foo", "foo"),  # recall hit
                self._mk_record("agent-full", "X2", "fail_revert_ac", "bar", "baz"),
                self._mk_record("agent-full", "X3", "abstain", "", "qux"),
            ],
            "no-cascade": [
                self._mk_record("no-cascade", "X1", "abstain", "foo", "foo", depth=1),
                self._mk_record("no-cascade", "X2", "abstain", "", "baz"),
                self._mk_record("no-cascade", "X3", "skipped", "", "qux"),
            ],
        }
        out = tmp_path / "summary.md"
        rs._aggregate_summary(
            results=results, out_path=out, running_usd=0.003, aborted=None
        )
        text = out.read_text(encoding="utf-8")
        # Headline + spend line
        assert "Smoke Ablation Summary" in text
        assert "$0.0030" in text
        # agent-full: 1 recall@1 hit, CVR = 1/(1+1+0) = 0.50
        assert "1/3" in text  # recall@1
        assert "0.50" in text  # CVR
        # no-cascade: 1 recall@1 hit (X1 predicted=gt), CVR n/a (denom 0)
        assert "n/a" in text  # CVR for no-cascade
        # Per-arm detail tables
        assert "agent-full` per-case detail" in text
        assert "no-cascade` per-case detail" in text

    def test_aborted_flag_renders_warning(self, tmp_path):
        rs = _load_run_smoke()
        results = {"agent-full": []}
        out = tmp_path / "summary.md"
        rs._aggregate_summary(
            results=results,
            out_path=out,
            running_usd=4.99,
            aborted="running-USD $4.9900 >= ceiling $5.0",
        )
        text = out.read_text(encoding="utf-8")
        assert "ABORTED" in text
        assert "running-USD $4.9900" in text
