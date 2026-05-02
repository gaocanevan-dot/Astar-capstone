"""Mode-string → RAGInjector factory.

Loop calls `get_injector(mode)` once at run start. Adding a new ablation
arm = adding one entry here + one new injector subclass; loop.py untouched.
"""
from __future__ import annotations

from typing import Optional

from agent.rag.base import RAGInjector
from agent.rag.null_injector import NullInjector

# Maps --mode flag to injector implementation name.
# Sentinel "null" means no injection (baseline/zero-shot arms).
INJECTOR_REGISTRY: dict[str, str] = {
    "5-baseline": "null",
    "5b-tool": "null",
    "5b-mandate": "null",
    "6-baseline": "null",
    "6-rag-inject": "anti_pattern_at_propose",
    "6-zero-shot": "null",
    # Day-7+ slots (ablation-ready):
    # "7-rag-episodic": "episodic_at_propose",
    # "7-rag-hybrid": "hybrid_anti_pattern_plus_episodic",
}


def get_injector(mode: Optional[str]) -> RAGInjector:
    """Return the concrete injector for the given mode.

    Unknown / None modes return NullInjector (safe default).
    """
    name = INJECTOR_REGISTRY.get(mode or "", "null")
    if name == "null":
        return NullInjector()
    if name == "anti_pattern_at_propose":
        # Local import to avoid pulling memory dependencies for null path.
        from agent.rag.anti_pattern_injector import AntiPatternInjector
        return AntiPatternInjector()
    # Future Day-7+ injectors land here.
    raise ValueError(f"Unknown injector implementation for mode={mode!r}: {name!r}")
