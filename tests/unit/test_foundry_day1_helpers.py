"""Unit tests for the Day-1 iter4 foundry adapter helpers.

Covers:
- T5 `_resolve_pragma`: 3-branch policy (^0.8 mirror / pre-0.8 force replica /
  no-pragma force 0.8.20)
- T4 `_should_write_original_source`: verifier_mode-driven seam (original /
  oz_vendored / replica_only / None legacy fallback)
- T1 `_ensure_forge_std_cache`: cache-hit short-circuit (no subprocess on warm
  cache); install-failed surface when forge is unavailable.

Forge is not invoked in these tests; we monkey-patch subprocess.run when
needed to verify the cache call count.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.adapters import foundry as foundry_mod
from agent.adapters.foundry import (
    _ensure_forge_std_cache,
    _forge_std_cache_lib,
    _resolve_pragma,
    _should_write_original_source,
)


# ---------------------------------------------------------------------------
# T5 — Pragma 3-branch resolver
# ---------------------------------------------------------------------------


class TestResolvePragma:
    def test_caret_08_mirrors_pragma(self):
        src = "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\ncontract X {}"
        directive, hint = _resolve_pragma(src)
        assert hint == "mirror"
        assert directive == "pragma solidity ^0.8.20;"

    def test_geq_08_mirrors_pragma(self):
        src = "pragma solidity >=0.8.0 <0.9.0;\ncontract X {}"
        directive, hint = _resolve_pragma(src)
        assert hint == "mirror"
        assert ">=0.8.0" in directive

    def test_pre_08_forces_replica(self):
        src = "pragma solidity ^0.7.6;\ncontract X {}"
        directive, hint = _resolve_pragma(src)
        assert hint == "pre_08_force_replica"
        # Forge-std needs 0.8+, so the replica path uses 0.8.20.
        assert directive == "pragma solidity 0.8.20;"

    def test_no_pragma_forces_0820(self):
        # 32/42 of the corpus stored snippets without a pragma.
        src = "contract X { function f() external {} }"
        directive, hint = _resolve_pragma(src)
        assert hint == "no_pragma_force_0820"
        assert directive == "pragma solidity 0.8.20;"

    def test_empty_source_treated_as_no_pragma(self):
        directive, hint = _resolve_pragma("")
        assert hint == "no_pragma_force_0820"
        assert directive == "pragma solidity 0.8.20;"


# ---------------------------------------------------------------------------
# T4 — verifier_mode-driven source-write seam
# ---------------------------------------------------------------------------


class TestShouldWriteOriginalSource:
    def test_mode_original_writes_source(self):
        assert _should_write_original_source("original", "// any poc", "Foo") is True

    def test_mode_oz_vendored_writes_source(self):
        assert _should_write_original_source("oz_vendored", "// any poc", "Foo") is True

    def test_mode_replica_only_does_not_write(self):
        # Even if the PoC accidentally references ../src/, replica_only wins.
        poc = 'import "../src/Foo.sol";'
        assert _should_write_original_source("replica_only", poc, "Foo") is False

    def test_legacy_none_falls_back_to_text_sniff_positive(self):
        poc = 'import "../src/MyContract.sol";\ncontract T {}'
        assert _should_write_original_source(None, poc, "MyContract") is True

    def test_legacy_none_falls_back_to_text_sniff_negative(self):
        poc = "// self-contained PoC, no original-source import\ncontract T {}"
        assert _should_write_original_source(None, poc, "MyContract") is False


# ---------------------------------------------------------------------------
# T1 — forge-std install cache
# ---------------------------------------------------------------------------


class TestForgeStdCache:
    """Cache hit short-circuits subprocess. Cache miss + no forge → install_failed.

    These tests use `OMC_FORGE_STD_CACHE` env override (read every call inside
    `_forge_std_cache_root`) so they do not touch the user's real ~/.cache.
    """

    def test_cache_hit_does_not_invoke_subprocess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        cache_root = tmp_path / "cache"
        lib = cache_root / "lib" / "forge-std"
        lib.mkdir(parents=True)
        # Populate with a sentinel file so `lib.exists() and any(lib.iterdir())`
        # is true. Plus the cache-completion sentinel (Major #1 fix) — without
        # it, the cache is treated as corrupt and re-installed.
        (lib / "PRESENT").write_text("ok", encoding="utf-8")
        (cache_root / ".cache_complete").write_text("ok", encoding="utf-8")

        monkeypatch.setenv("OMC_FORGE_STD_CACHE", str(cache_root))

        calls = []

        def fake_run(*args, **kwargs):
            calls.append(args)
            raise AssertionError("subprocess.run must not be called on cache hit")

        monkeypatch.setattr(foundry_mod.subprocess, "run", fake_run)

        out_lib, status = _ensure_forge_std_cache("/usr/bin/forge")
        assert status == "cache_hit"
        assert out_lib == _forge_std_cache_lib(cache_root)
        assert calls == []

    def test_cache_miss_install_failed_surfaces_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        cache_root = tmp_path / "cache"
        monkeypatch.setenv("OMC_FORGE_STD_CACHE", str(cache_root))

        # Simulate forge install returning non-zero (no real forge on test host).
        class _FakeCompleted:
            def __init__(self):
                self.returncode = 1
                self.stdout = ""
                self.stderr = "forge: command not found"

        def fake_run(*args, **kwargs):
            return _FakeCompleted()

        monkeypatch.setattr(foundry_mod.subprocess, "run", fake_run)

        out_lib, status = _ensure_forge_std_cache("/usr/bin/forge")
        assert status == "install_failed"
        assert out_lib == _forge_std_cache_lib(cache_root)


# ---------------------------------------------------------------------------
# Lightweight smoke: imports + literal completeness
# ---------------------------------------------------------------------------


def test_verdict_literal_includes_compile_and_runtime_split():
    """Day-1 T2 sanity: the new verdict labels exist as Literal members."""
    # If the Literal expansion regresses, this annotation read will still
    # succeed at runtime, but pytest -q gives us a single line we can grep.
    from agent.adapters.foundry import Verdict

    # `typing.get_args` on a Literal returns the tuple of its members.
    import typing

    members = set(typing.get_args(Verdict))
    assert "fail_error_compile" in members
    assert "fail_error_runtime" in members
    assert "fail_error" not in members  # legacy label fully removed
    assert "pass" in members
    assert "fail_revert_ac" in members
