# Consensus Plan: 150-Bad-Case 访问控制漏洞检测新框架

**Status:** APPROVED (Planner v2 + Architect second-pass SOUND + Critic APPROVE with 2-line addendum folded in)
**Spec:** `.omc/specs/deep-interview-150-bad-case-detection.md`
**Companion task doc:** `.omc/plans/consensus-tasks-150bad.md`
**Mode:** RALPLAN-DR Short (non-interactive)
**Iterations:** Planner v1 → Architect v1 → Critic v1 (ITERATE) → Planner v2 → Architect v2 (SOUND) → Critic v2 (APPROVE) = 1 re-review round

---

## 1. Requirements Summary

构建一个全新的、基于 LangGraph 的访问控制漏洞检测 Agent 框架。评测集 = 150 真实 Code4rena/SWC bad case + ~50 safe case,经 **stratified 75/25 dev + 75/25 test 切分后冻结**。在 held-out test 子集上,合约级 Precision/Recall/F1 均 ≥ 0.60,Function-Recall ≥ 0.35,Recall 显著优于 Slither baseline(≥ +8 pts)。现有 `src/` 全部废弃重建,仅保留 `data/dataset/*.json`。基线 = Slither + 裸 GPT-4 zero-shot。Ablation arms: full / no-static / no-rag / no-verify-loop。

---

## 2. RALPLAN-DR Summary

### Principles(7 条)

1. **P1a — Dataset partition is immutable before implementation** — dev/test 切分在 Phase 1 结束前固化;之后代码/prompt 改动只在 dev 上评估;test 在 Phase 5 只运行一次。
2. **P1b — Ground truth is compute-matched** — 每个方法(含 baseline)的 `tokens` 与 `llm_calls` 与 `wall_clock_seconds` 入 artifact;`summary.md` 必须含这些列。
3. **P2 — Greenfield clean room** — 新 `src/` 不 import 旧代码;旧代码放 `src_legacy/`,不进 runtime path。
4. **P3 — Ablation isolates the thing it names** — `no_verify_loop` 完全绕过 Node 3;4 个 arm 各自是独立 compile 的 StateGraph。
5. **P4 — State schema frozen at Node-contract boundary** — `AuditCore` 10 字段不可变,对齐 framework.md §4.1;实现级字段走 `AuditAnnotations` 旁路。
6. **P5 — Determinism is best-effort, fingerprint-tracked** — `system_fingerprint` / `seed` / `temperature` / `model_snapshot` / 工具版本入每个 artifact。
7. **P6 — Foundry at the edge** — forge PASS/FAIL 是 verifier 唯一真值源;verdict 分类器(`pass` / `fail_revert_ac` / `fail_error`)test-first,先 golden-set 单测通过再上线。

### Decision Drivers(top 3)

1. **Thesis-publishability**:P / R / F1 ≥ 0.60 on **test split**,Function-Recall ≥ 0.35,vs-Slither ΔRecall ≥ +8 pts。
2. **Research-prototype time budget**:一个人 ~3 周工程强度。
3. **Reproducibility**:Windows + Linux 都能跑;`scripts/run_eval.py` 一键产出论文可贴表格。

### Viable Options

#### Option A(选定)— Strict LangGraph + Split State + Compile-time Graph Arms
三节点/状态/条件边对齐 framework.md §4;`AuditCore`(frozen 10 字段)+ `AuditAnnotations`(旁路 dict/TypedDict);4 个 arm 各自独立 compile 的 StateGraph,通过共享 sub-constructor(`_add_verifier_loop` / `_add_report_terminal`)消除复制粘贴。

**Pros**
- 状态机结构 = 架构图 = 文档第 4 章,答辩可直接展示文档 figure
- conditional edge 原生支持 arm 独立 compile(P3)
- split state 吸收 schema churn,不 cascade

**Cons**
- LangGraph 依赖 + TypedDict 模板代码
- split state 略微偏离文档"所有状态写同一 Schema"字面描述(但语义一致)

#### Option B — Monolithic Orchestrator with DI
纯 Python class,顺序调 Node 函数,依赖注入 adapter。

**Pros**
- 无 LangGraph 学习曲线;debug 时 stack trace 直白
- 实现 LoC 更少

