# 下一步代码调整计划

## 目标

构建一条完整的漏洞发现流程，包含以下阶段：

1. 先运行静态分析工具，提取依赖关系和结构化信息。
2. 将合约源码、静态分析结果和 RAG 检索结果一起输入给 AI 分析节点。
3. 生成候选攻击 PoC 或验证 PoC。
4. 使用 simulation 工具验证攻击是否真的能够成功。
5. 通过消融实验评估各模块的贡献。
6. 在数据集上与至少一个基线工具做对比，证明整套系统有效。

这份文档是当前代码仓库接下来的实现方向。

## 目标端到端流程

### 完整流程

`合约 -> 静态分析 -> RAG 检索 -> AI 分析 -> PoC 生成 -> 仿真/验证 -> 报告输出`

### 各阶段的含义

- 静态分析：
  提取调用图、函数修饰符、状态变量写入关系、继承关系、权限检查、外部调用关系，以及潜在敏感函数候选。
- RAG：
  检索历史相似漏洞案例，作为 few-shot 上下文增强 AI 分析。
- AI 分析：
  使用合约源码、结构化静态分析事实和 RAG 检索结果来判断潜在漏洞。
- 仿真验证：
  使用 Foundry 或其他等价执行后端验证漏洞是否真实可利用。
- 报告输出：
  输出已确认漏洞、未确认怀疑点、失败原因和关键中间证据。

## 当前现状与目标的差距

### 已经具备的能力

- 有 `analyst -> builder -> verifier` 的 LangGraph 工作流
- 已有 RAG 数据加载与检索
- 已有基于 Foundry 的 verifier
- 已有数据集和评估脚本
- `src/tools/` 下已有工具封装

### 目前还缺少或比较薄弱的部分

- 静态分析结果还不是 agent state 的一等输入
- 在 analyst 之前还没有统一的预处理阶段
- 没有清晰区分以下几类结果：
  - 疑似漏洞
  - 经 simulation 确认的漏洞
  - 分析失败 / 工具失败
- 没有正式的消融实验运行器，用于比较：
  - 完整系统
  - 去掉静态分析
  - 去掉 RAG
  - 去掉静态分析和 RAG
- 没有基于同一数据集的基线工具对比流程

## 推荐的代码调整方向

## 1. 增加专门的静态分析预处理阶段

### 目的

在 AI analyst 运行前，先通过静态分析工具生成结构化事实，并写入 graph state。

### 建议新增节点

- `preprocess_static_analysis`

### 预期输入

- `contract_source`
- `contract_name`
- 可选的合约文件路径

### 预期输出

- 函数列表
- 调用图
- 继承图
- 每个函数使用了哪些 modifier
- 每个函数写入了哪些状态变量
- external/public 的敏感函数候选
- 权限检查相关信息
- 静态分析工具产生的 warning / finding

### 建议新增的 state 字段

- `static_analysis_summary`
- `function_summaries`
- `call_graph`
- `storage_write_map`
- `modifier_map`
- `role_check_map`
- `sensitive_candidates`
- `static_tool_findings`

### 代码调整方向

- 在 `src/tools/` 下增加或扩展统一的 adapter 层
- 统一 `slither.py` 的输出格式，必要时兼容 `aderyn.py`
- 将原始工具输出整理成紧凑的 JSON 风格结构，供 analyst 直接使用

## 2. 让静态分析成为 analyst 的核心输入之一

### 目的

LLM 不应该只基于原始 Solidity 代码做推理，而应该同时基于：

- 源码
- 静态分析事实
- RAG 检索案例

### 需要改动的内容

- 更新 analyst prompt 和 analyst 节点逻辑
- 将静态分析事实以结构化上下文传入，而不是只拼成一段自由文本
- 要求 analyst 明确给出：
  - 目标函数
  - 缺失的权限检查
  - 受影响的关键状态
  - 攻击路径
  - 置信度

### 建议的 prompt 输出结构

- `is_vulnerable`
- `vulnerability_type`
- `target_function`
- `missing_access_control`
- `critical_state_affected`
- `reasoning_summary`
- `attack_preconditions`
- `confidence`

