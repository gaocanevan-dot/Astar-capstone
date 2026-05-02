"""Day-6 AntiPatternInjector — retrieves top-k anti_patterns and injects
them as a synthetic tool-result before the first propose_target call.

STATUS: SKELETON. Body implementation lands in Step 2 of v6 plan, after
Step 0a (blind buildability) + Step 0b (full audit) + Step 1 (holdout
freeze) all PASS. Step 0a may trigger Path B escalation, in which case
this module stays at skeleton state and the work pivots to a different
RAGInjector subclass (e.g., over a SmartBugs-curated library).

The skeleton is committed NOW to lock in the architectural boundary:
loop.py imports only from `agent.rag` package, never reaches into
concrete injector internals. Future ablations (EpisodicInjector,
HybridInjector) drop in as siblings without touching loop.py.
"""
from __future__ import annotations

from typing import Any, Mapping

from agent.rag.base import RAGInjector


class AntiPatternInjector(RAGInjector):
    """Inject top-k anti_patterns at the first `propose_target` step.

    Constructor parameters:
        k: number of top results to inject (default 3)
        max_chars: total char cap on rendered payload (default 1500)
                   — keeps within prompt-token budget per Architect v3
                   review (`prompts.py:101-119` truncates source at 4000)
    """

    name = "anti_pattern_at_propose"

    def __init__(self, k: int = 3, max_chars: int = 1500) -> None:
        self.k = k
        self.max_chars = max_chars

    def should_inject(
        self,
        case: Mapping[str, Any],
        state: Any,
        next_tool: str,
    ) -> bool:
        # Fires once per case, only when LLM is about to call propose_target.
        # Step 2 implementation. Skeleton returns False so this can be safely
        # imported and instantiated without changing loop behaviour.
        return False

    def build_payload(
        self,
        case: Mapping[str, Any],
        memory: Any,
    ) -> dict:
        # Step 2 implementation:
        #   1. Build a query from case['contract_name'] + vulnerable_code excerpt
        #   2. Call memory.recall_anti_pattern(query, k=self.k)
        #   3. Format results as a synthetic tool-result dict, char-capped
        #   4. Tag with source='system_injection_at_propose' (AC15)
        #   5. Record retrieved IDs for AC11 verifier
        return {
            "source": "system_injection_at_propose",
            "retrieved_ids": [],
            "rendered": "",
        }
