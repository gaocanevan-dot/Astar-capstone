"""ReAct tool registry: 11 tools split into 3 categories.

Each tool has:
- An OpenAI function-calling schema (for the model)
- An implementation function (for dispatch)

The implementations live in this file as wrappers around existing modules
(`agent.adapters.static_analyzer`, `agent.nodes.builder`, `agent.nodes.verifier`,
`agent.memory.*`). The wrappers convert structured returns to string
observations the model can consume.

R8 GUARDS:
- `run_forge` enforces a per-case-call counter (max 4) inside its dispatcher
- Memory tools never raise (errors are returned as observation strings)
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from agent.react.state import AgentState


# ---------------------------------------------------------------------------
# OpenAI function-calling schemas (passed verbatim to chat_with_tools)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    # ----- Action -----
    {
        "type": "function",
        "function": {
            "name": "propose_target",
            "description": "Mark a candidate function as your current hypothesis target. Required before write_poc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_function": {"type": "string", "description": "Exact function name from the contract."},
                    "hypothesis": {"type": "string", "description": "One-sentence vulnerability hypothesis."},
                },
                "required": ["target_function", "hypothesis"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_poc",
            "description": "Generate a Foundry .t.sol PoC test for the proposed target. Returns the generated PoC code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_function": {"type": "string"},
                    "exploit_logic": {"type": "string", "description": "Brief description of how the exploit works."},
                },
                "required": ["target_function", "exploit_logic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_forge",
            "description": "Execute the most recently generated PoC against the original contract via forge test. Returns verdict (pass | fail_revert_ac | fail_error_compile | fail_error_runtime) and error_summary.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_finding",
            "description": "Terminal: declare a confirmed vulnerability. Call AFTER run_forge returned 'pass'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_function": {"type": "string"},
                    "evidence": {"type": "string", "description": "Reference to the passing forge run + brief explanation."},
                },
                "required": ["target_function", "evidence"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "give_up",
            "description": "Terminal: declare you cannot prove a vulnerability within remaining budget. Honest abandonment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Concrete reason (compile errors, runtime stuck, exhausted candidates...)."},
                },
                "required": ["reason"],
            },
        },
    },
    # ----- Inspection -----
    {
        "type": "function",
        "function": {
            "name": "list_functions",
            "description": "Return all functions in the contract with visibility + modifiers (via Slither if available, regex fallback otherwise). Output includes `tool_used` field.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_function_body",
            "description": "Return the body source of a specific function by name (regex slice — best-effort).",
            "parameters": {
                "type": "object",
                "properties": {"function_name": {"type": "string"}},
                "required": ["function_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "static_analyze",
            "description": "Run the suspicious-summary filter (external + state-changing + no AC modifier). Strictly stronger than list_functions for narrowing.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_imports",
            "description": "Inspect contract imports — flags sibling-relative paths (../*.sol) and external libs (OpenZeppelin, solady, etc.) that may break compilation against original.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    # ----- Memory -----
    {
        "type": "function",
        "function": {
            "name": "recall_anti_pattern",
            "description": "Retrieve top-3 access-control anti-patterns matching a query (e.g. 'missing modifier on state-changing setter').",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_similar_cases",
            "description": "Retrieve top-3 past audit cases (episodic memory) similar to the current contract.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_self_lesson",
            "description": "Retrieve top-3 self-distilled lessons from prior agent runs matching a query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_lesson",
            "description": "Append a short, reusable rule-of-thumb to your self-lesson memory. Use when you discover a pattern likely to recur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trigger": {"type": "string", "description": "Observable signal that should remind you of this lesson next time (≤120 chars)."},
                    "takeaway": {"type": "string", "description": "What to do / check when you see the trigger (≤200 chars)."},
                },
                "required": ["trigger", "takeaway"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations (string-observation contract)
# ---------------------------------------------------------------------------

# Per-case run_forge call counter (R8 partial — caps repeated forge use)
RUN_FORGE_LIMIT = 4

# Imports we treat as "external library" for check_imports
_EXTERNAL_PREFIXES = (
    "@openzeppelin/", "@oz/", "solady/", "@account-abstraction/",
    "@uniswap/", "@chainlink/", "ds-test/", "forge-std/",
)
_SIBLING_IMPORT_RE = re.compile(r'import\s+(?:[^"\']*from\s+)?["\']\.\./[^"\']+["\']')
_NAMED_IMPORT_RE = re.compile(r'import\s+(?:[^"\']*from\s+)?["\']([^"\']+)["\']')
_FN_BODY_RE_TMPL = (
    r"function\s+{name}\s*\([^)]*\)[^{{]*\{{(?P<body>(?:[^{{}}]|\{{[^{{}}]*\}})*)\}}"
)


def _truncate(s: str, n: int = 4000) -> str:
    return s if len(s) <= n else s[:n] + f"\n\n// ... (truncated; {len(s)} chars total)"


def tool_propose_target(args: dict, case: dict, mem, state: AgentState) -> str:
    target = (args.get("target_function") or "").strip()
    hyp = (args.get("hypothesis") or "").strip()
    if not target:
        return json.dumps({"ok": False, "error": "target_function required"})
    state.annotations["target_function"] = target
    state.annotations["hypothesis"] = hyp[:500]
    return json.dumps({"ok": True, "target_function": target, "hypothesis": hyp[:200]})


def tool_write_poc(args: dict, case: dict, mem, state: AgentState) -> str:
    from agent.nodes.builder import build_poc

    target = (args.get("target_function") or state.annotations.get("target_function") or "").strip()
    if not target:
        return json.dumps({"ok": False, "error": "no target_function — call propose_target first"})
    hyp = (args.get("exploit_logic") or state.annotations.get("hypothesis") or "").strip()

    try:
        poc = build_poc(
            contract_source=case.get("contract_source", ""),
            contract_name=case.get("contract_name", ""),
            target_function=target,
            hypothesis=hyp,
            error_history=list(state.annotations.get("error_history", [])),
            annotations=state.annotations,
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    state.annotations["verification_poc"] = poc
    return json.dumps({"ok": True, "poc_chars": len(poc), "poc_preview": _truncate(poc, 1500)})


def tool_run_forge(args: dict, case: dict, mem, state: AgentState) -> str:
    from agent.nodes.verifier import verify

    forge_count = int(state.annotations.get("forge_calls_this_case", 0))
    if forge_count >= RUN_FORGE_LIMIT:
        return json.dumps({
            "ok": False,
            "error": f"per-case run_forge limit ({RUN_FORGE_LIMIT}) reached",
        })
    poc = state.annotations.get("verification_poc", "")
    if not poc:
        return json.dumps({"ok": False, "error": "no PoC yet — call write_poc first"})

    try:
        verdict = verify(
            contract_source=case.get("contract_source", ""),
            contract_name=case.get("contract_name", ""),
            poc_code=poc,
            verifier_mode=case.get("verifier_mode"),
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    state.annotations["forge_calls_this_case"] = forge_count + 1
    state.last_forge_verdict = verdict.get("execution_result", "")
    eh = list(state.annotations.get("error_history", []))
    if state.last_forge_verdict.startswith("fail_error"):
        eh.append(verdict.get("error_summary", ""))
        state.annotations["error_history"] = eh
    return json.dumps({
        "ok": True,
        "verdict": state.last_forge_verdict,
        "error_summary": verdict.get("error_summary", "")[:300],
        "calls_used": forge_count + 1,
        "calls_remaining": max(0, RUN_FORGE_LIMIT - (forge_count + 1)),
    })


def tool_submit_finding(args: dict, case: dict, mem, state: AgentState) -> str:
    target = (args.get("target_function") or state.annotations.get("target_function") or "").strip()
    evidence = (args.get("evidence") or "").strip()
    state.submitted_target = target
    state.submitted_evidence = evidence[:600]
    state.submitted_hypothesis = state.annotations.get("hypothesis", "")
    return json.dumps({"ok": True, "terminal": "submit_finding"})


def tool_give_up(args: dict, case: dict, mem, state: AgentState) -> str:
    reason = (args.get("reason") or "").strip()
    state.given_up_reason = reason[:400]
    return json.dumps({"ok": True, "terminal": "give_up", "reason": reason[:200]})


def tool_list_functions(args: dict, case: dict, mem, state: AgentState) -> str:
    from agent.adapters.static_analyzer import analyze as static_analyze

    try:
        facts = static_analyze(case.get("contract_source", ""), case.get("contract_name", ""))
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    fns = [
        {"name": fn.name, "visibility": fn.visibility, "modifiers": fn.modifiers, "state_changing": fn.state_changing}
        for fn in facts.functions[:60]
    ]
    return json.dumps({
        "ok": True,
        "tool_used": facts.tool,
        "n_total": len(facts.functions),
        "functions": fns,
    })[:8000]


def tool_get_function_body(args: dict, case: dict, mem, state: AgentState) -> str:
    name = (args.get("function_name") or "").strip()
    if not name:
        return json.dumps({"ok": False, "error": "function_name required"})
    src = case.get("contract_source", "")
    pattern = _FN_BODY_RE_TMPL.format(name=re.escape(name))
    m = re.search(pattern, src, re.DOTALL)
    if not m:
        return json.dumps({"ok": False, "error": f"function {name!r} not found by regex slice"})
    return json.dumps({"ok": True, "name": name, "body": _truncate(m.group("body").strip(), 2000)})


def tool_static_analyze(args: dict, case: dict, mem, state: AgentState) -> str:
    from agent.adapters.static_analyzer import analyze as static_analyze

    try:
        facts = static_analyze(case.get("contract_source", ""), case.get("contract_name", ""))
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return json.dumps({
        "ok": True,
        "tool_used": facts.tool,
        "suspicious_summary": facts.suspicious_summary()[:3000],
    })


def tool_check_imports(args: dict, case: dict, mem, state: AgentState) -> str:
    src = case.get("contract_source", "")
    sibling = _SIBLING_IMPORT_RE.findall(src)
    externals = []
    for m in _NAMED_IMPORT_RE.finditer(src):
        ref = m.group(1)
        if any(ref.startswith(p) for p in _EXTERNAL_PREFIXES):
            externals.append(ref)
    return json.dumps({
        "ok": True,
        "n_sibling_imports": len(sibling),
        "sibling_imports": sibling[:10],
        "n_external_imports": len(externals),
        "external_imports": externals[:10],
        "compilation_risk": "high" if (sibling or externals) else "low",
    })


def tool_recall_anti_pattern(args: dict, case: dict, mem, state: AgentState) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return json.dumps({"ok": False, "error": "query required"})
    if mem is None:
        return json.dumps({"ok": True, "results": [], "note": "memory backend not wired (Phase 2)"})
    try:
        results = mem.recall_anti_pattern(query, top_k=3)
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return json.dumps({"ok": True, "n": len(results), "results": results})[:6000]


def tool_recall_similar_cases(args: dict, case: dict, mem, state: AgentState) -> str:
    if mem is None:
        return json.dumps({"ok": True, "results": [], "note": "memory backend not wired (Phase 2)"})
    try:
        results = mem.recall_similar_cases(case, top_k=3)
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return json.dumps({"ok": True, "n": len(results), "results": results})[:6000]


def tool_recall_self_lesson(args: dict, case: dict, mem, state: AgentState) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return json.dumps({"ok": False, "error": "query required"})
    if mem is None:
        return json.dumps({"ok": True, "results": [], "note": "memory backend not wired (Phase 2)"})
    try:
        results = mem.recall_self_lesson(query, top_k=3)
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    if results:
        # AC5b mechanical evidence — recall returned non-empty
        state.recall_self_lesson_nonempty += 1
    return json.dumps({"ok": True, "n": len(results), "results": results})[:6000]


def tool_save_lesson(args: dict, case: dict, mem, state: AgentState) -> str:
    trigger = (args.get("trigger") or "").strip()
    takeaway = (args.get("takeaway") or "").strip()
    if not (trigger and takeaway):
        return json.dumps({"ok": False, "error": "trigger and takeaway required"})
    if mem is None:
        return json.dumps({"ok": True, "saved": False, "note": "memory backend not wired (Phase 2)"})
    try:
        result = mem.save_lesson(trigger, takeaway, source_case_id=case.get("id"))
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return json.dumps({"ok": True, "saved": True, "lesson": result})


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

TOOL_DISPATCH: dict[str, Callable[..., str]] = {
    "propose_target": tool_propose_target,
    "write_poc": tool_write_poc,
    "run_forge": tool_run_forge,
    "submit_finding": tool_submit_finding,
    "give_up": tool_give_up,
    "list_functions": tool_list_functions,
    "get_function_body": tool_get_function_body,
    "static_analyze": tool_static_analyze,
    "check_imports": tool_check_imports,
    "recall_anti_pattern": tool_recall_anti_pattern,
    "recall_similar_cases": tool_recall_similar_cases,
    "recall_self_lesson": tool_recall_self_lesson,
    "save_lesson": tool_save_lesson,
}

TERMINAL_TOOLS: set[str] = {"submit_finding", "give_up"}


def dispatch_tool(
    tool_name: str,
    tool_args: dict,
    case: dict,
    memory_backend,  # None until S2 wires it
    state: AgentState,
) -> str:
    """Dispatch a tool call, returning a JSON-string observation. Errors
    are returned as `{"ok": false, "error": "..."}` rather than raised, so
    the agent loop can keep going."""
    fn = TOOL_DISPATCH.get(tool_name)
    if fn is None:
        return json.dumps({
            "ok": False,
            "error": f"unknown tool: {tool_name}. Valid tools: {sorted(TOOL_DISPATCH.keys())}",
        })
    try:
        return fn(tool_args, case, memory_backend, state)
    except Exception as exc:  # pragma: no cover — defensive
        return json.dumps({
            "ok": False,
            "error": f"tool dispatch failed: {type(exc).__name__}: {exc}",
        })