### 预期收益

- 减少目标函数定位错误或幻觉
- 提高漏洞函数定位能力
- 给 builder 提供更高质量的输入

## 3. 升级 builder，使其消费更丰富的证据

### 目的

Builder 应该基于结构化攻击假设生成 PoC，而不是只根据模糊自然语言怀疑点生成测试。

### 需要改动的内容

- Builder 输入应包含：
  - 目标函数
  - 对应函数签名
  - 预期攻击者动作
  - 预期攻击后状态
  - 合约初始化 / 构造相关假设
  - 静态分析证据
- Builder 应能区分不同攻击类型：
  - 直接未授权调用
  - 权限升级
  - 多步攻击

### 输出改进建议

- 不仅保存生成的 PoC 代码
- 还应保存：
  - 假设的攻击步骤
  - 预期成功条件
  - 预期 revert 条件

## 4. 将 simulation backend 与 verifier 策略解耦

### 目的

当前验证逻辑和执行后端耦合较紧，不利于后续实验扩展和替换。

### 建议的结构

- `simulation backend`
  - Foundry 执行
  - 未来如果需要，也可以接其他 backend
- `verification policy`
  - 解释执行结果
  - 映射为 `pass`、`fail_revert`、`fail_error`

### 代码调整方向

- 将原始执行逻辑移动到专门模块，例如：
  - `src/tools/foundry.py`
  - 或 `src/simulation/foundry_backend.py`
- `src/nodes/verifier.py` 主要保留节点级策略逻辑

### 额外建议

在 state 中保存更丰富的执行信息：

- `simulation_trace`
- `simulation_stdout`
- `simulation_stderr`
- `simulation_status`

这有助于后续失败分析和论文中的结果展示。

## 5. 在 graph 中加入明确的实验模式开关

### 目的

为了做消融实验，graph 必须支持组件级开关。

### 需要的实验开关

- `use_static_analysis`
- `use_rag`
- `use_simulation`

### 需要支持的实验模式

- Full：静态分析 + RAG + simulation
- No static analysis：RAG + simulation
- No RAG：静态分析 + simulation
- No static analysis and no RAG：仅 AI + simulation

### 代码调整方向

- 将这些开关加入配置和 graph 编译逻辑
- 让各节点按配置条件执行
- 确保评估输出里记录当前结果是由哪种模式产生的

## 6. 构建正式的消融实验运行器

### 目的

当前评估脚本需要从“单次执行”升级为“实验运行器”。

### 建议输出指标

- 找到的漏洞总数
- 被 simulation 确认的漏洞数
- analyst 检测率
- builder 成功率
- simulation 成功率
- precision
- recall
- 各漏洞类型的 recall
- 平均重试次数
- 每个 case 的平均运行时间

### 建议输出文件

- `data/evaluation/full.json`
- `data/evaluation/no_static.json`
- `data/evaluation/no_rag.json`
- `data/evaluation/no_static_no_rag.json`
- 聚合后的 Markdown 或 CSV 对比表

### 关键要求

实验运行器必须能区分：

- AI 没识别出目标漏洞
- AI 识别出了目标，但 builder 失败
- PoC 生成了，但 simulation 因语法 / 运行时 / 工具问题失败
- simulation 成功并最终确认漏洞

## 7. 增加基线工具对比

### 目的

你们不只是要证明内部模块有贡献，还要证明整套系统整体有效。

### 推荐的首个基线工具

优先使用 `Slither`

### 为什么优先选 Slither

- 是比较常见、容易解释的静态分析基线
- 与智能合约漏洞分析任务高度相关
- 你们仓库里已经有 `src/tools/slither.py`
- 便于在论文和答辩中说明

### 可选的第二个基线

- `Aderyn`

### 对比原则

在同一批合约上运行基线工具和你们自己的系统，对比：

- 找到的漏洞数量
- true positives
- false positives（如果标签允许统计）
- 覆盖的漏洞类型
- 是否具备“可利用性确认”能力

### 需要明确说明的一点

