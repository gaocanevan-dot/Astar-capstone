# 框架演进路线图:Harness 改造 + DPO 后训练

## 背景与决策

当前 pipeline 的两个核心问题:

1. **RAG 价值存疑**:目前 RAG 只做"相似案例 few-shot"——从 48 条数据里检索 3 条塞进 analyst prompt。GPT-4-turbo 对 access control 模式的先验已经很强,48 条样本提供的增量信号很稀。
2. **PoC 生成基本靠碰运气**:单次 prompt → 生成 Foundry test → forge 跑一次,失败就结束。权限升级 PoC 需要正确推断调用路径、前置状态、attacker 入口,一次 shot 的成功率必然很低。

### 选定方向:A + B 组合

| 方向 | 内容 | 收益 | 成本 | 论文价值 |
|---|---|---|---|---|
| **A. Harness 改造** | Agentic PoC loop + 静态结构化预处理 | 高 | 低(1–2 周) | 中 |
| **B. DPO 后训练** | 用 `forge test pass` 作为 reward 做偏好学习 | 高 | 中(需 GPU、7B 模型) | **高** — reward 信号天然干净 |

Pre-training 方向(继续在 Solidity 语料上预训练)对毕设体量性价比太低,不采纳。

---

## Phase A:Harness 改造(~1–2 周)

### A1 — 静态结构化预处理(2–3 天)

**动机**:让 analyst 看到结构化的权限边界信息,而不是让 LLM 从原始代码里"猜"。

**具体步骤**:

- 安装依赖:`pip install slither-analyzer`(需先安装 `solc-select` 并选择合约编译版本)
- 新文件:`src/static/structural_analyzer.py`,提取:
  - 所有 external / public 函数 + 其 modifier
  - state 变量的写入权限表(谁能写)
  - 继承链
  - owner / role 变量及其读写位置
- 修改 `src/core/graph_light.py` 的 `preprocess_static` 节点调用新模块,输出结构化 JSON 注入 state
- Analyst prompt 新增 "Contract Structure" 段,用表格替代原始代码片段

**交付物**:analyst 接收到的 context 包含结构化权限摘要,不再让 LLM 从原始源码中推断权限边界。

---

### A2 — Agentic PoC loop(3–5 天,**最高性价比**)

**动机**:PoC 失败时让 LLM 看到 forge 错误并迭代修正,通过率预期从 <20% → >50%。

**具体步骤**:

- State schema 扩展(`src/core/state_schema.py`):
  - `poc_attempts: int = 0`
  - `error_history: list[str] = []`
  - `max_attempts: int = 5`
- 修改 `src/core/graph_light.py`:
  - 新增条件边:`verifier → builder`(失败且 `poc_attempts < max_attempts` 时)
  - 成功或达到上限时 → `report`
- 修改 `src/nodes/builder.py`:
  - prompt 接收 `error_history`
  - 当 `error_history` 非空时,system message 前置:
    ```
    Previous attempts failed with these errors:
    {error_history}
    Analyze the errors and fix the issues in the new PoC.
    ```

**交付物**:PoC loop 能迭代 up to 5 次,每次把 forge 错误信息反馈给 builder。

---

### A3 — 扩展 ablation + 跑 baseline(1 天)

**动机**:先拿到当前 pipeline 的基线数字,后面每一步改动都有对照。

**具体步骤**:

- 扩展 `scripts/run_ablation.py` 模式:
  - 保留:`full`、`no-rag`、`no-static`
  - 新增:`no-loop`(max_attempts=1)、`static-enhanced`(A1 启用)
- 新增指标:
  - 检测准确率(vulnerabilities_found / no_vulnerabilities_found)
  - **PoC pass rate**(forge test 通过且触发目标漏洞的比例)
  - 平均迭代次数
  - 单合约平均耗时
- 在全部 48 条数据集上跑每种模式

**交付物**:CSV 结果 + 柱状图(可用 matplotlib)。

---

## Phase B:DPO 后训练(~3–4 周)

### B1 — 数据构造(5–7 天,**最耗时**)

**动机**:当前 48 条数据不足以做 DPO,需扩到 ~200。

**具体步骤**:

- 扩充数据集到 ~200:
  - Code4rena access-control issues(按 tag 过滤)
  - SWC Registry 相关条目
  - 可选:人工构造的合成变体(函数重命名、结构扰动)
