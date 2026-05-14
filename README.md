# Smart Contract Access Control Vulnerability Agent

一个面向智能合约**访问控制 / 权限升级漏洞**的研究原型，闭环流程：

```
合约源码 → Analyst (LLM) → Builder (LLM 写 PoC) → Verifier (Foundry forge test) → 通过/重试/放弃
```

不只做"代码扫描"，而是**生成可执行的攻击 PoC 并用 Foundry 实际验证**。

---

## 当前实验状态（2026-05-14）

| 指标 | 数 |
|---|---|
| 数据集规模 | **190 cases**（118 c5 本地 + 54 c4 GitHub 抓取 + 18 snippet 降级）|
| Ground-truth coverage | 178/190 有真函数名标签 |
| 完整源文件可编译尝试 | 172/190 (90.5%) |
| 4-arm ablation 已完成 | ✅ 每 arm × 172 cases |
| Total LLM cost | $3.77 (gpt-5-mini) |
| Wall-clock | 9.5 小时 |

### 4-arm Ablation 主表（172 cases / arm）

| arm | strict R@1 | hit@3 | PoC-pass | phantom-pass | $/case |
|---|---|---|---|---|---|
| **A1 full-cascade** | 43% | **59%** | 83% | 42% | $0.0102 |
| **A2 no-cascade**   | 43% | 43% | 78% | 41% | $0.0093 |
| **A3 gpt-zeroshot** | 42% | 54% | **87%** | 45% | $0.0037 |
| **A4 slither**      | 0% (172/172 编译失败) | 0% | 0% | - | $0 |

可视化：`data/evaluation/figures/*.png`

**关键发现**：
- A1 vs A2 → cascade router 把 hit@3 拉高 16pp（cascade 找对函数但未必排第一）
- A1 vs A3 → 完整 agent 在 R@1 上几乎没赢 zero-shot，但 hit@3 +5pp、成本贵 3 倍
- A4 → Slither 在隔离环境无法编译真实 Code4rena 合约（动机：未来 MCC 工作）
- **Phantom-pass 现象**：40%+ 的 "PoC pass" 实际是 builder 自己写的 mini-replica 自给自足攻击，**不是攻击原合约**。这是 inline-replica 时代的注水，未来 MCC 完成后会消失

---

## 项目结构