基线工具通常输出 warning，而你们的系统输出的是“漏洞是否可利用”的确认结果。因此在表述上要明确区分：

- warning-level detection
- exploit-confirmed detection

## 8. 升级数据集格式以支持实验

### 目的

当前数据集需要同时支持：

- 漏洞检测实验
- 漏洞可利用性验证实验

### 建议新增或标准化的字段

- `ground_truth_vulnerability_type`
- `ground_truth_functions`
- `attack_precondition`
- `expected_exploitability`
- `has_working_poc`
- `baseline_labels`
- `static_analysis_reference`

### 为什么重要

如果标签不统一，后续做消融实验和基线对比时会很难站得住脚。

## 9. 统一报告输出格式，服务于论文和 demo

### 每个 case 的结果建议包含

- contract id
- mode
- 是否使用静态分析摘要
- 是否使用 RAG
- AI hypothesis
- target function
- generated PoC
- simulation result
- 最终是否确认漏洞
- failure category
- runtime

### 为什么重要

这样可以支持：

- 干净地统计指标
- 生成用于展示或论文的对比表
- 快速定位系统中最弱的环节

## 建议的实施顺序

### 第一阶段：先把完整框架搭起来

1. 增加静态分析预处理节点。
2. 在 graph state 中加入静态分析相关字段。
3. 更新 analyst prompt，让其同时消费静态分析结果和 RAG。
4. 重构 verifier，拆分执行后端和结果解释逻辑。
5. 将实验模式开关配置化。

### 第二阶段：让实验可重复

1. 把评估脚本升级成消融实验运行器。
2. 保存每种实验模式的输出结果。
3. 引入失败分类。
4. 生成聚合比较表。

### 第三阶段：加入基线比较

1. 统一 Slither 输出提取逻辑。
2. 将基线输出映射到数据集标签。
3. 对比基线与完整系统。
4. 统计 bug 数量、recall 等关键指标。

## 具体到文件层面的调整建议

### 大概率需要修改的文件

- `src/core/state.py`
  - 增加静态分析字段和实验模式字段
- `src/core/graph.py`
  - 插入预处理节点和条件分支
- `src/nodes/analyst.py`
  - 联合消费静态分析摘要和 RAG 上下文
- `src/nodes/builder.py`
  - 基于结构化攻击假设生成 PoC
- `src/nodes/verifier.py`
  - 只保留策略逻辑，降低与执行后端的耦合
- `src/evaluation/evaluator.py`
  - 增加实验模式评估逻辑
- `scripts/evaluate.py`
  - 增加多模式实验运行能力

### 大概率需要新增的文件

- `src/nodes/preprocess_static.py`
- `src/tools/static_adapter.py`
- `src/simulation/foundry_backend.py` 或等价模块
- `scripts/run_ablation.py`
- `scripts/run_baseline_compare.py`
- `data/evaluation/README.md`

## 当前最小可行下一步

如果当前目标是尽快推进，最合适的实现顺序是：

1. 先只接一个静态分析预处理节点，优先接 Slither。
2. 将规范化后的静态分析结果传给 analyst。
3. 保留现有 RAG 和 Foundry 流程。
4. 增加实验开关，至少支持：
   - full
   - no static
   - no rag
5. 在现有数据集上先把完整流程跑通。
6. 然后再加入 Slither 基线对比。

这是最快形成可展示、可答辩原型的路径。

## 预期研究价值

如果实现得当，最终可以支撑这样一组结论：

- 静态分析可以提升漏洞定位和结构化推理能力。
- RAG 可以提升漏洞模式识别能力和 hypothesis 质量。
- Simulation 可以通过“攻击是否成功”减少误报。
- 完整系统在数据集上的表现优于去掉部分模块的版本，也优于单独的基线工具。

## 当前的直接行动项

- 先定义统一的静态分析输出 schema。
- 将静态分析预处理节点插入 LangGraph 流程。
- 围绕结构化证据重写 analyst prompt。
- 增加实验模式开关和消融实验输出文件。
- 先选 `Slither` 作为首个基线，实现其数据集级运行器。
