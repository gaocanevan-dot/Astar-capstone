"""
Parsers for various outputs and formats.
"""

import re
import json
from typing import List, Dict, Optional, Tuple


def parse_solidity_functions(source_code: str) -> List[Dict]:
    """
    解析 Solidity 源码中的函数定义。
    
    Returns:
        函数列表，每个函数包含:
        - name: 函数名
        - visibility: 可见性 (public, external, internal, private)
        - modifiers: 修饰符列表
        - parameters: 参数列表
        - returns: 返回值
        - is_state_changing: 是否修改状态
    """
    functions = []
    
    # 函数定义正则
    # 匹配: function name(params) visibility modifiers returns (type) { ... }
    func_pattern = re.compile(
        r'function\s+(\w+)\s*\(([^)]*)\)\s*'
        r'(public|external|internal|private)?\s*'
        r'((?:\w+\s*)*?)\s*'
        r'(?:returns\s*\(([^)]*)\))?\s*'
        r'[{;]',
        re.MULTILINE
    )
    
    # 状态修改函数的关键字
    state_changing_keywords = ['=', 'delete', 'push', 'pop', 'transfer', 'send', 'call']
    pure_view_keywords = ['pure', 'view']
    
    matches = func_pattern.finditer(source_code)
    
    for match in matches:
        name = match.group(1)
        params = match.group(2).strip() if match.group(2) else ""
        visibility = match.group(3) or "internal"
        modifiers_str = match.group(4).strip() if match.group(4) else ""
        returns = match.group(5).strip() if match.group(5) else ""
        
        # 解析修饰符
        modifiers = []
        if modifiers_str:
            # 排除 visibility 和 state mutability
            mod_parts = modifiers_str.split()
            for mod in mod_parts:
                if mod not in ['public', 'external', 'internal', 'private', 
                               'pure', 'view', 'payable', 'virtual', 'override']:
                    modifiers.append(mod)
        
        # 判断是否修改状态
        is_state_changing = True
        for keyword in pure_view_keywords:
            if keyword in modifiers_str:
                is_state_changing = False
                break
        
        functions.append({
            "name": name,
            "visibility": visibility,
            "modifiers": modifiers,
            "parameters": params,
            "returns": returns,
            "is_state_changing": is_state_changing
        })
    
    return functions


def parse_solidity_modifiers(source_code: str) -> List[Dict]:
    """
    解析 Solidity 源码中的修饰符定义。
    """
    modifiers = []
    
    # modifier 定义正则
    modifier_pattern = re.compile(
        r'modifier\s+(\w+)\s*\(([^)]*)\)\s*{',
        re.MULTILINE
    )
    
    matches = modifier_pattern.finditer(source_code)
    
    for match in matches:
        name = match.group(1)
        params = match.group(2).strip() if match.group(2) else ""
        
        modifiers.append({
            "name": name,
            "parameters": params
        })
    
    return modifiers


def parse_forge_output(output: str) -> Dict:
    """
    解析 forge test 的输出。
    
    Returns:
        {
            "success": bool,
            "tests": [
                {
                    "name": str,
                    "status": "pass" | "fail",
                    "gas": int,
                    "reason": str (if failed)
                }
            ],
            "summary": {
                "passed": int,
                "failed": int,
                "total": int
            }
        }
    """
    result = {
        "success": False,
        "tests": [],
        "summary": {
            "passed": 0,
            "failed": 0,
            "total": 0
        }
    }
    
    # 尝试解析 JSON 输出
    try:
        json_output = json.loads(output)
        # 处理 JSON 格式的输出
        if isinstance(json_output, dict):
            return parse_forge_json_output(json_output)
    except json.JSONDecodeError:
        pass
    
    # 解析文本输出
    # 匹配测试结果行
    # [PASS] testFunction() (gas: 12345)
    # [FAIL. Reason: ...] testFunction() (gas: 12345)
    
    pass_pattern = re.compile(r'\[PASS\]\s+(\w+)\(\)\s+\(gas:\s+(\d+)\)')
    fail_pattern = re.compile(r'\[FAIL\.\s+Reason:\s+([^\]]+)\]\s+(\w+)\(\)')
    
    for match in pass_pattern.finditer(output):
        result["tests"].append({
            "name": match.group(1),
            "status": "pass",
            "gas": int(match.group(2)),
            "reason": None
        })
        result["summary"]["passed"] += 1
    
    for match in fail_pattern.finditer(output):
        result["tests"].append({
            "name": match.group(2),
            "status": "fail",
            "gas": 0,
            "reason": match.group(1)
        })
        result["summary"]["failed"] += 1
    
    result["summary"]["total"] = result["summary"]["passed"] + result["summary"]["failed"]
    result["success"] = result["summary"]["failed"] == 0
    
    return result


def parse_forge_json_output(json_output: Dict) -> Dict:
    """解析 forge test --json 的 JSON 输出"""
    result = {
        "success": True,
        "tests": [],
        "summary": {
            "passed": 0,
            "failed": 0,
            "total": 0
        }
    }
    
    # 遍历测试结果
    for contract_name, contract_results in json_output.items():
        if isinstance(contract_results, dict):
            for test_name, test_result in contract_results.items():
                if isinstance(test_result, dict):
                    status = "pass" if test_result.get("success", False) else "fail"
                    
                    result["tests"].append({
                        "name": test_name,
                        "status": status,
                        "gas": test_result.get("gas", 0),
                        "reason": test_result.get("reason")
                    })
                    
                    if status == "pass":
                        result["summary"]["passed"] += 1
                    else:
                        result["summary"]["failed"] += 1
                        result["success"] = False
    
    result["summary"]["total"] = result["summary"]["passed"] + result["summary"]["failed"]
    
    return result


def extract_revert_reason(output: str) -> Optional[str]:
    """从输出中提取 Revert 原因"""
    # 常见的 revert 原因模式
    patterns = [
        r'revert:\s*(.+?)(?:\n|$)',
        r'Reason:\s*(.+?)(?:\n|$)',
        r'Error:\s*(.+?)(?:\n|$)',
        r'reverted with reason string\s*["\'](.+?)["\']',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def is_access_control_revert(output: str) -> bool:
    """判断是否是访问控制导致的 Revert"""
    access_keywords = [
        'owner',
        'admin',
        'unauthorized',
        'access',
        'permission',
        'role',
        'denied',
        'forbidden',
        'only',
        'caller is not'
    ]
    
    lower_output = output.lower()
    for keyword in access_keywords:
        if keyword in lower_output:
            return True
    
    return False