**Cons(技术理由)**
- 重试 / 条件路由要手写状态机,约 150-200 LoC 复现 LangGraph 的 conditional edge + checkpointer
- 4 种 ablation 只能通过 config 开关 + if/else 实现,**违反 P3**(不是"编译期独立 graph")
- 框架文档 §1 结论表明确选定 LangGraph → 答辩无法解释偏离

#### Option C — LangGraph Core + Pydantic Frozen State + Annotation Sidecar
Architect 提出的三选路径,已并入 A(frozen `AuditCore` + mutable sidecar)。

**→ Option B 失效理由:** 违反 P3 + 文档 §1 选型结论。Option C 已合并进 A。

---

## 3. 交付物

### 3.1 Plan 文档(本文件)

架构决策 + 实施阶段 + acceptance criteria + ADR + changelog。

### 3.2 Task 文档(`.omc/plans/consensus-tasks-150bad.md`)

**Schema(每一行任务必填):**

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `task_id` | string | `P1.2-build-safe-cases` | 格式 `P{phase}.{seq}-{slug}`,全局唯一 |
| `phase` | int | `1` | 对应 §5 的 Phase 编号(0-6) |
| `title` | string | "构造 50 条 safe case,混源" | 单行祈使句 |
| `depends_on` | list[task_id] | `["P1.1-merge-bad-cases"]` | 有向无环 |
| `files_touched` | list[path] | `["scripts/build_eval_set.py", "data/dataset/safe_cases.json"]` | 全 repo 统一使用相对路径(从 repo root 起) |
| `exit_test` | string | `python scripts/build_eval_set.py --validate && [ $(jq '.cases\|map(select(.ground_truth_label=="safe"))\|length' data/dataset/eval_set.json) -ge 50 ]` | **必须是可执行 shell/pytest**,无主观判断 |
| `estimate_h` | number | `4` | 人-小时估计 |
| `owner_hint` | string | `executor\|data-engineer\|test-engineer` | 团队角色 |
| `status` | enum | `todo\|in_progress\|blocked\|done` | 初始全 `todo` |
| `notes` | string(可选) | `"优先用 OZ contracts 作为独立 safe"` | 自由补充 |

**Dep-graph 表示:** 每个 phase 段首一张 mermaid DAG,渲染 `depends_on`。
**Sync 规则:** plan phase 调整时,task 文档 `phase` 字段必须跟改。

Task 文档起点规模:~45 atomic tasks(Phase 0: 3 / P1: 10 / P2: 15 / P3: 5 / P4: 7 / P5: 4 / P6: 3 — 见 companion 文档)。

---

## 4. 目标目录结构(新 src/)