```
capstone/
├── src/agent/                        # 主代码包（installable as `agent`）
│   ├── state.py                      # AuditCore + AuditAnnotations
│   ├── graph.py                      # 线性 pipeline + cascade router + reflection wedge
│   ├── graph_lg.py                   # LangGraph 4-arm（full/no-static/no-rag/no-verify-loop）
│   ├── nodes/                        # analyst / analyst_with_tools / builder / verifier / reflector
│   ├── adapters/                     # llm.py / foundry.py / rag.py / static_analyzer.py
│   ├── baselines/                    # gpt_zeroshot.py / slither_baseline.py
│   ├── memory/                       # pattern / episodic / lesson stores
│   ├── react/                        # ReAct loop + tools + prompts
│   ├── rag/                          # RAG strategy registry (anti_pattern / null)
│   ├── eval/                         # metrics + runner + report
│   └── data/                         # pydantic Case schema + loader
│
├── scripts/
│   ├── source_fetcher/               # Phase 0 数据补全管线
│   │   ├── local_copier.py           # P_local: 118 case 从 Repair-Access-Control-C 拷
│   │   ├── gh_client.py              # GitHub REST API client (PAT via ~/.config/claude/mcp.env)
│   │   ├── c4_fetcher.py             # P_mcp: 72 case 从 c4 issue → 上游源码
│   │   ├── run_c4_fetch.py           # P_mcp 驱动
│   │   ├── reconcile_snippet_fallback.py  # F4: 死链 case 用 CSV snippet 降级
│   │   └── update_eval_set.py        # 重建 eval_set.json (190 cases)
│   │
│   ├── mcc/                          # Week 1 MCC infrastructure（Day 1-2 完成）
│   │   ├── case_loader.py            # eval_set → CaseInfo (target_file, pragma, project_root)
│   │   └── extract_closure.py        # BFS import graph, MAX_FILES=10
│   │
│   ├── run_ablation_sweep.py         # 4-arm × 172-case sweep 主驱动（resume + cost guard）
│   ├── run_b_smoke.py                # 单 arm 烟雾测试
│   ├── run_full_pipeline.py          # 旧 driver (legacy 42-case schema)
│   └── plot_sweep.py                 # 用 matplotlib 出 4 张 PNG + metrics.json
│
├── tests/unit/                       # 210+ unit tests（含新增 15 个 MCC 测试）
│
├── data/
│   ├── dataset/
│   │   ├── access_control_dataset.csv             # 190 case 元数据（来源 CSV）
│   │   ├── c5_access_control_dataset_118.csv      # 118 c5 子集
│   │   ├── source_map_118.csv                     # incident_id → Repair 内 .sol 路径
│   │   ├── eval_set.json                          # ★ 当前使用的 190-case dataset
│   │   ├── source_unresolved.json                 # 18 case 死链 manifest
│   │   └── Repair-Access-Control-C-main/          # 学术外部数据（gitignored, 122MB）
│   │
│   ├── contracts/
│   │   ├── VulnerableAccessControl.sol            # 玩具 demo
│   │   ├── raw/                                   # 172 个 case 的本地源文件 (32MB)
│   │   │   ├── ACF-001/                           # incident_id 子目录，含 target + siblings
│   │   │   └── ...
│   │   ├── raw_local_index.json                   # P_local manifest
│   │   └── raw_c4_index.json                      # P_mcp manifest
│   │
│   └── evaluation/
│       ├── sweep_A1_full_cascade.json             # ★ ablation 数据
│       ├── sweep_A2_no_cascade.json
│       ├── sweep_A3_gpt_zeroshot.json
│       ├── sweep_A4_slither.json
│       ├── sweep_summary.md                       # ★ ablation 主表
│       └── figures/
│           ├── headline_metrics.png
│           ├── recall_comparison.png
│           ├── cost_vs_recall.png
│           ├── verdict_distribution.png
│           └── metrics.json
│
├── docs/
│   ├── ARCHITECTURE.md                # 单 Agent 变体架构说明
│   ├── FEASIBILITY_REPORT.md          # 早期可行性报告（v0.4，部分数字已被 ablation sweep 取代）
│   ├── WEEK1_MCC_SPIKE.md             # MCC Week 1 Day-by-day 计划
│   ├── RUN.md                         # 复现步骤
│   └── methodology/                   # Day-by-day 方法学日志
│
├── lib/vendored/                      # Solidity deps (gitignored, 51MB)
│                                      # 由 scripts/source_fetcher/install_libs.sh 安装
└── framework.md                       # 原始设计稿
```

---

## 环境依赖

| 工具 | 版本 |
|---|---|
| Python | 3.10+（实测 3.14.4）|
| Foundry | 1.7.1+（forge / cast / anvil）|
| solc-select | 1.2+（管理多版本 solc）|
| OpenAI API | gpt-5-mini（项目默认） |

---

## 快速开始

### 1. 装环境

```bash
# Foundry
curl -L https://foundry.paradigm.xyz | bash && ~/.foundry/bin/foundryup

# solc-select + 5 个 solc 版本（覆盖 2020-2024 合约）
pip install solc-select
solc-select install 0.6.12 0.7.6 0.8.10 0.8.20 0.8.23

# Python venv + 项目依赖
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]" slither-analyzer matplotlib

# Solidity vendored libs（OZ v3/v4/v5 + Solady + forge-std + solmate, ~51MB）
bash scripts/source_fetcher/install_libs.sh
```

### 2. 配 API key

```bash
cp .env.example .env
# 编辑 .env 填 OPENAI_API_KEY
```

### 3. 准备数据集（已包含在 repo 内的 eval_set.json 含 190 case）

若要重建（需要 GitHub PAT 用于 c4 抓取）：

```bash
# 把 GitHub PAT 写到 ~/.config/claude/mcp.env (单行: GITHUB_PERSONAL_ACCESS_TOKEN=...)
echo "GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxx" > ~/.config/claude/mcp.env
chmod 600 ~/.config/claude/mcp.env

# P_local + P_mcp + snippet fallback
.venv/bin/python -m scripts.source_fetcher.local_copier
.venv/bin/python -m scripts.source_fetcher.update_eval_set
.venv/bin/python -m scripts.source_fetcher.run_c4_fetch
.venv/bin/python -m scripts.source_fetcher.reconcile_snippet_fallback
```

