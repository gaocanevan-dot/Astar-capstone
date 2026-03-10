#!/usr/bin/env python3
"""
根据 data/contracts/mapping.json，把本地 .sol 文件内容填进
data/dataset/vulnerabilities.json 里对应 case 的 contract_source（及可选的 contract_name）。

mapping.json 格式示例：
{
  "CSW-H-01": {
    "path": "data/contracts/raw/CSW/CoinbaseSmartWallet.sol",
    "contract_name": "CoinbaseSmartWallet"
  },
  "GRA-H-02": "data/contracts/raw/GRA/GraphTokenUpgradeable.sol"
}
path 相对项目根目录；contract_name 可选，不写则只填 contract_source。
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
MAPPING_PATH = ROOT / "data" / "contracts" / "mapping.json"
DATASET_PATH = ROOT / "data" / "dataset" / "vulnerabilities.json"


def main():
    if not MAPPING_PATH.exists():
        print(f"Mapping not found: {MAPPING_PATH}")
        print("Create it with incident_id -> path or {path, contract_name}.")
        return

    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}")
        return

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("cases", [])
    id_to_index = {c["id"]: i for i, c in enumerate(cases)}

    updated = 0
    for incident_id, value in mapping.items():
        if incident_id not in id_to_index:
            print(f"Skip: no case with id={incident_id}")
            continue

        if isinstance(value, str):
            path_rel = value
            contract_name_override = None
        else:
            path_rel = value.get("path")
            contract_name_override = value.get("contract_name")
        if not path_rel:
            print(f"Skip: no path for {incident_id}")
            continue

        path_abs = ROOT / path_rel
        if not path_abs.exists():
            print(f"Skip: file not found {path_abs}")
            continue

        source = path_abs.read_text(encoding="utf-8")
        idx = id_to_index[incident_id]
        cases[idx]["contract_source"] = source
        if contract_name_override:
            cases[idx]["contract_name"] = contract_name_override
        updated += 1
        print(f"Filled: {incident_id} <- {path_rel}")

    if updated:
        with open(DATASET_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Updated {updated} case(s) in {DATASET_PATH}")
    else:
        print("No cases updated.")


if __name__ == "__main__":
    main()
