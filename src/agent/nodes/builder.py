"""Builder node — generate a Foundry .t.sol test that triggers the
vulnerability hypothesis the analyst produced.

Interface:
    build_poc(contract_source, contract_name, target_function, hypothesis,
              error_history, annotations) -> str

Builder doesn't try to be clever; it's a thin prompt wrapper. The iteration
loop (retries) is managed in graph.py.
"""

from __future__ import annotations

import re

from agent.adapters.llm import invoke_json
from agent.state import AuditAnnotations


SYSTEM_PROMPT = """You are a Solidity security engineer. You write minimal
Foundry tests that DEMONSTRATE an access-control vulnerability.

Output STRICT JSON with exactly this shape:
{"poc_code": "full .t.sol file content including pragma and imports"}

**CRITICAL: the PoC file MUST be 100% self-contained.**
- NEVER write `import "../src/SomeContract.sol"` or similar.
- The test file must include an inline minimal replica of ONLY the vulnerable
  function(s) + any state the assertion needs (e.g. `owner`, `balances`).
- Do NOT replicate the whole contract — just the fields and functions your test
  will actually touch.
- If the target uses external dependencies (OpenZeppelin, custom interfaces),
  stub them with minimal inline interfaces or replace the calls with no-ops.
- Pragma MUST be `pragma solidity 0.8.20;` regardless of the target's original
  pragma. The replica you write is new code, you control its version.

PoC template:
```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import "forge-std/Test.sol";

// Minimal vulnerable replica (inline — do NOT import from ../src/)
contract {CONTRACT_NAME} {
    // only the state + functions your exploit touches
    address public owner;
    function {VULNERABLE_FUNCTION}(...) external {
        // minimal logic matching the real function's signature + missing AC
    }
}

contract {CONTRACT_NAME}Test is Test {
    {CONTRACT_NAME} target;
    address attacker;

    function setUp() public {
        target = new {CONTRACT_NAME}();
        attacker = makeAddr("attacker");
    }

    function test_attacker_exploits_{VULNERABLE_FUNCTION}() public {
        vm.prank(attacker);
        target.{VULNERABLE_FUNCTION}(...);
        // assert state changed — e.g. assertEq(target.owner(), attacker);
    }
}
```

Rules:
- Use `forge-std/Test.sol`.
- Use solidity 0.8.20 pragma always.
- The test function name must start with `test_`.
- Keep it under 80 lines total.
- Never use `vm.expectRevert` — we WANT the attack to succeed.
- If the analyst's hypothesis is about an initializer, show a stranger calls `initialize()` and becomes owner.
- If the hypothesis is a missing modifier, prank a stranger and assert state changed."""


USER_PROMPT_TEMPLATE = """Target contract name: {contract_name}
Target function (from analyst): {target_function}
Vulnerability hypothesis: {hypothesis}

Contract source:
```solidity
{contract_source}
```

{error_section}

Generate the Foundry .t.sol file that demonstrates this vulnerability.
Return JSON with key "poc_code"."""


def build_poc(
    contract_source: str,
    contract_name: str,
    target_function: str,
    hypothesis: str,
    error_history: list[str],
    annotations: AuditAnnotations,
) -> str:
    """Return the raw .t.sol code (cleaned)."""
    error_section = ""
    if error_history:
        # Bound the history shown to the model to avoid token blowup.
        recent = error_history[-3:]
        bullets = "\n".join(f"- {e[:400]}" for e in recent)
        error_section = (
            f"PREVIOUS ATTEMPTS FAILED WITH:\n{bullets}\n\n"
            "Fix the issue(s) in the new PoC. Common fixes: adjust function "
            "signature, use correct constructor args, remove unused imports."
        )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        contract_name=contract_name,
        target_function=target_function or "<unknown>",
        hypothesis=hypothesis or "missing access control on state-changing function",
        contract_source=_truncate(contract_source),
        error_section=error_section,
    )

    raw = invoke_json(SYSTEM_PROMPT, user_prompt, annotations)
    poc_code = _extract_poc_from_json(raw)
    return _clean_solidity(poc_code)


def _truncate(source: str, max_chars: int = 18000) -> str:
    if len(source) <= max_chars:
        return source
    return source[:max_chars] + f"\n\n// ... (truncated; original {len(source)} chars)"


def _extract_poc_from_json(raw: str) -> str:
    import json

    try:
        data = json.loads(raw)
        return data.get("poc_code", "") or ""
    except json.JSONDecodeError:
        # Fallback: if model emitted raw Solidity, look for a code block
        m = re.search(r"```solidity\s*(.*?)```", raw, re.DOTALL)
        if m:
            return m.group(1)
        m = re.search(r"```\s*(.*?)```", raw, re.DOTALL)
        if m:
            return m.group(1)
        return raw


def _clean_solidity(code: str) -> str:
    code = code.strip()
    if code.startswith("```solidity"):
        code = code[len("```solidity") :].lstrip()
    elif code.startswith("```"):
        code = code[3:].lstrip()
    if code.endswith("```"):
        code = code[:-3].rstrip()
    return code.strip()
