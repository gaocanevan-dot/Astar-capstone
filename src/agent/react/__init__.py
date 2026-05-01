"""Day-5 ReAct-style agent.

A real LLM-driven loop where the model decides each next action via tool
calls. Lives alongside (does not replace) `agent.graph::run_pipeline`,
which stays as the Day-4 baseline / fallback path.

Public entry: `run_react_agent(case, memory_backend, ...)` in `loop.py`.
"""

from agent.react.loop import AgentResult, run_react_agent  # noqa: F401
from agent.react.state import AgentState  # noqa: F401
from agent.react.trace import Trace, TraceStep  # noqa: F401

__all__ = ["AgentResult", "AgentState", "Trace", "TraceStep", "run_react_agent"]
