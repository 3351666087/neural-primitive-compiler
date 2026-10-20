# Verifiable Neural Primitive Compiler

**Research Mission 01：能否由能力规格直接编译出神经网络，而不针对每个任务重新训练？**

这是一个在受限计算模型上检验该路线的实验系统。模型是离散整数积分发放神经元，有 1–3 个输入、几步到十几步的时域，所有实验都在本机 CPU 上运行。系统包括：

- 一个**可执行的语义**（模拟器），
- 一个**带合同的原语库**和受约束的 **DSL**，
- **三个相互独立的验证引擎**：Z3 有界模型检测、穷举枚举、显式状态无界可达性，
- **四种合成器**：模板 CEGIS、参数枚举、原语组合枚举（DAG 和带环两种）、LLM 草图填洞，
- 一个**不需要搜索的经典 FSM 构造**和**精确的可实现性判定**，
- 给 LLM 用的 **Skill**：`skills/neural-compiler/SKILL.md`。

> **一句话结论**（详见 [evidence-ledger.md](evidence-ledger.md) 与 [theory.md](theory.md)）：
> 在有限状态的时序规格上，"由规格编译出网络"是**成立的，但这是经典结论**：每个可实现的函数式规格都能不经搜索直接编译，不可实现的可以被精确判定并给出见证，而且整个过程不需要训练。
> 真正的困难不在"能不能"，而在**规模**：合成是 Σ₂ᴾ 难的；无界验证最坏是 PSPACE 难的，实测中符号方法能多项式地处理有限记忆链，但在长程计数上和显式方法一样爆炸；精确合同的组合推理不改变增长类型；时间动力学换来的是神经元数量上的简洁，而不是新的计算能力。
> 现有证据**不支持**把这条路线外推到更广泛的智能功能。

## 主要结果（详见 evidence-ledger.md）

| 问题 | 证据 | 结论 |
|---|---|---|
| 能否不训练、直接由规格编译？ | 31 个任务（A–C 10 个，D 21 个）全部由经典构造编译，或被定理 3 判定为不可实现；编译结果全部通过无界验证 | 能，但这是经典自动机理论 |
| 编译出的网络有多大？ | 经典构造 6–258 个神经元，已知最小解 1–3 个 | 差距 4–100 倍，必须靠搜索 |
| 盲目搜索能走多远？ | CEGIS 在 3 个输入、2 个神经元时常在 240 s 内超时；3 原语带环枚举 160 万+ 候选后超时；D 组 CEGIS 有 8/21 超时 | 规模上限约 2–3 个神经元 |
| LLM 提议 + 求解器 + 验证器 | 作者本人的 D 组第 1 轮草图 6 中 5；盲测会话（只读 SKILL.md）在 10 个难任务上 10/10 首个提议成功，包括作者失败的 D02（5 个神经元） | 有用，验证器没有误判过一次；仍为同一模型家族，反例修订环节没有被检验 |
| 动力学有用吗？ | 模 2/3 计数：IF 只需 1 个神经元，无记忆需 2 / ≥ 3 个；窗口类两者相同 | 只在计数状态上有用，信息量不变 |
| 组合合同降复杂度吗？ | 显式：状态比为 1.0 / 约 0.5，两者都指数增长；符号（k-induction/PDR）：有限记忆链到 N = 64–256，计数链止于 N = 4，合同只改变常数因子 | 精确合同下不能；爆炸取决于记忆的类型 |
| 名称能当证据吗？ | `pairdet` 的直觉合同被反例 `1110` 驳倒 | 不能 |

## 单命令安装、测试与示例

```bash
./run.sh
```

它依次执行 `make install`（创建 `.venv` 并安装 `z3-solver numpy pytest hypothesis`）、`make test`（全部测试）和 `make demo`。也可以分步运行：

```bash
make install
```

```bash
make test
```

```bash
make demo
```

```bash
make experiments
```

已在 Apple M4 MacBook Air（arm64）、Python 3.12.13、z3-solver 5.3.1 上测试，Z3 在 Apple Silicon 上安装和运行都没有问题。

## 快速上手

```bash
.venv/bin/npc primitives
```

```bash
.venv/bin/npc verify examples/toggle.npc --network toggle_lite --spec parity_sparse --compositional
```

```bash
.venv/bin/npc realize examples/parity_latency1.npc --spec parity_latency1
```

```bash
.venv/bin/npc synth experiments/tasks.npc --spec C2_parity_dense --method cegis --out out/c2.json
```

退出码：0 = 已验证/已合成，1 = 有反例/不可实现/已穷尽，2 = 无结论（超时、UNKNOWN、资源上限），3 = 输入错误。

## 仓库结构

