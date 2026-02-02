"""
Data Formatter - 数据格式转换器

将数据转换为各种 LLM 训练格式。
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Literal


class DataFormatter:
    """
    数据格式转换器
    
    支持转换为多种 LLM 微调格式
    """
    
    @staticmethod
    def to_openai_chat_format(
        system_prompt: str,
        user_input: str,
        assistant_output: str
    ) -> Dict:
        """转换为 OpenAI Chat 微调格式"""
        return {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": assistant_output}
            ]
        }
    
    @staticmethod
    def to_alpaca_format(
        instruction: str,
        input_text: str,
        output_text: str
    ) -> Dict:
        """转换为 Alpaca 格式"""
        return {
            "instruction": instruction,
            "input": input_text,
            "output": output_text
        }
    
    @staticmethod
    def to_sharegpt_format(
        conversations: List[Dict]
    ) -> Dict:
        """
        转换为 ShareGPT 格式
        
        conversations: [{"from": "human|gpt", "value": "..."}]
        """
        return {
            "conversations": conversations
        }
    
    @staticmethod
    def format_contract_for_prompt(
        contract_source: str,
        contract_name: str = ""
    ) -> str:
        """格式化合约代码用于提示"""
        header = f"Contract: {contract_name}\n" if contract_name else ""
        return f"{header}```solidity\n{contract_source}\n```"
    
    @staticmethod
    def format_analysis_output(
        is_vulnerable: bool,
        vulnerable_functions: List[str],
        vulnerability_type: str,
        hypothesis: str
    ) -> str:
        """格式化分析输出"""
        result = {
            "is_vulnerable": is_vulnerable,
            "vulnerable_functions": vulnerable_functions,
            "vulnerability_type": vulnerability_type,
            "hypothesis": hypothesis
        }
        return json.dumps(result, indent=2)
    
    @staticmethod
    def create_analysis_prompt() -> str:
        """创建分析任务的系统提示"""
        return """You are a smart contract security auditor specializing in access control vulnerabilities.

Analyze the given Solidity contract and identify:
1. Functions that should have access control but don't
2. Incorrect or bypassable access control checks
3. Privilege escalation vulnerabilities

Focus ONLY on:
- Access Control vulnerabilities (missing onlyOwner, incorrect role checks)
- Privilege Escalation vulnerabilities (unauthorized ownership transfer, role manipulation)

Output your analysis as JSON with this structure:
{
    "is_vulnerable": true/false,
    "vulnerable_functions": ["function1", "function2"],
    "vulnerability_type": "access_control" or "privilege_escalation",
    "hypothesis": "Description of the vulnerability"
}"""
    
    @staticmethod
    def create_poc_prompt() -> str:
        """创建 PoC 生成任务的系统提示"""
        return """You are a security researcher who writes Foundry test cases to verify access control vulnerabilities.

Given a contract, target function, and vulnerability hypothesis, generate a minimal Foundry test that:
1. Deploys the target contract
2. Creates an unauthorized address (attacker)
3. Attempts to call the vulnerable function as the attacker
4. Asserts that the unauthorized action succeeded (proving the vulnerability)

The test should PASS if the vulnerability exists (attack succeeds).
The test should FAIL (revert) if access control works correctly.

Use these Foundry features:
- vm.prank(address) - impersonate an address for one call
- makeAddr("name") - create a labeled address
- assertEq(a, b) - assert equality

Output ONLY the Solidity test code."""

    @classmethod
    def batch_convert(
        cls,
        examples: List[Dict],
        output_format: Literal["openai", "alpaca", "sharegpt"],
        output_path: str
    ):
        """
        批量转换数据格式
        
        Args:
            examples: 原始样本列表
            output_format: 目标格式
            output_path: 输出文件路径
        """
        converted = []
        
        for ex in examples:
            if output_format == "openai":
                converted.append(cls.to_openai_chat_format(
                    system_prompt=ex.get("system", ""),
                    user_input=ex.get("input", ""),
                    assistant_output=ex.get("output", "")
                ))
            elif output_format == "alpaca":
                converted.append(cls.to_alpaca_format(
                    instruction=ex.get("instruction", ""),
                    input_text=ex.get("input", ""),
                    output_text=ex.get("output", "")
                ))
            elif output_format == "sharegpt":
                converted.append(cls.to_sharegpt_format(
                    conversations=ex.get("conversations", [])
                ))
        
        # 保存为 JSONL
        with open(output_path, 'w', encoding='utf-8') as f:
            for item in converted:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        print(f"Converted {len(converted)} examples to {output_format} format")
        print(f"Saved to: {output_path}")


def create_few_shot_examples() -> List[Dict]:
    """
    创建 Few-shot 示例
    
    用于在提示中提供参考案例
    """
    return [
        {
            "contract": """
contract VulnerableVault {
    address public owner;
    uint256 public fee;
    
    constructor() {
        owner = msg.sender;
    }
    
    function setFee(uint256 _fee) public {  // Missing onlyOwner!
        fee = _fee;
    }
    
    function withdraw() public {  // Missing onlyOwner!
        payable(owner).transfer(address(this).balance);
    }
}
""",
            "analysis": {
                "is_vulnerable": True,
                "vulnerable_functions": ["setFee", "withdraw"],
                "vulnerability_type": "access_control",
                "hypothesis": "setFee and withdraw functions lack access control - anyone can modify fee or trigger withdrawals"
            },
            "poc": """
function test_AnyoneCanSetFee() public {
    address attacker = makeAddr("attacker");
    
    // Attacker sets fee
    vm.prank(attacker);
    vault.setFee(999);
    
    // Fee was changed - vulnerability confirmed
    assertEq(vault.fee(), 999);
}
"""
        },
        {
            "contract": """
contract SecureVault {
    address public owner;
    uint256 public fee;
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }
    
    constructor() {
        owner = msg.sender;
    }
    
    function setFee(uint256 _fee) public onlyOwner {
        fee = _fee;
    }
}
""",
            "analysis": {
                "is_vulnerable": False,
                "vulnerable_functions": [],
                "vulnerability_type": None,
                "hypothesis": "No access control vulnerability found - setFee is properly protected by onlyOwner modifier"
            }
        }
    ]
