# Week 1 MCC Spike Plan

**Goal**: 搭起 Minimal Compilable Closure (MCC) 基础设施，让 Foundry 能直接编译并测试真实 Code4rena 合约，替代当前 `builder.py` 写 inline-replica 的方案。

**Timebox**: 5 个工作日（Day 1 – Day 5）。Day 5 EOD 未达 acceptance gate 则冻结现状，写 retro，决定是否延 1-2 天进 Week 2 或砍范围。

**Week 1 Acceptance Gate**: 5 个 hand-picked case 中至少 **3 个** 在 `forge build` 下编译通过、build 时间 ≤ 30s。

**MCC 在项目中的定位**: 基础设施层，**不是论文 headline**。Headline 是 agent 的 detection performance；MCC 是让那些数字 trustworthy 的脚手架（论文 §4 Infrastructure）。

---

## 1. Hand-Picked Cases for Spike

| 序号 | Case | 仓库路径 | 选择理由 | 预期难度 |
|---|---|---|---|---|
| C1 | VulnerableAccessControl | `data/contracts/VulnerableAccessControl.sol` | 玩具 demo，无外部 dep；must-pass，是闭环 sanity check | 极易 |
| C2 | CSW (Coinbase Smart Wallet) | `data/contracts/raw/CSW/CoinbaseSmartWallet.sol`<br>`data/contracts/raw/CSW/CoinbaseSmartWalletFactory.sol` | 2 文件，Solady 依赖，现代 Solidity 0.8.23；现代项目代表 | 中 |
| C3 | GRA (The Graph) | `data/contracts/raw/GRA/{BridgeEscrow, L2GraphToken, GraphTokenUpgradeable, L1GraphTokenGateway, L2GraphTokenGateway}.sol` | 5 文件，OZ-upgradeable，跨合约调用；典型 DeFi 多文件项目 | 中-高 |
| C4 | NOYA | `data/contracts/raw/NOYA/AccountingManager.sol`<br>`data/contracts/raw/NOYA/Registry.sol` | 2 文件，会计 + registry 模式；中等复杂度 | 中 |
| C5 | 来自 `eval_set.json` 的随机 case | `data/dataset/eval_set.json` 第一条有 contract_source 的 | 数据集真实样本，external validity | 未知 |

**选择原则**: 4 个已有 raw source 的 + 1 个 dataset 内的，覆盖"无 dep / 现代库 / 多文件 / 升级合约 / 数据集真实"5 种情形。

---

## 2. Vendored Library 清单（v0 必备）

`lib/vendored/` 一次性配齐：

| 库 | 版本 | 大小估计 | 覆盖范围 |
|---|---|---|---|
| `forge-std` | v1.9.4 | ~200 KB | 全部 test 文件依赖 |
| `openzeppelin-contracts-v3.4.2` | v3.4.2 | ~5 MB | 2020-2021 Code4rena（Solidity 0.6/0.7） |
| `openzeppelin-contracts-v4.9.5` | v4.9.5 | ~6 MB | 2022-2023 主流（Solidity 0.8.0-0.8.20） |
| `openzeppelin-contracts-v5.0.2` | v5.0.2 | ~7 MB | 2024+（custom error 改版） |
| `openzeppelin-contracts-upgradeable-v4.9.5` | v4.9.5 | ~3 MB | upgradeable 系列（GRA 案例需要） |
| `solady` | v0.0.245 | ~2 MB | 新项目（CSW 需要） |
| `solmate` | v6 | ~1 MB | 部分 DeFi 项目 |

**总大小 ~25 MB**，直接 git commit，不用 LFS。

**版本固定原则**: 每个大版本固定一个 patch，不维护多个 patch 级。OZ minor 内 ABI 兼容性已验证。

**安装步骤** (`scripts/mcc/install_libs.sh`):
```bash
mkdir -p lib/vendored
cd lib/vendored
git clone --depth 1 --branch v1.9.4 https://github.com/foundry-rs/forge-std.git
git clone --depth 1 --branch v3.4.2 https://github.com/OpenZeppelin/openzeppelin-contracts.git openzeppelin-contracts-v3.4.2
git clone --depth 1 --branch v4.9.5 https://github.com/OpenZeppelin/openzeppelin-contracts.git openzeppelin-contracts-v4.9.5
git clone --depth 1 --branch v5.0.2 https://github.com/OpenZeppelin/openzeppelin-contracts.git openzeppelin-contracts-v5.0.2
git clone --depth 1 --branch v4.9.5 https://github.com/OpenZeppelin/openzeppelin-contracts-upgradeable.git openzeppelin-contracts-upgradeable-v4.9.5
git clone --depth 1 --branch v0.0.245 https://github.com/Vectorized/solady.git
git clone --depth 1 https://github.com/transmissions11/solmate.git
# 删 .git 减小体积（可选）
find . -name ".git" -type d -exec rm -rf {} +
```