| 路径 | 内容 |
|---|---|
| `src/npc/network.py` | 网络数据模型、静态合法性检查、代价度量；文档字符串中给出形式语义 |
| `src/npc/simulator.py` | 参考解释器、numpy 批量模拟器、有限状态步进函数（三者经测试一致） |
| `src/npc/spec.py` | 规格语言：有界过去时 LTL + 计数；解析器、批量求值器、增量监视器 |
| `src/npc/smt.py` | 网络动力学和规格的 Z3 (QF_LIA) 编码，支持参数洞 |
| `src/npc/verify.py` | `bmc` / `exhaustive` / `reach` 三个引擎；反例一律经参考解释器回放 |
| `src/npc/dsl.py` + `src/npc/lib/primitives.npc` | `.npc` 语言与 13 个带合同的原语 |
| `src/npc/compose.py` | 合同层（组合）验证，含反馈和假设消解 |
| `src/npc/synth.py` | `cegis`、`minimize_synapses`、`search_neurons`、`enumerate_params`、`compose_dag`、`compose_cyclic`、`sketch` |
| `src/npc/fsm.py` | 规格 → 最小 Moore 机 → 可实现性判定（定理 3）→ one-hot 经典构造 |
| `src/npc/cli.py` | 命令行 `npc` |
| `tests/` | 单元测试、性质测试（hypothesis）、反例测试 |
| `experiments/` | 任务、手工设计、运行器、原始结果 JSON、D 组协议、LLM 草图 |
| `skills/neural-compiler/SKILL.md` | LLM 工作流 |

## 设计决策（以及原因）

1. **所有突触延迟 ≥ 1**。网络因此严格因果：任何反馈环都有良定义的语义，同步更新与神经元顺序无关，而且循环假设–保证推理可以靠对时间的归纳来证明可靠。代价是网络永远不能对同一步的输入作出反应，这一点由定理 3 精确刻画。
2. **原语用 DSL 本身写成**（神经元 + 突触 + 合同），不能调用宿主语言。参数算术只允许整数 `+ - *`，并用白名单 AST 解析器检查（`tests/test_dsl.py` 检验了无逃逸）。
3. **名称不是证据**：没有合同的原语会被拒绝；`pairdet`（看起来像"连续两次脉冲检测器"）的直觉合同会被验证器用反例 `in=1110` 驳倒。
4. **结论分级**：VERIFIED_BOUNDED(T) ≠ VERIFIED_UNBOUNDED；TIMEOUT、UNKNOWN、RESOURCE_LIMIT 都不算通过；CEGIS 的 UNREALIZABLE 只覆盖模板的参数范围，定理 3 的 UNREALIZABLE 覆盖任意规模。
5. **LLM 只提议**：草图中的选择洞 `?{…}` 和整数洞 `?[lo,hi]` 由工具填充和验证；Skill 禁止 LLM 自行宣布通过。

## Mission 02：认知原语（`mission-02` 分支）

Mission 02 检验：一套紧凑、可参数化、组合语义可验证的原语，能否让智能体对**未见的**认知功能规格直接构造网络，而不逐任务训练权重。Mission 01 的结果作为基础设施保留，没有改动。

- 首轮判定见 [mission-02/SCIENTIFIC_VERDICT.md](mission-02/SCIENTIFIC_VERDICT.md)：核心假说 **INCONCLUSIVE**；构造与推导 SUPPORTED_IN_TOY_DOMAIN；"发现了不只是重编码的认知原语" NOT_SUPPORTED。用任务书的话说：**目前只得到程序综合的神经实现**。
- 冻结后的 16 个未见任务：A-LLM 16/16，A-auto 10/16（都是差分测试 [E]；无界检查在状态预算处 UNKNOWN）。
- 否定结果见 [mission-02/negative-results.md](mission-02/negative-results.md)；代码在 `src/cog/`，Skill 在 `skills/cognitive-compiler/SKILL.md`。
- 复现：`make mission02`（Z3 参数化证明、未见任务全流程、事后第三规模检查）。

## 文档

- [prior-art.md](prior-art.md)：文献审计与新颖性对照（每条引用都标了核查状态）
- [research-hypotheses.md](research-hypotheses.md)：实验前写下的假设 H1–H8 与证伪条件
- [theory.md](theory.md)：形式语义、定理 1–5 及证明，以及"什么被证明了、以什么方式"
- [evidence-ledger.md](evidence-ledger.md)：逐条证据、对假设的判定，以及 Phase 6 的六个问题
- [limitations.md](limitations.md)：限制与偏差
- `experiments/results/SUMMARY_ABC.md`、`experiments/results/HYPOTHESES_CHECK.md`、`experiments/D_unseen/SUMMARY.md`：由原始 JSON 自动生成的表格

## 关于 Git

开发环境的命令沙箱禁止写入 `.git/config`。获得用户明确许可后，所有 git 操作改在用户的终端面板中执行（不受沙箱限制）。提交历史按阶段记录：工具链 → A–C 结果 → 冻结 → D 组 → 最终评估。D 组的冻结点同时由 SHA-256 清单和一次提交标记。

## 许可

代码与文档以 [MIT License](LICENSE) 发布。
