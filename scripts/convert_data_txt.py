#!/usr/bin/env python3
"""
将 data/data.txt 中整理的审计报告摘要，转换为
data/dataset/vulnerabilities.json，供 RAG 使用。

说明：
- 目前只提取「Access Control」和「Privilege Escalation」相关条目；
- contract_source 和 poc_code 先留空，后续可以手动补充；
- description 使用 root_cause + impact 拼接；
- severity 使用 metadata.priority_type（High/Medium/...）。
"""

import json
import re
from pathlib import Path


ROOT = Path(__file__).parent.parent
INPUT_PATH = ROOT / "data" / "data.txt"
OUTPUT_DIR = ROOT / "data" / "dataset"
OUTPUT_PATH = OUTPUT_DIR / "vulnerabilities.json"


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    text = INPUT_PATH.read_text(encoding="utf-8")

    # 非严格解析：data.txt 中每一段 [...] 是一个 JSON 数组
    # 我们用正则把所有方括号数组提取出来，然后逐个用 json.loads 解析
    arrays: list[list[dict]] = []
    for match in re.finditer(r"\[\s*{.*?}\s*\]", text, flags=re.DOTALL):
        block = match.group(0)
        try:
            arr = json.loads(block)
            if isinstance(arr, list):
                arrays.append(arr)
        except Exception:
            # 跳过无法解析的块
            continue

    cases = []

    for arr in arrays:
        for item in arr:
            try:
                incident_id = item.get("incident_id", "")
                metadata = item.get("metadata", {}) or {}
                vuln = item.get("vulnerability", {}) or {}
                loc = item.get("location", {}) or {}

                issue_category = (vuln.get("issue_category") or "").strip()

                # 只保留访问控制 / 权限升级相关
                is_access_control = "access control" in issue_category.lower()
                is_priv_escalation = "privilege escalation" in issue_category.lower()
                if not (is_access_control or is_priv_escalation):
                    continue

                vulnerability_type = (
                    "access_control" if is_access_control else "privilege_escalation"
                )

                contract_name = loc.get("contract_name") or (
                    vuln.get("affected_contracts") or [""]
                )[0]
                attack_surface = loc.get("attack_surface") or ""

                # 从 attack_surface 中尽量提取函数名（例如 "function foo(...)"）
                vulnerable_function = ""
                m = re.search(r"function\s+([A-Za-z0-9_]+)", attack_surface)
                if m:
                    vulnerable_function = m.group(1)

                root_cause = vuln.get("root_cause") or ""
                impact = vuln.get("impact") or ""
                description_parts = []
                if root_cause:
                    description_parts.append(root_cause)
                if impact:
                    description_parts.append(impact)
                description = " ".join(description_parts)

                severity = (metadata.get("priority_type") or "").lower()
                # 统一成 lower，保持简单

                fix_recommendation = ""  # 暂时留空，后续可手动补

                case = {
                    "id": incident_id or f"{contract_name}_{vulnerable_function}",
                    "contract_source": "",  # 以后补充真实 Solidity 代码
                    "contract_name": contract_name,
                    "vulnerable_function": vulnerable_function,
                    "vulnerability_type": vulnerability_type,
                    "severity": severity,
                    "description": description,
                    "poc_code": "",
                    "fix_recommendation": fix_recommendation,
                    # 额外保留一些原始信息，方便后续人工完善
                    "metadata": metadata,
                    "issue_category": issue_category,
                    "attack_surface": attack_surface,
                    "vulnerable_code_snippet": loc.get("vulnerable_code", ""),
                }

                cases.append(case)
            except Exception:
                # 单条出问题就跳过，避免影响整体转换
                continue

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"cases": cases}
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Converted {len(cases)} access-control-related cases to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