- 数据生成流程:
  - 对每个 (contract, vuln_func),用 Phase A pipeline 以 temperature=0.7 采样 K=8 次
  - 分类:
    - `chosen` = forge 通过 **且** 触发目标漏洞
    - `rejected` = 编译失败 **或** 通过但触发了错误漏洞
  - 过滤掉全部通过或全部失败的样本(无法构成偏好对)
- 输出格式:`data/dpo_pairs.jsonl`,每行:
  ```json
  {"prompt": "...", "chosen": "...", "rejected": "..."}
  ```

**交付物**:~1000–2000 条偏好对。

---

### B2 — 训练(7–10 天)

**具体步骤**:

- **Base model**:`Qwen/Qwen2.5-Coder-7B-Instruct`
  - 理由:Solidity 熟练度够、社区支持好、HF 生态完整
  - 备选:`deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct`
- **框架**:HuggingFace `trl.DPOTrainer` + **QLoRA 4-bit**(单卡 RTX 4090 24GB 可跑)
- **依赖安装**:
  ```bash
  pip install trl transformers peft bitsandbytes accelerate datasets
  ```
- **超参**:
  - `learning_rate=5e-7`(DPO 对 lr 很敏感,不要用 SFT 的 lr)
  - `num_train_epochs=3`
  - `beta=0.1`
  - `per_device_train_batch_size=2` + `gradient_accumulation_steps=8`
  - LoRA rank=16, alpha=32, dropout=0.05
- **开工前先 sanity check**:用 20 条样本裸测 Qwen2.5-Coder 的 Solidity 能力,若太差换 DeepSeek-Coder。

**交付物**:LoRA adapter 保存到 `models/poc_dpo_v1/`。

---

### B3 — 集成 + 最终对比(2–3 天)

**具体步骤**:

- 用 vLLM 起本地推理服务:
  ```bash
  vllm serve Qwen/Qwen2.5-Coder-7B-Instruct --enable-lora --lora-modules poc_dpo=models/poc_dpo_v1/
  ```
- `src/nodes/builder.py` 加 config 开关:
  - PoC builder 可切换到 fine-tuned 模型
  - Analyst 仍用 GPT-4(access control 检测和 PoC 生成是不同任务)
- 重跑 Phase A3 的 ablation,加入 "DPO-model" 这个 arm
- 论文主结果表对比:
  - GPT-4 only(baseline)
  - GPT-4 + agentic loop
  - GPT-4 + static-enhanced
  - GPT-4 + 全套 Harness
  - **GPT-4 analyst + DPO-tuned builder**(最终方案)

**交付物**:最终对比表 + 论文可用图表。

---

## 执行时间线

```
Today   → A3  (先跑 baseline,知道起点)
Week 1  → A2  (agentic loop,收益最大)
Week 2  → A1  (静态预处理)
Week 3-4→ B1  (数据构造,最耗时,可提前启动)
Week 5  → B2  (训练)
Week 6  → B3 + 论文实验
```

> Phase B1 可以在 Phase A 后期并行启动——数据构造不依赖训练本身。

---

## 风险与检查点

| 风险 | 缓解方案 |
|---|---|
| 数据量不足 | B1 先扩到 200 条合约,检查偏好对数量是否 ≥ 1000 |
| Reward 假阳性(PoC 通过但利用了错误漏洞) | 在 B1 加二次验证 filter:比较 PoC 调用的函数是否匹配 `vuln_func` |
| Qwen2.5-Coder 对 Solidity 能力不足 | B2 开工前用 20 条样本裸测,必要时换 DeepSeek-Coder |
| QLoRA 仍然显存不够 | 降到 `per_device_train_batch_size=1` + 增大梯度累积 |
| Foundry 版本 / 合约编译器版本不匹配 | A1 开工时用 `solc-select` 锁定版本 |

---

## 立即下一步

**从 A3 开始**——先扩 `scripts/run_ablation.py` 在当前 48 条上跑一遍拿 baseline,这样后续每个改动都有对照。

具体动作:
1. 检查当前 ablation 脚本现状
2. 新增 `no-loop`、`static-enhanced` 模式(即使功能还没实现,先占位)
3. 新增 PoC pass rate 指标
4. 跑一遍拿 baseline 数据