```text
agent/
├── src/                                    # 全部重建
│   ├── agent/
│   │   ├── state.py                        # AuditCore(frozen 10 fields) + AuditAnnotations
│   │   ├── graph.py                        # 4 compile-time graphs + shared sub-constructors
│   │   └── config.py                       # env / model / version pinning
│   ├── nodes/
│   │   ├── analyst.py
│   │   ├── builder.py
│   │   └── verifier.py
│   ├── adapters/
│   │   ├── llm.py                          # snapshot pinned, system_fingerprint logged
│   │   ├── static_analyzer.py              # Slither + regex fallback, in-memory source
│   │   ├── rag.py                          # Chroma, dev-only corpus, LOO within dev
│   │   ├── foundry.py                      # verdict classifier driven by revert_keywords.yaml
│   │   └── revert_keywords.yaml            # versioned keyword list(post-test 受写锁保护)
│   ├── data/
│   │   ├── loader.py
│   │   └── schema.py
│   ├── eval/
│   │   ├── metrics.py                      # P/R/F1 + bootstrap CI + function recall
│   │   ├── runner.py                       # --split dev|test + hash-lock guard
│   │   └── report.py                       # summary table with tokens/llm_calls columns
│   └── baselines/
│       ├── slither_baseline.py
│       └── gpt4_zeroshot.py
│
├── scripts/
│   ├── build_eval_set.py
│   ├── split_eval_set.py                   # stratified 75/25 split, writes split_seed.txt
│   ├── load_rag.py                         # 只加载 dev.json 里的 vulnerable case
│   ├── run_eval.py                         # 主入口;hash-lock 自检
│   ├── verify_split_stratification.py
│   ├── verify_ablation_effect.py
│   └── smoke_test.py
│
├── tests/
│   ├── unit/
│   │   ├── test_state.py
│   │   ├── test_graph.py
│   │   ├── test_nodes_analyst.py
│   │   ├── test_nodes_builder.py
│   │   ├── test_nodes_verifier.py          # Phase 2 先行;读 fixtures/verifier_verdicts/
│   │   ├── test_adapters_static.py
│   │   ├── test_adapters_rag.py
│   │   ├── test_rag_leakage.py             # 枚举 RAG 索引,断言无 self-leak
│   │   └── test_metrics.py
│   └── fixtures/
│       ├── mini_dataset.json
│       ├── verifier_verdicts/
│       │   ├── revert_ac_openzeppelin_v4.txt
│       │   ├── revert_ac_openzeppelin_v5.txt        # custom error
│       │   ├── revert_ac_custom_error.txt
│       │   ├── revert_ac_non_english.txt
│       │   ├── revert_non_ac_oog.txt
│       │   ├── revert_non_ac_assert.txt
│       │   ├── pass_withdraw_full.json
│       │   └── fail_compile_0_8_20.txt
│       └── baseline_sanity/
│           └── five_known_labels.json
│
├── data/
│   ├── dataset/
│   │   ├── vulnerabilities.json                     # 保留(素材)
│   │   ├── vulnerabilities_pre.json                 # 保留(素材)
│   │   ├── bad_cases.json                           # 新,≥150
│   │   ├── safe_cases.json                          # 新,≥50
│   │   ├── eval_set.json                            # 合并
│   │   ├── dev.json                                 # 75 bad + 25 safe
│   │   ├── test.json                                # 75 bad + 25 safe (held out)
│   │   ├── split_seed.txt                           # "42"
│   │   └── .dataset_hashes.lock                     # sha256 of dev/test/seed
│   ├── evaluation/
│   │   ├── full.json / no_static.json / no_rag.json / no_verify_loop.json
│   │   ├── baseline_slither.json / baseline_gpt4_zeroshot.json
│   │   ├── summary_dev.md
│   │   ├── summary_test.md                          # 只写一次
│   │   ├── test_run_history.jsonl                   # append-only audit log
│   │   └── confusion_matrices.md
│   ├── vectorstore/
│   └── foundry_template/
│
└── docs/
    ├── ARCHITECTURE.md
    ├── RUN.md
    ├── DATASET.md
    ├── DEV_ITERATION_LOG.md
    └── graphs/
        ├── full.mmd / no_static.mmd / no_rag.mmd / no_verify_loop.mmd
```

---

## 5. Implementation Phases

### Phase 0 — Repo Reset & Scaffolding(0.5 day)
- `git tag v0.2-before-rewrite`(用户手动)
- `src/` → `src_legacy/`;`.gitignore` 可选忽略 legacy runtime
- 新目录结构所有空文件 + `__init__.py` + 最小 docstring
- `pyproject.toml` package 路径 → 新 `src/agent`
- **Exit:** `python -c "from agent.graph import create_audit_graph"` 不报错;旧代码 0 行被 import;git 有 tag。

### Phase 1 — Dataset Construction & Split Lock(3-5 days)
1. 合并 + 去重 `vulnerabilities.json` + `vulnerabilities_pre.json`
2. 空 `contract_source` case 从 `data/contracts/raw/` 补齐
3. 不足 150 条 → Code4rena / SWC semi-manual 扩充
4. 构造 ≥ 50 safe case:混源 `≤40% fixed_code / ≥40% OZ / ≥20% c4_invalid`;每条 `source_type` 字段
5. Schema 校验:`src/data/schema.py` + `scripts/build_eval_set.py --validate`
   - 必填:`id`, `contract_source`, `contract_name`, `ground_truth_label`, `source`, `source_type`, `buildable`
   - 若 vulnerable:`vulnerable_function`, `vulnerability_type` 必填
6. **切分固化:** `scripts/split_eval_set.py --seed 42 --strategy stratified --keys vulnerability_type,source_type`
   - 75 bad + 25 safe → `dev.json`;剩余 → `test.json`
   - 写 `data/dataset/split_seed.txt`
   - 计算 `sha256(dev.json) + sha256(test.json) + sha256(split_seed.txt)` → 写 `data/dataset/.dataset_hashes.lock`
   - git commit 四个文件作为切分证据