---

## 3. Day-by-Day Tasks

### Day 1 — Vendored Libs + solc-select

**Tasks**
1. 跑 `scripts/mcc/install_libs.sh`，把 7 个库克隆到 `lib/vendored/`
2. 装 5 个 solc 版本：`solc-select install 0.6.12 0.7.6 0.8.10 0.8.20 0.8.23`
3. 在 C1 (VulnerableAccessControl) 上做 sanity check：手写 `foundry.toml`、跑 `forge build`、确认通过
4. 文档化 install 步骤到 `docs/RUN.md` 末尾"MCC setup"段

**Deliverable**: `lib/vendored/` 7 个子目录齐全；`solc-select versions` 显示 5 个版本；C1 能 `forge build` 成功

**Exit test**
```bash
test -d lib/vendored/forge-std/src \
  && test -d lib/vendored/openzeppelin-contracts-v3.4.2/contracts \
  && test -d lib/vendored/openzeppelin-contracts-v4.9.5/contracts \
  && test -d lib/vendored/openzeppelin-contracts-v5.0.2/contracts \
  && test -d lib/vendored/openzeppelin-contracts-upgradeable-v4.9.5/contracts \
  && test -d lib/vendored/solady/src \
  && solc-select versions | grep -qE "0\.6\.12" \
  && solc-select versions | grep -qE "0\.8\.23"
```

**估时**: 2-3 小时（含网络下载）

---

### Day 2 — Case Loader + Closure Extractor

**Tasks**
1. 写 `scripts/mcc/case_loader.py`:
   - `load_case(case_id: str) -> CaseInfo`，从 `data/dataset/eval_set.json` 读
   - 返回 `target_file` 路径、`pragma` 字符串、`project_root` 目录
2. 写 `scripts/mcc/extract_closure.py`:
   - `extract_closure(target: Path, project_root: Path) -> ClosureResult`
   - BFS 遍历 import 图，正则解析 import 语句
   - `MAX_FILES = 10` 硬上限
   - 区分 vendored import（`@openzeppelin/...`, `solady/...`, `forge-std/...`）和项目内 import（相对路径）
   - 返回：`ClosureResult(target, project_files: list[Path], vendored: set[str], size: int, within_budget: bool)`
3. 在 C1 + C2 上单元测试

**Deliverable**: 2 个脚本 + pytest 单元测试，C1（0 deps）和 C2（少量 Solady deps）都能正确解析

**Exit test**
```bash
pytest tests/unit/test_mcc_closure.py -v \
  && python scripts/mcc/extract_closure.py \
      --target "data/contracts/VulnerableAccessControl.sol" \
      --project-root "data/contracts/" \
  | grep -q "file_count\": 1" \
  && python scripts/mcc/extract_closure.py \
      --target "data/contracts/raw/CSW/CoinbaseSmartWallet.sol" \
      --project-root "data/contracts/raw/CSW/" \
  | grep -qE "\"within_budget\":\s*true"
```

**估时**: 1 个完整工作日

---

### Day 3 — Dep Router + Project Materializer

**Tasks**
1. 写 `scripts/mcc/dep_router.py`:
   - `route_deps(pragma: str, hint_oz_version: str = None) -> DepChoice`
   - 输入 pragma → 输出 `DepChoice(solc_version, oz_version, remappings: dict[str, str])`
   - 规则：
     - `^0.8.20` → solc 0.8.20 + OZ v4.9.5（默认）或 v5.0.2（如 hint）
     - `^0.8.0..^0.8.19` → solc 0.8.10 + OZ v4.9.5
     - `^0.7.x` → solc 0.7.6 + OZ v3.4.2
     - `^0.6.x` → solc 0.6.12 + OZ v3.4.2
     - `^0.5.x` → reject（无兼容 OZ）