### 4. 跑 ablation sweep

```bash
# 后台跑 ~9 小时,$3-5
.venv/bin/python scripts/run_ablation_sweep.py

# 或者仅一个 arm 烟雾测试 (10 cases)
.venv/bin/python scripts/run_b_smoke.py --limit 10
```

### 5. 出图

```bash
.venv/bin/python scripts/plot_sweep.py
# → data/evaluation/figures/*.png
```

### 6. 跑单元测试

```bash
.venv/bin/python -m pytest tests/unit/ -v
```

---

## 数据集说明

`access_control_dataset.csv` 190 case 来自：
- **c5 (118)**: `c5_access_control_dataset_118.csv`（学术 corpus，源码本地在 `Repair-Access-Control-C-main/` 内）
- **c4 (72)**: Code4rena GitHub findings（issue body 内含上游源码 URL，通过 GitHub MCP/REST 抓取）

数据补全管线：
1. **P_local**：118 c5 case 直接从 Repair-Access-Control-C 复制 `.sol` + 同目录 siblings（cap=20）
2. **P_mcp**：72 c4 case 解析 issue body 内的 `https://github.com/.../blob/<sha>/<path>.sol#L...` → REST API 拉文件 + repo 树
3. **F4 fallback**：18 个上游已删除的 c4 case 用 CSV `vulnerable_code` snippet 降级（analyst-only 评估）

---

## Ablation 设计

4 arm 在同一份 N=172 数据上跑（snippet_only 18 case 默认跳过）：

| arm | 实现 | 目的 |
|---|---|---|
| A1 full-cascade | `graph.run_pipeline()` 默认 | 当前完整 pipeline baseline |
| A2 no-cascade   | `use_cascade=False` (top-1 only) | 消融 cascade router |
| A3 gpt-zeroshot | `baselines.gpt_zeroshot.evaluate()` | LLM 单次 prompt baseline |
| A4 slither      | `baselines.slither_baseline.evaluate()` | 业界静态工具基线 |

详细配对解读：
- A1 vs A2 → cascade router 的贡献
- A1 vs A3 → 完整 pipeline vs zero-shot LLM
- A1 vs A4 → LLM agent vs 静态工具

---

## 当前已知局限

1. **Phantom-pass 注水**：~42% 的 PoC-pass 实际是 builder 自给自足攻击 inline mini-replica，**不是攻击原合约**。这是 inline-replica 时代的方法学硬伤
2. **Slither 全编译失败**：Code4rena 真实合约依赖太深，隔离环境无法链接 — `A4 = 0/172` 反映**工程问题**，不是 Slither 弱
3. **N=190 仍偏小**：Wilson 95% CI 在 R=0.43 处约 ±7pp
4. **无 safe-case 集**：当前 dataset 全是 vulnerable，无法报 Precision/FPR/F1
5. **18 snippet-only case 不参与 forge build**：上游 repo 永久删除，只能用 CSV 漏洞片段做 analyst-only 评估
6. **prompt SHA / model fingerprint 未 pin**：复现性 best-effort

未来工作：
- **MCC (Minimal Compilable Closure)**：让 builder 写 `import "src/X.sol"` 直接 attack 原合约，消灭 phantom-pass — Day 1-2 infra 已完成
- 扩 safe-case 集 → 解锁 Precision/F1
- bootstrap CI + paired bootstrap p-value
- 跨漏洞类型扩展

---

## 关键脚本入口

| 命令 | 作用 |
|---|---|
| `python scripts/run_ablation_sweep.py` | **核心实验** — 4-arm × N=172 |
| `python scripts/plot_sweep.py` | 出 4 张 PNG |
| `python -m scripts.source_fetcher.local_copier` | 重建 c5 本地源 |
| `python -m scripts.source_fetcher.run_c4_fetch` | 重新抓 c4 上游源 |
| `python -m scripts.mcc.case_loader <id>` | 调试单 case |
| `python -m scripts.mcc.extract_closure <id>` | 调试闭包提取 |
| `python -m pytest tests/unit/ -q` | 跑全部 unit test |

---

## License

MIT