**Exit criteria:**
- `jq '.cases|length' dev.json` ≥ 100,`test.json` ≥ 100
- `python scripts/verify_split_stratification.py` 通过
- 20 条人工 spot-check label 正确率 100%
- 编译率 ≥ 90%(不达则 `buildable=False` case 仅 analyst-only)
- `.dataset_hashes.lock` 与实际文件 sha256 一致

### Phase 2 — Core Agent Implementation(4-5 days)

**Test-first 强制:** `tests/unit/test_nodes_verifier.py` 必须先 red → green,再写 verifier adapter 实现。

1. `src/agent/state.py`:
   - `AuditCore` TypedDict,10 字段对齐 framework.md §4.1(`contract_source`, `contract_abi`, `defined_roles`, `sensitive_functions`, `audit_hypothesis`, `verification_poc`, `execution_trace`, `retry_count`, `finding_confirmed`, `audit_report`)
   - `AuditAnnotations` = `TypedDict` with `total=False`,明确字段:`error_history: list[str]`, `tokens_prompt: int`, `tokens_completion: int`, `llm_calls: int`, `system_fingerprint: str`, `wall_clock_seconds: float`(**非** `Dict[str, Any]`,Architect minor #1)
2. `tests/unit/test_nodes_verifier.py` + `tests/fixtures/verifier_verdicts/`(≥ 8 fixtures):OZ v4 / OZ v5 custom error / 自定义 error / 非英文 revert / OOG / Panic / full pass / compile fail
3. `src/adapters/static_analyzer.py`:Slither + 正则 fallback;内存源码优先(tmpfile 调用)
4. `src/adapters/rag.py`:Chroma 本地;语料 = **dev.json** 的 vulnerable cases;评估 dev case 时对同 `case_id` 做 LOO;test 阶段索引不含 test case,天然隔离
5. `src/adapters/llm.py`:`ChatOpenAI(temperature=0.1, seed=42, model="gpt-4-turbo-2024-04-09")`;每次响应 `system_fingerprint` 写 annotations
6. `src/adapters/foundry.py`:verdict 分类器从 `src/adapters/revert_keywords.yaml` 读关键字;三类输出
7. `src/nodes/analyst.py`:prompt = 系统提示 + few-shot(来自 RAG)+ 静态事实 + 合约源 → JSON `{target_function, hypothesis, confidence, reasoning}`
8. `src/nodes/builder.py`:输入 `target_function + hypothesis + error_history[]`,输出 `.t.sol`
9. `src/agent/graph.py` — **4 compile-time graphs + shared sub-constructors**(Architect minor #2):
   - `_add_verifier_loop(graph)`:复用的 verifier+router+报告/安全终点逻辑
   - `_add_report_terminal(graph)`, `_add_safe_terminal(graph)`
   - `build_graph_full()`:preprocess_static → rag_retrieve → analyst → builder → _add_verifier_loop
   - `build_graph_no_static()`:rag_retrieve → analyst → builder → _add_verifier_loop
   - `build_graph_no_rag()`:preprocess_static → analyst → builder → _add_verifier_loop
   - `build_graph_no_verify_loop()`:preprocess_static → rag_retrieve → analyst → builder → `mark_vulnerable_on_poc_generated` → END(**完全不含 Node 3**)
   - 每个 graph 独立 `graph.get_graph().draw_mermaid()` 导出到 `docs/graphs/`
   - router(full / no_static / no_rag 中存在):
     - `pass` → report → END
     - `fail_revert_ac` → mark_safe → END
     - `fail_error` 且 `retry_count < 5` → builder(携 trace)
     - `fail_error` 且 `retry_count ≥ 5` → mark_safe → END

**Exit criteria:**
- `pytest tests/unit/test_nodes_verifier.py -v` 8 fixtures 全绿
- `python scripts/smoke_test.py --graph full --contract <demo>` 端到端 `pass`,`retry_count ≤ 3`
- 4 个 graph 均能独立 mermaid 导出;`no_verify_loop.mmd` 不含 verifier node(人工 diff 或 `grep verifier docs/graphs/no_verify_loop.mmd` 为空)
- `pytest tests/unit/ -q` 全绿

### Phase 3 — Baselines(1.5 days)
1. `src/baselines/slither_baseline.py`:每个 case 跑 `slither --json`,AC-category detector 任一触发 → `flagged=True`;输出 `{case_id, flagged, flagged_functions, tokens_prompt=0, tokens_completion=0, llm_calls=0, wall_clock_seconds}`
2. `src/baselines/gpt4_zeroshot.py`:单 prompt "Analyze this Solidity contract for access-control vulnerabilities. Return JSON {is_vulnerable, vulnerable_functions}";无静态、无 RAG、无 verify;输出同 schema,含 `tokens_prompt/completion`, `llm_calls=1`

**Exit:** 每个 baseline 在 `tests/fixtures/baseline_sanity/five_known_labels.json`(5 条人工标答)上,`slither` 与 `gpt4_zeroshot` 至少 3 条命中;运行时间 Slither ≤ 30s/case,GPT-4 zero-shot ≤ 10s/case。

### Phase 4 — Eval Runner + Metrics(2 days)
1. `src/eval/metrics.py`:
   - `compute_contract_metrics(predictions, ground_truth) -> {TP, FP, TN, FN, P, R, F1}`(含 95% bootstrap CI)
   - `compute_function_recall(predictions, ground_truth) -> float`(仅 vulnerable case;top-1 命中)
2. `src/eval/runner.py`:
   - 迭代 `eval_set.json` × `arms = [full, no_static, no_rag, no_verify_loop, baseline_slither, baseline_gpt4]`
   - 每 (case, arm) 保存 per-case detail 到 `data/evaluation/{arm}.json`
   - 支持 `--cases N`, `--arms a,b,c`, `--split dev|test`
   - **Hash-lock 自检(Architect minor #3 升级 plan-level):** 启动时读 `data/dataset/.dataset_hashes.lock`,计算 `dev.json/test.json/split_seed.txt` 当前 sha256;不一致则 abort(拒绝评估,避免切分被动过)
   - **Test-set 物理防沉迷:** `--split test` 必须配 `--i-am-aware-this-opens-the-test-set`;若 `summary_test.md` 已存在,拒绝运行,除非加 `--overwrite-test-i-accept-contamination`(Critic v2 addendum)
   - Test 运行时 append 一行到 `data/evaluation/test_run_history.jsonl`(timestamp + arms + commit sha + fingerprint)
   - 首次 `--split test` 跑完后,hash-lock 扩展涵盖 `src/adapters/revert_keywords.yaml` + `src/nodes/*.py` 的 prompt 字符串(**Critic v2 addendum;防止 executor "小改一下 prompt 再跑 test"**)
   - 并行度:forge=1(避免竞态),LLM ≥ 4
3. `src/eval/report.py`:
   - 聚合 → `summary_dev.md` / `summary_test.md`
   - 列:`Method | Split | Tokens | LLM Calls | Runtime | TP | FP | TN | FN | P (±CI) | R (±CI) | F1 (±CI) | Func-R (±CI) | Avg Retries`

**Exit:**
- `python scripts/run_eval.py --cases 20 --arms full,baseline_slither --split dev` 完整 artifact + `summary_dev.md`
- `tests/unit/test_metrics.py` 覆盖 all-TP / all-FN / all-safe / empty pred / mixed
- `tests/unit/test_rag_leakage.py` 全绿:评估 dev case `C` 时,`C.id` 不在 RAG 索引
- Hash-lock 自检:手动修改 `dev.json` 中一行 → `run_eval.py` 拒绝启动

### Phase 5 — Full Benchmark on DEV(2 days) + Frozen TEST Run(0.5 day)

**DEV 阶段:**
- 跑 `full` 全 dev → `summary_dev.md` → failure-category 分析
- 允许调:analyst prompt / few-shot 选择策略 / builder prompt / `revert_keywords.yaml`
- **不准**:换模型 / 改 graph 结构 / 改 metrics 定义
- 每次改动 commit + `docs/DEV_ITERATION_LOG.md` 记一行"why"

**TEST 阶段(仅一次):**
- 达到 dev 目标或用完 iteration 预算后,冻结 prompt/config
- `python scripts/run_eval.py --arms full,no_static,no_rag,no_verify_loop,baseline_slither,baseline_gpt4 --split test --i-am-aware-this-opens-the-test-set`
- 首次跑完后 hash-lock 扩展到 `revert_keywords.yaml` + prompt 文件
- `summary_test.md` → 论文主表

**Exit criteria(硬性):**
- `summary_dev.md` 的 `Ours(full)` dev 上:P ≥ 0.60,R ≥ 0.60,F1 ≥ 0.60,Func-R ≥ 0.35
- `summary_test.md` 存在且 `git log --all -- data/evaluation/summary_test.md` 只一次 commit(或 `test_run_history.jsonl` 单行)
- test 上 `Ours(full)` 主指标允许比 dev 下降 ≤ 0.05;P/R/F1 任一 < 0.55 视为 Phase 5 未通过
- test 上 `Ours(full)` Recall ≥ `Slither(test)` Recall + 8 pts
- **指定** `no_verify_loop` 在 test 上 Recall 比 full 下降 ≥ 5 pts(防 cherry-pick)
- 每 row `Tokens` 与 `LLM Calls` 列非空(P1b 合规)

### Phase 6 — Docs & Reproducibility(1 day)
- `docs/ARCHITECTURE.md`:mermaid 架构图(4 graph)+ state schema 字段表 + 节点契约
- `docs/RUN.md`:Windows + Linux 安装步骤 + `scripts/run_eval.py` 用法 + "best-effort reproducibility modulo OpenAI `system_fingerprint` drift"
- `docs/DATASET.md`:150 bad + 50 safe 每条来源 + `split_seed=42` + stratification 证据
- `README.md` 顶部加"论文主结果表"锚点,引用 `summary_test.md`

**Exit:** 干净 WSL Ubuntu 22.04 + 干净 Windows 11 各执行一次 `docs/RUN.md`,能走到 `summary_test.md`。

---

## 6. Risks & Mitigations

| # | 风险 | 可能性 | 影响 | 缓解 |
|---|------|--------|------|------|
| R1 | Code4rena 合约编译失败率高(solc 跨版本)→ Phase 1 卡死 | 高 | 高 | `solc-select` 按 pragma 自动选版本;失败 case 降级只 analyst-only 评估;Phase 1 budget 3-5 天 |
| R2 | Safe case 构造不纯 → FP 假低估 | 中 | 中 | 混源比例 `≤40% fixed / ≥40% OZ / ≥20% c4_invalid`;summary 加 `FP_by_source_type` 分层 |
| R3 | Function-Recall < 0.35 | 中 | 高 | 只允许 dev 上调 prompt + 静态证据强化;dev 达标 test 未达 → 报告原因,不伪造数字,改论文叙事(不加自降级 escape) |
| R4 | 废弃 src/ 后发现可救模块 | 中 | 低 | `src_legacy/` 保留;`grep legacy` 是任何相似实现的 pre-task |
| R5 | LangGraph 升级 breaking | 低 | 高 | `pyproject.toml` pin;CI 校验 |
| R6 | Foundry 并发竞态 flaky | 中 | 中 | `run_eval.py` 强制 forge 并行度=1;每 case 独立 tmpdir |
| R7 | OpenAI API 额度/限流 | 中 | 中 | 每 case artifact 独立保存,断点续跑;可切 azure-openai |
| R8 | 老师口径变动 | 中 | 低 | baseline 接口 `evaluate_baseline(case) -> PredictionRecord` stable;加 baseline = 新 file + registry 一行 |
| R9 | RAG 语料泄题 | 高 | 高 | RAG = `dev.json` only;同 id LOO;test 阶段索引天然隔离;`test_rag_leakage.py` 枚举检测 |
| R10 | Verifier 关键字 miss(OZ v5 custom error / 非英文 revert) | 高 | 高 | `tests/fixtures/verifier_verdicts/` golden-set;Phase 2 test-first;`revert_keywords.yaml` 版本化 + post-test 写锁 |
| R11 | 150-case harvesting > 预算 | 高 | 中 | Phase 1 budget 3-5 天;若 > 7 天,规模降到 120 bad + 40 safe(80/20 dev + 40/20 test),切分 seed 仍固定 |
| R12 | LLM `seed` 非真 deterministic | 中 | 中 | `system_fingerprint` 入 artifact;docs/RUN.md 诚实声明 "best-effort, fingerprint-tracked";论文表加脚注 |
| R13 | Dev/test 项目级重叠(同协议 fork 分到两侧)→ 隐性泄题 | 中 | 低 | 切分时 `source` 元字段附带 `project_name`,`verify_split_stratification.py` 检测同 `project_name` 不跨侧(task 级 note;非阻塞) |

---

## 7. Verification Steps

1. **Phase 2 pre-verifier test-first**:`pytest tests/unit/test_nodes_verifier.py -v` 在 adapter 实现 commit 前先 red → green
2. **Phase 2 ablation-isolates verification**:4 个 graph 独立 mermaid 导出后人工 diff;`grep -c verifier docs/graphs/no_verify_loop.mmd` 返回 0
3. **Phase 2 end-to-end smoke(happy + unhappy)**:
   - Happy:`smoke_test --graph full --contract <demo-vuln>` → `pass`
   - fail_revert_ac:`smoke_test --contract <demo-safe>` → `mark_safe`
   - fail_error + retry:`smoke_test --contract <demo-bad-signature>` 观察 `retry_count > 0`
4. **Phase 3 baseline sanity**:`tests/fixtures/baseline_sanity/five_known_labels.json` 下两 baseline 各命中 ≥ 3 条
5. **Phase 4 metrics correctness**:`pytest tests/unit/test_metrics.py` 5 种边界 + 合成 toy 手算对齐
6. **Phase 4 RAG leakage check**:`pytest tests/unit/test_rag_leakage.py`;评估 dev case `C` 时 `C.id` ∉ RAG 索引
7. **Phase 5 one-shot test integrity**:`git log --all -- data/evaluation/summary_test.md` 恰好一次;`data/evaluation/test_run_history.jsonl` 单行
8. **Phase 5 ablation specificity**:`scripts/verify_ablation_effect.py --arm no_verify_loop --min-drop 5` 检查 Recall 下降 ≥ 5
9. **Phase 6 reproducibility**:干净 WSL Ubuntu 22.04 + 干净 Windows 11 各执行 `docs/RUN.md`,到 `summary_test.md`
10. **Across phases hash-lock(Architect minor #3 升级 plan-level):**
    - `scripts/run_eval.py` 启动读 `data/dataset/.dataset_hashes.lock` 自检
    - 首次 `--split test` 跑完后,hash-lock 自动扩展覆盖 `src/adapters/revert_keywords.yaml` + `src/nodes/*_prompt.*`
    - 不再依赖外部 CI / pre-commit 的存在

---

## 8. Timeline Estimate

| Phase | 时间 | 累计 |
|-------|------|------|
| 0 | 0.5 天 | 0.5 天 |
| 1 | 3-5 天 | 3.5-5.5 天 |
| 2 | 4-5 天 | 7.5-10.5 天 |
| 3 | 1.5 天 | 9-12 天 |
| 4 | 2 天 | 11-14 天 |
| 5 | 2.5 天 | 13.5-16.5 天 |
| 6 | 1 天 | 14.5-17.5 天 |
| **合计** | **≈ 3 周**(单人全职) | |

Phase 1 + Phase 2 可部分并行(若 dev/test split 已完成,Phase 2 用最初 40 条跑端到端)。

---

## 9. Open Questions

1. **`baseline_gpt4_zeroshot` 是否加 CoT?** 默认不加,保持最朴素对照;若 dev 上 Ours 相对提升 < 3 pts,加 CoT 版作补充 baseline(避免 apples-to-oranges)— 这是**dev 驱动的 gated branch**,task 文档 P5 阶段明确标注分支。
2. **Function-Recall 是否提供 top-k 兜底?** 默认 top-1 严格;top-k 可作 stretch 放到 `summary_test_topk.md`。

---

## 10. ADR — Architecture Decision Record

### Decision
采用 **Option A: Strict LangGraph + Split State + 4 Compile-time Graph Arms** 作为 150-bad-case 访问控制漏洞检测框架的基础架构。

### Drivers
- **Thesis-publishability** — 需要在论文/答辩里直接引用架构图与 framework.md §4 的节点/状态/边对齐;LangGraph + split state 让这一引用是字面一致而非近似。
- **Ablation-isolates(P3)** — 4 个独立 compile 的 StateGraph 使每个 ablation arm 是结构性独立的对象,可通过 mermaid diff 人工确认,不依赖 config 开关的"隐性模糊"。
- **Research-prototype time budget** — 单人 ~3 周;任何"自建 LangGraph 子集"的做法都会被 retry/checkpoint/conditional edge 的自实现吞掉 1-2 周。

### Alternatives considered

- **Option B — Monolithic Orchestrator with DI**:纯 Python class + DI。优点简单;失效于 P3(ablation 变成 if/else 开关,结构上不隔离)+ 复现 LangGraph 状态机需要 150-200 LoC + 违反 framework.md §1 选型结论。
- **Option C — LangGraph + Pydantic Frozen State + Annotation Sidecar**:Architect 在 v1 review 提出,已在 v2 合并进 A(`AuditCore` frozen + `AuditAnnotations` sidecar);不再作为独立 option。

### Why chosen
A 是唯一同时满足 P3(ablation structurally isolated)+ P4(frozen core schema)+ framework.md §1 选型的方案;在三条 decision driver 上无短板。合并 Architect synthesis 后,A 兼具 Option B 的"状态 schema 不 cascade"优点。

### Consequences

**Positive**
- 架构 = 文档 figure,答辩可直接引用
- 4 个 arm 的 ablation 表可信度高(结构性隔离,不是 flag toggle)
- `AuditCore` 冻结 → 新字段加到 `AuditAnnotations`,零 cascade
- Verifier 三元分类器 test-first + 版本化关键字 yaml → 关键 heuristic 不再是"prod 上才发现"
- 评估器 hash-lock 自检 → 切分 / prompt / keyword 冻结后动一下立刻 abort,防止无意间的 test-set 污染

**Negative**
- LangGraph 依赖 + TypedDict 模板代码
- 4 个 graph 需共享 sub-constructor(`_add_verifier_loop` / `_add_report_terminal`)防止复制漂移(Architect minor #2)
- `AuditAnnotations` 若未严格用 `total=False` TypedDict 则会退化为 `Dict[str, Any]`(Architect minor #1,已在 Phase 2 §1 明确字段清单)
- 三周 timeline 里 0.5 天用于 repo reset / legacy 迁移,不直接产出指标

**Net:** 可接受,且均有具体 mitigation。

### Follow-ups

- Phase 1 完成后用 `verify_split_stratification.py` 额外检测 `project_name` 不跨 dev/test(R13 mitigation)
- Phase 2 的 `AuditAnnotations` 按明确字段清单实现,**不**用 bare `Dict[str, Any]`
- Phase 2 的 graph 共享 sub-constructor 在 task 文档 P2.15 专门列出
- 若 Phase 5 dev 冲不到目标,contingency = Phase 1 R11(降级到 120 bad + 40 safe)或论文叙事调整(R3)
- 论文脚注必须引用 `system_fingerprint` 与 `model_snapshot` 具体值(Phase 6 交付)

---

## Changelog

**v1 → v2:** Absorbed 7 Architect findings + 10 Critic fixes. Principles expanded 5 → 7 (new P1a/P1b/P4). Options rewritten with technical dismissal of B + Option C folded. Phase 1 added split lock. Phase 2 changed to 4 compile-time graphs + test-first verifier. Phase 5 split dev/test with physical guards. Risks R9–R12 added. Verification §7 expanded 5 → 10 items.

**v2 → Final:** Folded Critic v2 addendum — §7 item 10 upgraded from "CI or pre-commit" to plan-level "hash-lock inside `run_eval.py`"; Phase 5/R10 extended write-lock to `revert_keywords.yaml` + prompt files post-test; `--overwrite-test-i-accept-contamination` guard added. ADR section added. R13 added (project-level dev/test overlap).

**Review trail:**
- Planner v1 draft → `.omc/drafts/plan-150bad-v1.md`
- Architect v1 CONCERNS (7 findings: RAG leakage, no_verify_loop semantics, verdict classifier, state-schema cascade, baseline fairness, Phase 5 contamination, determinism aspiration)
- Critic v1 ITERATE (10 fixes)
- Planner v2 draft → `.omc/drafts/plan-150bad-v2.md`
- Architect v2 SOUND (4 minor: AuditAnnotations typing, graph duplication, CI/pre-commit ambiguity, CoT gated branch)
- Critic v2 APPROVE (2-line addendum: hash-lock mechanism, prompt/keywords post-test write-lock)
- Final plan = v2 + addendum + ADR
