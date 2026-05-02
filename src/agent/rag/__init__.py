"""Day-6 RAG injection module — separable from ReAct loop.

This package is intentionally decoupled from `agent.react.*` so that
ablation studies (Day-7 episodic, future hybrid injectors, alternative
embedding models) can be implemented as new `RAGInjector` subclasses
without modifying the loop.

Public surface:
    - RAGInjector (base.py): abstract interface
    - NullInjector (null_injector.py): no-op for baseline arms
    - AntiPatternInjector (anti_pattern_injector.py): Day-6 implementation
    - get_injector (registry.py): factory keyed by mode string

Loop integration contract (loop.py):
    1. At each iteration, BEFORE issuing the next LLM call, ask
       `injector.should_inject(case, state, next_tool)`.
    2. If True, call `injector.build_payload(case, memory)` and append a
       synthetic assistant+tool message pair to the conversation.
    3. Set `state.rag_injection_fired = True` and record
       `state.rag_retrieved_pattern_ids`.

The synthetic payload MUST include `source` key (per AC15).
"""

from agent.rag.base import RAGInjector
from agent.rag.null_injector import NullInjector
from agent.rag.registry import get_injector

__all__ = ["RAGInjector", "NullInjector", "get_injector"]