2. 写 `scripts/mcc/materialize.py`:
   - `materialize(case_id: str, closure: ClosureResult, dep: DepChoice) -> Path`
   - 写入 `data/mcc_projects/<case_id>/`:
     - `foundry.toml`（含 `solc = "<version>"`）
     - `remappings.txt`
     - `src/` 内拷贝 `target` + `project_files`
     - `lib/` 软链到 `../../../lib/vendored/`
   - 输出工程根目录
3. 在 C2 + C3 上手动跑通：materialize → cd → `forge build` 观察

**Deliverable**: C2 (CSW) 和 C3 (GRA) 各自产生独立的 forge project 并 build 通过

**Exit test**
```bash
python scripts/mcc/materialize.py --case CSW-001 \
  && (cd data/mcc_projects/CSW-001 && forge build 2>&1) | grep -q "Compiler run successful"
```

**估时**: 1 个完整工作日

---

### Day 4 — Build Probe + Retry/Stub

**Tasks**
1. 写 `scripts/mcc/build_probe.py`:
   - `probe(case_id: str) -> ProbeResult`
   - 流程：
     1. Load case → extract closure → route deps → materialize
     2. 跑 `forge build`，超时 30s
     3. 失败时分析 stderr：
        - `not found` → 找出缺失的 import，写 stub interface
        - 版本不匹配 → 报错，标记 reject 原因
        - 其他错误 → 重试一次，再失败则 reject
     4. 写入 `data/mcc_projects/<case_id>/mcc_meta.json`
   - `mcc_meta.json` schema:
     ```json
     {
       "case_id": "<id>",
       "buildable": true | false,
       "solc_version": "0.8.23",
       "oz_version": "4.9.5",
       "file_count": 3,
       "vendored_libs": ["solady", "forge-std"],
       "build_time_s": 4.2,
       "build_log_tail": "...",
       "rejected_reason": null
     }
     ```
2. 写 stub 生成器（在 `extract_closure.py` 加 `_generate_stub_for_unresolved_import`）：
   - 用 `interface I<Name> { }` 形式占位
   - 在 stub 文件头加注释标记 auto-generated

**Deliverable**: `build_probe.py` 在 C1-C4 上运行完成，每个产生 `mcc_meta.json`

**Exit test**
```bash
for case in C1 C2 C3 C4; do
  python scripts/mcc/build_probe.py --case $case
  test -f "data/mcc_projects/$case/mcc_meta.json"
done
```

**估时**: 1 个完整工作日

---

### Day 5 — 5-Case Sweep + Spike Report

**Tasks**
1. 跑 C5（从 eval_set 选一个有 contract_source 的 case）
2. 跑全 5 个 case 的 build_probe，统计结果
3. 写 `data/mcc_projects/spike_report.md`，含：
   - 每个 case 的 pass/fail + 原因
   - 总体 build success rate
   - 每个失败 case 的 root cause（OZ 版本？stub 不够？多文件解析失败？）
   - Acceptance gate 评估：通过/不通过
4. 如果通过：写 Week 2 batch plan
5. 如果不通过：写 retro，列出 3-5 个具体修复点

**Deliverable**: `data/mcc_projects/spike_report.md`

**Exit test**
```bash
test -f data/mcc_projects/spike_report.md \
  && [ $(grep -c "buildable.*true" data/mcc_projects/spike_report.md) -ge 3 ]
```

**估时**: 半天 sweep + 半天写报告

---

## 4. Week 1 Acceptance Gate（Day 5 EOD）

硬性条件，全部满足才进 Week 2：

- [ ] `data/mcc_projects/spike_report.md` 存在
- [ ] 5 个 hand-picked case 中至少 3 个 `buildable=true`
- [ ] 通过的 case build 时间均 ≤ 30s
- [ ] 没有需要手工干预的步骤（脚本一行命令跑完）
- [ ] `mcc_meta.json` schema 字段齐全

**通过 → Week 2 plan**：batch apply to 42 cases；预期 buildable rate ~70%

**不通过 → 三选一**：
- (a) 延 2 天到 Week 2 Day 1-2 修关键 bug
- (b) 砍范围：放宽闭包 `MAX_FILES` 到 15、接受更多 stub
- (c) 升级到老师：MCC 比预期难，能否接受 inline-replica + MCC 混合方案

---

## 5. Week 1 特有风险 + Mitigation

