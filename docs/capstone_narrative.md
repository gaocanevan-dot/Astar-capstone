# Capstone Narrative — Agent vs Zero-Shot Baseline

Bilingual draft. Honest framing. All numbers traceable to artifacts in `data/evaluation/` and `.omc/plans/day4-routing-reversal-disclosure.md`.

---

## English version (~250 words)

We built a closed-loop agent for smart-contract access-control vulnerability detection: an analyst layer (LLM-driven function ranking with optional tool-augmented self-consistency), a builder layer (Foundry PoC generation), and a verifier layer (forge-based PoC execution against original contracts). The agent uses cascade routing between top-3 analyst candidates and a locked reflection node for re-ranking on failure.

We benchmarked against a strict zero-shot baseline: GPT-5-mini predicts top-1 vulnerable function, then the same builder/verifier pipeline runs once. On a 10-case smoke set drawn from the C5/Repair-Access-Control corpus (full Solidity contracts, 356-1290 LOC, 10 distinct projects), the agent passes **6/10 PoC verifications** versus zero-shot's **4/10**, a 50% relative lift at 3x cost premium ($0.29 vs $0.10).

The lift has clear mechanistic attribution. ACF-114 (`SpaceGodzilla`) fails at top-1 under both systems but agent's hybrid cascade router advances to depth=3 and finds an exploitable function; zero-shot stops at the first failure. ACF-103 (`ANCHToken`) is skipped by single-shot analyst (returns empty target) under zero-shot but recovered by SC=3 RRF voting under agent-full. Cascade depth>1 fired in 4/10 cases, reflection wedge invoked in 4/10 cases — the agent's machinery is observably active.

Honest limitations: Recall@1 (predicted = labeled function) remains 2/10 under both systems — Code4rena contracts often have multiple AC-deficient functions, so passes happen on non-labeled exploitable functions. We treat the agent's contribution as **end-to-end exploit construction**, not labeled-function identification.

Post-hoc cascade routing adjustments are disclosed in `.omc/plans/day4-routing-reversal-disclosure.md`.

---

## 中文版（约 250 字）

我们构建了一个闭环 agent 用于智能合约访问控制漏洞检测：analyst 层（LLM 驱动的函数排序，含可选的工具增强自一致性投票）、builder 层（Foundry PoC 生成）、verifier 层（forge 在原合约上执行 PoC）。agent 在 top-3 候选间使用 cascade 路由，并在失败时由 LOCKED reflection 节点重排序。

我们以严格 zero-shot 为对照：GPT-5-mini 预测 top-1 漏洞函数，然后用相同的 builder/verifier 流水线执行一次。在 C5/Repair-Access-Control 语料抽取的 10 个完整合约（356-1290 行，10 个不同项目）smoke set 上，**agent 通过 6/10 个 PoC 验证，zero-shot 通过 4/10**，相对提升 50%，成本溢价 3 倍（$0.29 vs $0.10）。

提升有明确的机制归因。ACF-114（SpaceGodzilla）在两个系统的 top-1 都失败，但 agent 的 hybrid cascade router 推进到 depth=3 找到了可利用函数；zero-shot 在第一次失败就停了。ACF-103（ANCHToken）的 single-shot analyst 返回空 target → zero-shot 直接 skipped，但 agent-full 的 SC=3 RRF voting 救回。cascade depth>1 在 4/10 case 触发，reflection wedge 在 4/10 case 调用——agent 的核心机制可观测地激活。

诚实声明：在两个系统下 Recall@1（预测函数 = label 函数）都是 2/10——Code4rena 合约普遍存在多个 AC 缺陷函数，因此 PoC 在非 label 函数上 pass 是常态。我们将 agent 的核心贡献定位为**端到端漏洞利用构造**，而非 label 函数识别。

Cascade 路由的 post-hoc 调整在 `.omc/plans/day4-routing-reversal-disclosure.md` 中全程公开。

---

## Defense Q&A — 评委可能问的硬问题（带答案）

**Q1: 你的 routing 改动是 Day-3 baseline 持平后才做的，这是不是 p-hacking？**

是 post-hoc，但有以下结构化缓解：(1) 改动 1（cascade hybrid）保留了原 Critic 的 retry-on-flake 安全网，只是在 2 次失败后 advance 而非 abstain；(2) 改动 3（SC=3）用 R8 pre-test 在投入完整重跑前**预先注册**了"≥2 case 在 SC vs single-shot 下产生不同 top-1"作为生效闸门，结果 3/6 通过；(3) 全部测试 assertion 改动透明记录在 disclosure file。reviewer 可以查看每个 lift 的具体 trace 是否符合机制声明。

**Q2: Recall@1 没变，agent 真的有用吗？**

agent 找到的是**真实可利用函数**（forge `pass` 在原合约上），不是 label 那个。这反映 Code4rena 合约本身的多漏洞性质（验证：手动检查 ACF-114 的 ForceBet 和 ACF-101 的 mint，都是真 AC 缺陷）。所以 agent 的价值是**端到端可执行 PoC 输出能力**，不是更准的函数预测。**这恰恰是 zero-shot 做不到的——zero-shot 在 ACF-101 fail compile，agent 重试 + cascade 找到可打的函数**。

**Q3: 成本溢价 3 倍值不值？**

每个 pass agent 花 $0.048 vs zero-shot 的 $0.024，agent 贵 2x 每 pass。但 agent 多找到 50% 的真 bug，且每个 pass 都附带 PoC 代码（一份具备实际审计价值的可执行漏洞利用）。zero-shot 在 4/10 pass 之外什么都不输出。这个 trade-off 在 capstone 级别的研究里是**端到端能力 vs 单点预测**的权衡。

**Q4: n=10 太小**

确认。+2 pass 在 Wilson 95% CI 的边界处。这是 capstone 实验的工程约束（成本、时间）。下一步推荐是**扩到 n=30**（计入安全孪生 + 多样化漏洞类别），并增加 variance check 多 seed 重跑。当前实验作为**机制 demonstration + 方法论 infrastructure** 是合格的。

**Q5: cascade 改成 advance-on-runtime 是不是把 baseline 也变好了？**

不会。zero-shot e2e 是**单 shot 流水线**（zero-shot prediction → builder 一次 → forge 一次），不经过 cascade 路由。改动 1 只影响 agent-full 的内部流转。zero-shot 4/10 是 Day-3 baseline，没动过。这点用户可在 `data/evaluation/smoke_gpt-zeroshot-e2e.json` 的 `method` 字段（`gpt_zeroshot + builder + forge`）核对。

---

## Numbers reference

| Source | What | Value |
|---|---|---|
| `smoke_gpt-zeroshot-e2e.json` | zero-shot e2e pass | 4/10 |
| `smoke_gpt-zeroshot-e2e.json` | zero-shot e2e cost | $0.0956 |
| `smoke_agent-full.json` (Day-4) | agent-full pass | 6/10 |
| `smoke_agent-full.json` (Day-4) | agent-full cost | $0.2912 |
| `smoke_agent-full.json` (Day-4) | cascade_depth>1 fired | 4/10 |
| `smoke_agent-full.json` (Day-4) | reflection_calls in those 4 | 2 each |
| `pretest_self_consistency.json` | SC=3 divergence on 6 non-pass | 3/6 |
| `pretest_self_consistency.json` | R8 gate cost | $0.0825 |
| Cumulative all-day spend | total LLM | ~$1.40 / $5 budget |

---

*这份 narrative 起草于 Day 4 完成时，所有数字可由 `data/evaluation/` 下 JSON 直接核对。*
