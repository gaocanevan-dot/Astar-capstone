"""Foundry adapter — runs `forge test` and classifies output into four verdicts:
pass / fail_revert_ac / fail_error_compile / fail_error_runtime.

Keyword list is sourced from `revert_keywords.yaml` and versioned independently
of this module, so new AC revert patterns can be added as a tiny PR.

Day-1 iter4 changes:
- Verdict split: `fail_error` → `fail_error_compile` | `fail_error_runtime` so
  the cascade router can distinguish "PoC didn't compile" (don't blame the
  candidate) from "PoC ran and reverted for non-AC reasons" (advance candidate).
- Forge-std install cache at `~/.cache/omc/forge-std/` (override via env
  `OMC_FORGE_STD_CACHE`) so 4-arm × 10-case ablations don't pay 60 cold installs.
- `verifier_mode`-driven source-write seam replacing the `poc_imports_original`
  text-sniff heuristic. Backwards-compat: when `verifier_mode is None`, falls
  back to the old heuristic.
- `_resolve_pragma()` returns `(pragma_directive, mode_hint)` for the smoke-set
  builder + (later) the builder node's pragma 3-branch policy.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml


Verdict = Literal[
    "pass",
    "fail_revert_ac",
    "fail_error_compile",
    "fail_error_runtime",
]


@dataclass
class ForgeResult:
    verdict: Verdict
    stdout: str
    stderr: str
    return_code: int
    duration_s: float
    error_summary: str


_KEYWORDS_CACHE: dict | None = None


def _load_keywords() -> dict:
    global _KEYWORDS_CACHE
    if _KEYWORDS_CACHE is None:
        path = Path(__file__).with_name("revert_keywords.yaml")
        _KEYWORDS_CACHE = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _KEYWORDS_CACHE


def classify_verdict(stdout: str, stderr: str, return_code: int) -> ForgeResult:
    """Pure function: given forge output, return a verdict + summary."""
    trace = (stdout or "") + "\n" + (stderr or "")
    trace_lower = trace.lower()
    kw = _load_keywords()

    # Compile errors come first (they're structurally different from test reverts)
    compile_markers = [
        "compiler run failed",
        "parsererror",
        "identifiernotfound",
        "syntaxerror",
        "typeerror: ",
        "declarationerror",
        "unresolved import",
    ]
    if any(m in trace_lower for m in compile_markers):
        return ForgeResult(
            verdict="fail_error_compile",
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            duration_s=0.0,
            error_summary=_extract_error(trace),
        )

    if return_code == 0:
        return ForgeResult(
            verdict="pass",
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            duration_s=0.0,
            error_summary="",
        )

    # Check if the revert matches an AC pattern
    ac_hits = [k for k in kw.get("access_control", []) if k.lower() in trace_lower]
    non_ac_hits = [k for k in kw.get("non_access_control", []) if k.lower() in trace_lower]

    if ac_hits and not non_ac_hits:
        return ForgeResult(
            verdict="fail_revert_ac",
            stdout=stdout,
            stderr=stderr,
            return_code=return_code,
            duration_s=0.0,
            error_summary=f"AC intercept: {ac_hits[0]}",
        )

    return ForgeResult(
        verdict="fail_error_runtime",
        stdout=stdout,
        stderr=stderr,
        return_code=return_code,
        duration_s=0.0,
        error_summary=_extract_error(trace),
    )


def _extract_error(trace: str) -> str:
    """Best-effort single-line error summary for the retry loop."""
    lines = trace.splitlines()
    error_lines = [
        ln for ln in lines
        if re.search(r"\berror\b|\brevert\b|\bfailed\b|\bPanic\b", ln, re.IGNORECASE)
    ]
    if error_lines:
        return " | ".join(line.strip() for line in error_lines[:3])[:500]
    return trace[:300]


_PRAGMA_RE = re.compile(r"^\s*pragma\s+solidity\s+([^;]+);", re.MULTILINE)


def _resolve_pragma(contract_source: str) -> tuple[str, str]:
    """Day-1 T5 — pragma 3-branch policy.

    Returns (pragma_directive, mode_hint):
      - mode_hint == "mirror"      → source has ^0.8.x or >=0.8.x; mirror it.
      - mode_hint == "pre_08_force_replica"
                                   → source pragma is < 0.8 (e.g. ^0.7.6);
                                     PoC forge-std needs 0.8, so the smoke-set
                                     builder should tag this case `replica_only`.
      - mode_hint == "no_pragma_force_0820"
                                   → no pragma found in source (32/42 dominant
                                     case in our corpus). Force `pragma 0.8.20`.

    The directive is the literal `pragma solidity X;` line to write.
    """
    m = _PRAGMA_RE.search(contract_source or "")
    if not m:
        return ("pragma solidity 0.8.20;", "no_pragma_force_0820")
    spec = m.group(1).strip()
    # Detect 0.8+ (mirror) vs pre-0.8 (force replica).
    if re.search(r"(?:\^|>=|=|>)?\s*0\.8", spec):
        return (f"pragma solidity {spec};", "mirror")
    return ("pragma solidity 0.8.20;", "pre_08_force_replica")


# ---------------------------------------------------------------------------
# Day-1 T1: forge-std install cache
# ---------------------------------------------------------------------------
# The original implementation (still active fallback below) ran
# `forge install foundry-rs/forge-std --no-git` for every case. On a 4-arm ×
# 10-case smoke run that's 40 cold installs — each one a network round-trip.
# We now keep a single populated copy under `~/.cache/omc/forge-std/lib/...`
# (or `$OMC_FORGE_STD_CACHE`) and `shutil.copytree` it into per-case tmpdirs.

_FORGE_STD_CACHE_ENV = "OMC_FORGE_STD_CACHE"


def _forge_std_cache_root() -> Path:
    override = os.environ.get(_FORGE_STD_CACHE_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "omc" / "forge-std"


def _forge_std_cache_lib(cache_root: Path) -> Path:
    """Where the forge-std library lives inside the cache (`lib/forge-std`)."""
    return cache_root / "lib" / "forge-std"


_CACHE_SENTINEL = ".cache_complete"


def _ensure_forge_std_cache(forge: str, timeout_s: int = 60) -> tuple[Path, str]:
    """Ensure `_forge_std_cache_lib()` is populated. Returns (lib_path, status).

    status ∈ {"cache_hit", "cache_miss_populated", "install_failed"}.

    Concurrency / partial-population guard (code-reviewer Major #1):
    - We treat the cache as valid ONLY when a sentinel file
      `cache_root/.cache_complete` exists. A directory that has files but no
      sentinel is treated as a corrupt half-write (e.g. timed-out install,
      Ctrl-C during populate) and re-installed.
    - The sentinel is written AFTER `forge install` succeeds and AFTER the lib
      directory verification passes.
    - This is not a true cross-process lock (we don't pull in `filelock` for a
      capstone smoke run), but it converts the failure mode from "silent
      corrupt cache" into "redundant install" which is recoverable.

    On `install_failed`, lib_path is still the (possibly empty) cache directory;
    caller should map this to a `fail_error_runtime` ForgeResult.
    """
    cache_root = _forge_std_cache_root()
    lib = _forge_std_cache_lib(cache_root)
    sentinel = cache_root / _CACHE_SENTINEL
    if sentinel.exists() and lib.exists() and any(lib.iterdir()):
        return (lib, "cache_hit")

    # Cache miss OR previous install was partial → wipe + re-populate.
    if cache_root.exists() and not sentinel.exists():
        # Best-effort: stale lib without sentinel = treat as corrupt.
        try:
            shutil.rmtree(cache_root)
        except OSError:
            pass
    cache_root.mkdir(parents=True, exist_ok=True)
    (cache_root / "lib").mkdir(exist_ok=True)
    try:
        install = subprocess.run(
            [forge, "install", "foundry-rs/forge-std", "--no-git"],
            cwd=str(cache_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return (lib, "install_failed")
    if install.returncode != 0 or not lib.exists() or not any(lib.iterdir()):
        return (lib, "install_failed")
    # Atomic-ish: write sentinel only after we've confirmed the lib is populated.
    try:
        sentinel.write_text("ok", encoding="utf-8")
    except OSError:
        return (lib, "install_failed")
    return (lib, "cache_miss_populated")


def resolve_forge() -> str | None:
    """Find a forge executable: PATH first, then env FOUNDRY_PATH, then default."""
    forge_on_path = shutil.which("forge")
    if forge_on_path:
        return forge_on_path
    env_path = os.environ.get("FOUNDRY_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_dir():
            candidate = candidate / ("forge.exe" if os.name == "nt" else "forge")
        if candidate.exists():
            return str(candidate)
    default = Path.home() / ".foundry" / "bin" / ("forge.exe" if os.name == "nt" else "forge")
    if default.exists():
        return str(default)
    return None


def _should_write_original_source(
    verifier_mode: str | None,
    poc_code: str,
    contract_name: str,
) -> bool:
    """Day-1 T4 — `verifier_mode`-driven source-write seam.

    - `verifier_mode in {"original", "oz_vendored"}` → ALWAYS write the original
      `contract_source` to `proj/src/{Name}.sol`. PoC must `import "../src/..."`.
    - `verifier_mode == "replica_only"` → NEVER write source; PoC is self-contained.
    - `verifier_mode is None` → backward-compat: keep the legacy text-sniff
      heuristic (`poc_imports_original`) so callers that haven't been migrated
      yet keep working.
    """
    if verifier_mode in ("original", "oz_vendored"):
        return True
    if verifier_mode == "replica_only":
        return False
    # Legacy fallback path
    return (
        f'../src/{contract_name}' in poc_code
        or f'"src/{contract_name}' in poc_code
    )


def run_forge_test(
    contract_source: str,
    contract_name: str,
    poc_code: str,
    install_forge_std: bool = True,
    timeout_s: int = 180,
    verifier_mode: str | None = None,
) -> ForgeResult:
    """Write contract + PoC into a temp foundry project, run `forge test -vvv`.

    Returns a ForgeResult with classified verdict.

    `verifier_mode` (Day-1 T4):
      - "original"        → write original `contract_source` to `proj/src/`.
      - "oz_vendored"     → same as "original" (OZ remap activation deferred to
                            DEF2; tag carried on the case for telemetry).
      - "replica_only"    → never write source; PoC must be self-contained.
      - None              → legacy text-sniff fallback.
    """
    forge = resolve_forge()
    if forge is None:
        return ForgeResult(
            verdict="fail_error_runtime",
            stdout="",
            stderr="forge executable not found",
            return_code=-1,
            duration_s=0.0,
            error_summary="forge not found on PATH / FOUNDRY_PATH / default",
        )

    write_source = _should_write_original_source(
        verifier_mode, poc_code, contract_name
    )

    # Day-2 Prereq-B: pragma 3-branch policy is enforced at source-write time.
    #   - mirror              → write source as-is (already 0.8+)
    #   - no_pragma_force_0820 → prepend `pragma solidity 0.8.20;` so forge can compile
    #   - pre_08_force_replica → cannot bridge pre-0.8 to forge-std; force replica path
    pragma_directive: str = ""
    pragma_hint: str = ""
    if write_source:
        pragma_directive, pragma_hint = _resolve_pragma(contract_source)
        if pragma_hint == "pre_08_force_replica":
            write_source = False  # let the PoC's own 0.8 declaration drive compile

    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="agent_forge_") as tmpdir:
        proj = Path(tmpdir)
        (proj / "src").mkdir()
        (proj / "test").mkdir()

        if write_source:
            source_to_write = (
                pragma_directive + "\n" + contract_source
                if pragma_hint == "no_pragma_force_0820"
                else contract_source
            )
            (proj / "src" / f"{contract_name}.sol").write_text(source_to_write, encoding="utf-8")
        (proj / "test" / f"{contract_name}.t.sol").write_text(poc_code, encoding="utf-8")
        (proj / "foundry.toml").write_text(
            "[profile.default]\n"
            'src = "src"\n'
            'out = "out"\n'
            'libs = ["lib"]\n'
            'solc = "0.8.20"\n'
            "auto_detect_solc = true\n",
            encoding="utf-8",
        )

        if install_forge_std:
            cached_lib, cache_status = _ensure_forge_std_cache(forge)
            if cache_status == "install_failed":
                return ForgeResult(
                    verdict="fail_error_runtime",
                    stdout="",
                    stderr=f"forge install failed (cache root: {cached_lib.parent.parent})",
                    return_code=-1,
                    duration_s=time.time() - t0,
                    error_summary="forge install failed (forge-std cache could not be populated)",
                )
            # Cache hit OR just-populated → copy into per-case tmpdir so the
            # remappings + libs paths resolve identically.
            (proj / "lib").mkdir(exist_ok=True)
            try:
                shutil.copytree(cached_lib, proj / "lib" / "forge-std")
            except Exception as exc:  # pragma: no cover - filesystem edge cases
                return ForgeResult(
                    verdict="fail_error_runtime",
                    stdout="",
                    stderr=f"forge-std cache copy failed: {exc}",
                    return_code=-1,
                    duration_s=time.time() - t0,
                    error_summary=f"forge-std cache copy failed: {exc}",
                )

        try:
            result = subprocess.run(
                [forge, "test", "-vvv"],
                cwd=str(proj),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return ForgeResult(
                verdict="fail_error_runtime",
                stdout="",
                stderr=f"forge test timed out after {timeout_s}s",
                return_code=-1,
                duration_s=time.time() - t0,
                error_summary="forge test timed out",
            )

    classified = classify_verdict(result.stdout, result.stderr, result.returncode)
    return ForgeResult(
        verdict=classified.verdict,
        stdout=result.stdout,
        stderr=result.stderr,
        return_code=result.returncode,
        duration_s=time.time() - t0,
        error_summary=classified.error_summary,
    )