| # | 风险 | 缓解 |
|---|---|---|
| W1 | OZ v4 / v5 在同一项目混用导致 import 不兼容 | per-case 检测 OZ 版本；`mcc_meta.json` 记录；默认 v4，case JSON 加 `oz_version` 字段做 override |
| W2 | Solidity pragma 与 vendored 库无兼容版本（如 `pragma 0.5.x`） | Day 3 Dep Router 直接 reject；spike_report 单独标记此类 case |
| W3 | Stub 生成把"真正会被攻击调用"的 interface 占位掉 | Stub 仅生成在"未被 vulnerable_function 调用链触及"的 import 上；闭包提取保留调用链分析（Day 4 加） |
| W4 | macOS / Windows / Linux symlink 行为差异 | 文档化 Unix 为 canonical dev 环境；`materialize.py` Windows fallback 用 copy 代替 symlink |
| W5 | Code4rena 项目原 OZ 版本与我们 vendored 不一致导致行为差异 | Honest limitation；`mcc_meta.json` 记 `oz_version` 与 case 元数据原 OZ 版本对照；论文 Limitations 单独说明 |
| W6 | Day 2-3 闭包解析正则覆盖不全（多行 import 等） | 准备 fallback 正则；最终 5 case sweep 出现解析失败时打日志 |
| W7 | `forge build` 超时 30s 卡死（巨型项目） | 30s 硬 timeout，超时直接 reject；不阻塞 sweep |
| W8 | `solc-select install` 在某些机器上失败 | install 脚本含每个 solc 版本的独立失败检测；缺少版本则该版本对应的 case 全部 reject |

---

## 6. Files Touched in Week 1

```
lib/vendored/
├── forge-std/                                  (new)
├── openzeppelin-contracts-v3.4.2/              (new)
├── openzeppelin-contracts-v4.9.5/              (new)
├── openzeppelin-contracts-v5.0.2/              (new)
├── openzeppelin-contracts-upgradeable-v4.9.5/  (new)
├── solady/                                     (new)
└── solmate/                                    (new)

scripts/mcc/                                    (new directory)
├── __init__.py
├── install_libs.sh
├── case_loader.py
├── extract_closure.py
├── dep_router.py
├── materialize.py
└── build_probe.py

tests/unit/                                     (modified)
└── test_mcc_closure.py                         (new)

data/mcc_projects/                              (new directory)
├── C1/ ... C5/                                 (5 case projects)
│   ├── foundry.toml
│   ├── remappings.txt
│   ├── src/
│   ├── lib/  (symlinks)
│   └── mcc_meta.json
└── spike_report.md                             (Day 5 deliverable)

docs/
├── WEEK1_MCC_SPIKE.md                          (this file)
└── RUN.md                                      (modified, add MCC setup section)
```

`src/agent/` 不动；这是基础设施 spike，不碰 agent 主代码。Builder 改写是 Week 2 任务。

---

## 7. Week 2 Handoff（仅当 Week 1 acceptance gate 通过）

1. **批量化 MCC**（Day 6-7）：`build_probe.py` 跑 `data/dataset/eval_set.json` 全 42 cases，aggregate 统计
2. **Builder node 重构**（Day 8-9）：`src/agent/nodes/builder.py` 改写
   - 移除 "do NOT import from ../src/" 约束
   - prompt 改为 "MUST `import \"src/<contract_name>.sol\";` and attack the imported contract"
   - Verifier sanity check: grep 生成的 PoC 里如果有 `contract <name>` 重声明则 reject
3. **第一轮诚实 baseline**（Day 10）：在 MCC buildable subset 上重跑 Day-4 pipeline + Slither + GPT-zeroshot，与 inline-replica 时代的 85.7% 数字对照
4. **Decision**（Day 10 EOD）：根据诚实数字决定是否进 Week 3 的数据扩集（42→100）

---

## 8. 跟原计划的对应关系

本 spike 是 6-8 周计划的 Week 1。完整 8 周路径见上层 plan（口头版，未持久化）：

```
Week 1     MCC spike (本文)
Week 2     MCC batch + builder 重构 + 第一轮诚实 baseline
Week 3-4   Dataset 扩集到 N=100,跑 4-arm ablation + 2 baseline
Week 5     Full ablation 表 + bootstrap CI
Week 6     N5 (DPO) Decision Gate
Week 7-8   分支 A: N5 训练 + 最终评测
           分支 B: N4-only paper 收官 + buffer
```

**MCC 在论文中的定位**: §4 Infrastructure（不是 §1 Contribution）。Headline 永远是 agent 的 detection metric。
