# Verifiable Neural Primitive Compiler

本仓库研究一个问题：能否由能力规格直接构造出可执行、可验证的神经网络，而不针对每个任务训练权重？研究分三轮进行，每一轮都把上一轮留下的未知作为对象：

- **Mission 01** 以有限状态时序规格为对象，检验"规格 → 网络"的编译路线。
- **Mission 02** 冻结一组原语，检验能否对此前未见过的认知功能规格直接构造网络。
- **Mission 03** 去掉规格中的机制信息，检验能否只凭目标级证据（输入输出范例、被动观测）发现机制，并在第三方任务上与强符号基线比较。

三轮使用同一个计算模型：离散整数积分发放（IF）神经元，所有突触延迟 ≥ 1。Mission 03 的发现过程在符号层完成，神经网络只在一次端到端检查中作为编译目标出现。全部实验都在本机 CPU 上运行。

## 研究轮次与判定

| 研究轮次 | 问题 | 判定 | 主要文档 |
|---|---|---|---|
| Mission 01 | 能否由有限状态时序规格直接编译出网络，而不训练？ | 能，但这是经典自动机理论的结论；证据不支持把这条路线外推到更广泛的智能功能 | [evidence-ledger.md](evidence-ledger.md)、[theory.md](theory.md) |
| Mission 02 | 原语冻结后，能否对未见的认知功能规格直接构造网络？ | 核心假说 INCONCLUSIVE；构造与推导 SUPPORTED_IN_TOY_DOMAIN；"发现了不只是重编码的认知原语" NOT_SUPPORTED | [mission-02/SCIENTIFIC_VERDICT.md](mission-02/SCIENTIFIC_VERDICT.md) |
| Mission 03 | 不给机制，只给目标级证据，能否发现并构造未见能力？ | 主结论 INCONCLUSIVE；在给定假设形式内的机制发现 SUPPORTED_IN_TOY_DOMAIN；相对符号 DSL 的表示层优势 NOT_SUPPORTED；第三方持出任务上覆盖 1.5 % | [mission-03/SCIENTIFIC_STATUS.md](mission-03/SCIENTIFIC_STATUS.md) |

**三轮合起来的结论**。Mission 01 表明，机制完全给定时，编译是经典问题。Mission 02 表明，机制以坐标映射的形式写在规格里时，"直接构造"实际上是翻译。Mission 03 表明，只给目标级证据时，在设计者给定的假设形式之内可以发现机制，方法就是程序综合。三轮都没有给出的，是假设形式本身（并集映射、区域占据、对象、计数等表示层）如何从证据中产生；这是当前最不了解的机制，下一步的鉴别实验见 [mission-03/OPEN_QUESTIONS.md](mission-03/OPEN_QUESTIONS.md)。

### 各轮之间的关系

后一轮都把前一轮当作基础设施使用，不修改前一轮的源码、冻结记录和原始结果。后一轮的审计对前一轮的结论作了三处限定：

1. **Mission 02 对 Mission 01**：`latency1_weights(bound=64)` 给出的"no network of any size"只在输入数 m ≤ 3 时成立，对一般的 m 只能理解为"在 |参数| ≤ 64 内无解"。Mission 01 实际报告过的不可实现结论都只有 m ≤ 2 个输入，因此仍然成立（[mission-02/G0-audit.md](mission-02/G0-audit.md)）。
2. **Mission 03 对 Mission 02（LLM 路线）**：一个不调用 LLM 的查表解码器能逐字节复现全部 16 个 A-LLM 程序。因此 A-LLM 的 16/16 测量的是任务描述对机制的编码，而不是机制发现。
3. **Mission 03 对 Mission 02（自动路线）**：A-auto 的规模外推所依赖的手写映射词汇，可以由一个不含命名映射、对复合封闭的通用格点几何先验替代（[mission-03/UNKNOWNNESS_AUDIT.md](mission-03/UNKNOWNNESS_AUDIT.md)）。

## Mission 01：由时序规格编译神经网络

**问题**。在有限状态的时序规格上，能否由规格直接编译出网络，而不训练？

**方法**。系统由以下部分组成：

- 可执行的语义（模拟器）；
- 带合同的原语库，以及受约束的 DSL；
- 三个相互独立的验证引擎：Z3 有界模型检测、穷举枚举、显式状态无界可达性；
- 四种合成器：模板 CEGIS、参数枚举、原语组合枚举（DAG 与带环两种）、LLM 草图填洞；
- 不需要搜索的经典 FSM 构造，以及精确的可实现性判定；
- 供 LLM 使用的 Skill：`skills/neural-compiler/SKILL.md`。

| 问题 | 证据 | 结论 |
|---|---|---|
| 能否不训练、直接由规格编译？ | 31 个任务（A–C 组 10 个，D 组 21 个）全部由经典构造编译，或被定理 3 判定为不可实现；编译结果全部通过无界验证 | 能，但这是经典自动机理论 |
| 编译出的网络有多大？ | 经典构造 6–258 个神经元，已知最小解 1–3 个 | 差距 4–100 倍，缩小差距要靠搜索 |
| 盲目搜索能走多远？ | CEGIS 在 3 个输入、2 个神经元时常在 240 s 内超时；3 原语带环枚举 160 万+ 候选后超时；D 组 CEGIS 有 8/21 超时 | 规模上限约 2–3 个神经元 |
| LLM 提议 + 求解器 + 验证器 | 作者本人的 D 组第 1 轮草图 6 中 5；盲测会话（只读 SKILL.md）在 10 个难任务上 10/10 首个提议成功，包括作者失败的 D02（5 个神经元） | 在这些任务上有效，验证器没有出现一次误判；提议者仍属同一模型家族，反例修订环节没有被检验 |
| 时间动力学有用吗？ | 模 2/3 计数：IF 只需 1 个神经元，无记忆网络需 2 / ≥ 3 个；窗口类任务两者相同 | 只在计数状态上有用，信息量不变 |
| 组合合同能降低复杂度吗？ | 显式：状态比为 1.0 / 约 0.5，两者都指数增长；符号（k-induction/PDR）：有限记忆链到 N = 64–256，计数链止于 N = 4，合同只改变常数因子 | 精确合同下不能；爆炸与否取决于记忆的类型 |
| 名称能当证据吗？ | `pairdet` 的直觉合同被反例 `1110` 驳倒 | 不能 |

**结论**（详见 [evidence-ledger.md](evidence-ledger.md) 与 [theory.md](theory.md)）。由规格直接编译出网络是可行的，而且整个过程不需要训练：每个可实现的函数式规格都能不经搜索直接编译，不可实现的规格可以被精确判定并给出见证。这是经典自动机理论的结论。困难在于规模。合成是 Σ₂ᴾ 难的，无界验证最坏是 PSPACE 难的。实测中，符号方法能以多项式代价处理有限记忆链，但在长程计数上与显式方法一样爆炸。精确合同下的组合推理不改变增长类型。时间动力学换来的是神经元数量上的简洁，而不是新的计算能力。

## Mission 02：对未见认知功能的直接构造

**问题**。是否存在一套紧凑、可参数化、组合语义可验证的原语，使智能体读取此前未见过的认知功能规格后，只通过实例化与组合原语、不训练权重，就能构造出满足规格的网络？

**方法**。实验分四步。

1. **任务族**。设计阶段使用两个任务族：N×N 网格上的空间工作记忆（"心像变换"），以及对象–属性绑定与关系查询。第三个任务族（网格上的多个对象）只作为未见组合出现。
2. **原语发现**。原语不是预先命名的，而是从设计任务的黑盒探测中提取：逐个（命令, 坐标）学习更新规则，再归纳成参数化模式。由此得到 CMR（字母门控的并集寄存器）、SEL（门控选择）、ANY（区域 OR 归约）和 GATE（与 / 与非）四个原语。它们作用在带类型的索引空间上，由一个不含用户函数的 JSON IR 组合。
3. **合同**。原语合同和一个组合定理由 Z3 在任意索引集或任意 N 上证明，每条结论都附有非空性检查与变异检查。
4. **冻结与评测**。源码冻结后（树哈希 `1c40ea5a…`），由该哈希导出的种子生成 16 个未见任务，比较三条构造路线：A-LLM（读自然语言描述写 IR，程序在任何裁判运行之前提交）、A-auto（只在两个最小规模上做黑盒探测，不使用 LLM）、随机结构基线。

| 问题 | 证据 | 结论 |
|---|---|---|
| 黑盒探测能否压缩出跨任务族共享的模式？ | 353 条（坐标, 字母）规则都是"新值 = 若干旧坐标的 OR"这一模板的实例，两个任务族共用；被动学习在 6 个可构造任务中有 3 个过度泛化，主动探测 6/6 正确 | 能，但这个模板就是经典的寄存器更新 |
| 冻结后能否不求解权重，直接构造未见任务？ | A-LLM 16/16；A-auto 10/16，6 个失败都是安全拒绝（4 个条件命令、2 个 `same` 查询）；随机结构每个任务 0/100 | 在这一任务类中能（差分测试，[E]） |
| 能否外推到未探测的规模？ | A-auto 构造的 4 个空间任务在 N = 3、5 探测，在 N = 8 不调用 oracle 也正确；事后选定的第三规模上 A-auto 10/10 正确，A-LLM 空间程序在 N = 11 上 8/8 正确 | 能，但规模泛化来自手写的映射词汇 |
| 逐任务权重搜索（路线 B）的代价？ | N = 2 网格上，4 个神经元的 CEGIS 模板（76 个洞）在 600 s、30 轮反例后超时；HP-2 原语只需 16 个神经元，无需搜索 | 逐任务搜索的路线被淘汰 |
| 整体功能能否由部件合同推出？ | CMR 合同（P1）与条件命令的组合定理（P4）对任意索引集成立；SEL 合同没有符号证明；编译器的正确性没有证明 | 部分能 |
| 未见任务的网络是否经过机器验证？ | 符合条件的网络上，无界乘积搜索全部在 2,000,000 个状态的预算处返回 UNKNOWN | 否；未见任务只有差分测试证据 |
| 这些原语是新的认知计算规律吗？ | CMR、SEL、ANY、GATE 分别对应寄存器加多路选择器、AND-OR 交叉开关、OR 归约、AND / AND-NOT；任务规格已给出每个命令的坐标映射 | 否：目前只得到程序综合的神经实现 |

**结论**（详见 [SCIENTIFIC_VERDICT.md](mission-02/SCIENTIFIC_VERDICT.md) 与 [negative-results.md](mission-02/negative-results.md)）。在冻结后生成的未见任务上，不求解任何权重就能直接构造出通过差分测试的网络。但原语是经典构件的重编码，规格又以机制级的坐标映射给出，构造器所做的是翻译。只要规格停留在机制层面，构造成功率就无法区分"认知原语"与"带神经后端的程序综合"，因此核心假说判为 INCONCLUSIVE。对绘画这类生成性能力，缺口首先在语义（由目标推出机制）和知识（视觉与运动先验，包括映射词汇本身），其次在结构（生成性选择、迭代、计数、非单调更新、索引绑定）。缺口不在计算资源：A-auto 对每个未见任务的构造时间为 0.12–0.61 s。任务书的停止条件在这一玩具域内部分成立，下一轮的修订假设（H-N1 至 H-N4）列在判定文件的 Q6 中。

## Mission 03：从目标级证据中发现机制

**问题**。不给机制，只给目标级证据，能否发现机制并构造未见能力？任务书要求每个问题都有竞争解释、事先锁定的预测、强符号基线和独立的持出任务，并允许以 INCONCLUSIVE 结束。

**方法**。研究分五步。

1. **未知性审计**。核对 Mission 02 的证据，检验三项信息泄漏假说，并列出构造所需知识的实际来源。
2. **竞争假说**。四条机制层路线（由范例发现机制、生成性选择、关系绑定、部分可观测）与两个零假说（神经后端不必要；与同等信息的符号 DSL 相比没有表示层优势），按鉴别力选出前两条优先研究。
3. **探索循环**。先在不扩建原语库的前提下，解释 Mission 02 自动路线解不了的两类任务（条件命令与关系查询 `same`），再追问每次失败背后的机制。判据或先验的每次修改都在看到相应结果之前以修正案提交，共 10 个。
4. **独立挑战**。ARC-AGI-1 公开任务（第三方，Apache-2.0）：训练集 400 个用于开发，评测集 400 个作为持出集，在解算器冻结后只运行一次。
5. **公平对照**。发现型构造器 M-DISC 与表达类大部分重叠的命名词汇 DSL（B-SAME）、表达更丰富的 DSL（B-RICH）、平凡基线和三种消融比较。

| 问题 | 证据 | 结论 |
|---|---|---|
| Mission 02 的未见任务成功中有多少来自泄漏？ | 查表解码器逐字节复现 16 个 A-LLM 程序；通用格点几何先验让 25/25 个命令外推到 N = 8、11（先验须对复合封闭）；去掉单格探测后 A-auto 仍为 10/16 | 机制知识全部来自描述与脚手架；真正的特权是整幅状态读出 |
| 只凭被动范例，能否解释条件命令与 `same`？ | 原判据下失败，归因于守卫分支的不可观察域与分支内证据不足；修正判据后 DEV 4/4，在新生成的 6 个任务上冻结代码一次通过 6/6；`same` 在 16,434 个组合中唯一一致 | 在给定假设形式内可以；方法就是程序综合（分治枚举加 SAT） |
| 中间概念能否在没有候选清单时被发明？ | 只假设"存在隐藏变量"时不可识别；假设"概念是区域占据"时，Z3 在全部格子子集中唯一确定真实区域（4/4） | 需要概念的形式先验 |
| 有没有事先预测、对构造成本有可测效应的原则？ | 事先锁定的封闭性实验：由训练任务中发现的动力学闭包得到的概念库覆盖全部 6 个持出概念，100 条轨迹即全部识别；同样大小的随机库为 0；覆盖一切的通用先验需要 300 条 | 支持（DEV）；与等变假设类的已知理论一致 |
| 机制种类能否由行为定律读出？ | 固定规模下 15 个机制的定律签名两两不同；只用与规模无关的定律时，填洞与包围盒填充碰撞 | 部分 |
| 生成性目标何时无需搜索？ | 连通形状、闭合环、置换：局部生长无死路；路径：局部生长 52–67 % 走进死路，加一个距离场不动点后为 0；N 皇后两者都有死路 | 与已知理论一致，没有新规律 |
| 在第三方持出任务上表现如何？ | ARC 评测集：M-DISC 6/400（1.5 %，精度 0.86），B-SAME 4/400，B-RICH 6/400，非平凡方法的并集 14/400；去掉唯一性检查后精度降到 0.75 | 覆盖面与符号 DSL 同一量级，而且都很小 |

**结论**（详见 [SCIENTIFIC_STATUS.md](mission-03/SCIENTIFIC_STATUS.md) 与 [EXPLORATION_LEDGER.md](mission-03/EXPLORATION_LEDGER.md)）。在设计者给定的假设形式之内，只凭被动的目标级证据发现机制是可行的：概念实例被唯一发明，机制在未见规模上逐事件正确。所用的方法就是程序综合，没有表现出相对同等信息的符号 DSL 的表示层优势。在 ARC 持出集上，它与命名词汇 DSL 的覆盖都在 1–1.5 %。唯一一条经事先预测检验的原则是"概念先验应是已发现概念在已发现动力学下的闭包"。它在 DEV 任务上降低了识别所需的数据量，但还没有在第三方任务上得到足够的检验。因此主结论为 INCONCLUSIVE。本轮最不了解的机制是新的假设形式（例如对象、计数这一层表示）如何从证据中产生：所有成功都发生在给定形式之内，没有一种新形式是由数据提出的。

## 安装、测试与复现

```bash
./run.sh
```

`run.sh` 依次执行 `make install`（创建 `.venv`，安装 `z3-solver numpy pytest hypothesis`）、`make test`（全部 144 个测试）和 `make demo`。各步骤也可以单独运行：

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

```bash
make mission02
```

```bash
make mission03
```

```bash
make mission03-arc
```

| 命令 | 内容 |
|---|---|
| `make experiments` | Mission 01 的实验（A–C 组、规模、Q2、LLM 草图）与汇总 |
| `make mission02` | Mission 02 的 Z3 参数化证明、未见任务全流程和事后第三规模检查 |
| `make mission03` | Mission 03 的泄漏检查、条件命令与 `same` 的发现、确认实验、概念发明、定律签名、生成性构造与先验封闭性实验 |
| `make mission03-arc` | ARC 自检、不可判定任务集、训练集与持出集；持出集运行前核对解算器的冻结哈希，约 30 分钟 |

已在 Apple M4 MacBook Air（arm64）、Python 3.12.13、z3-solver 5.3.1 上测试。

## 快速上手

Mission 01 的命令行工具 `npc`：

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

退出码：0 = 已验证 / 已合成，1 = 有反例 / 不可实现 / 已穷尽，2 = 无结论（超时、UNKNOWN、资源上限），3 = 输入错误。

Mission 02 的参数化证明（输出与 `mission-02/experiments/proofs.txt` 对应）：

```bash
.venv/bin/python -m cog.proofs
```

Mission 03 中最快的一个发现实验：只凭被动数据，在 16,434 个库内组合中找出 `same` 查询的机制（约 4 秒，输出写入 `mission-03/experiments/p1_composition/p1_t2.json`）：

```bash
.venv/bin/python mission-03/experiments/p1_composition/run_t2.py
```

## 仓库结构

公共部分：

| 路径 | 内容 |
|---|---|
| `tests/` | 单元测试、性质测试（hypothesis）、反例测试 |
| `Makefile`、`run.sh` | 安装、测试与各轮实验的入口 |

Mission 01：

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
| `experiments/` | 任务、手工设计、运行器、原始结果 JSON、D 组协议、LLM 草图 |
| `skills/neural-compiler/SKILL.md` | LLM 工作流 |

Mission 02：

| 路径 | 内容 |
|---|---|
| `src/cog/tasks.py` | 任务族的参考语义，即规格本身；构造代码不得导入它（由测试强制） |
| `src/cog/prims.py` | CMR、SEL、ANY、GATE 四个原语模板 |
| `src/cog/ir.py` | 带类型索引空间上的 JSON IR 及其编译器；没有用户函数，也没有 eval |
| `src/cog/check.py` | 差分测试、无界乘积搜索 `reach_equiv`、布线自同构检查 |
| `src/cog/proofs.py` | Z3 参数化证明 P1–P5 |
| `src/cog/learn.py`、`src/cog/auto.py` | 黑盒结构学习（被动学习与主动探测）和 A-auto 构造路线 |
| `src/cog/realize.py` | 精确（不设权重界）的延迟 1 可实现性判定 |
| `src/cog/unseen.py` | 未见任务生成器，与原语一起冻结 |
| `mission-02/` | 文档、协议与实验；`experiments/` 下是原始 JSON、日志和运行脚本 |
| `skills/cognitive-compiler/SKILL.md` | LLM 工作流：由能力描述写 IR，结论只来自裁判 |

Mission 03：

| 路径 | 内容 |
|---|---|
| `mission-03/` | 文档与协议；`experiments/` 下按轮次存放脚本、原始 JSON 和日志（泄漏检查、条件命令与 `same`、概念发明、定律签名、生成性构造、先验封闭性、ARC） |
| `mission-03/experiments/arc/` | ARC 上的 M-DISC 构造器、B-SAME / B-RICH 基线、运行器与冻结清单 `arc_freeze.json` |
| `mission-03/external/arc-agi-1/` | ARC-AGI-1 公开任务的未修改副本（Apache-2.0），附完整性清单；来源与污染风险见 `mission-03/external/ARC_PROVENANCE.md` |

## 设计决策（以及原因）

1. **所有突触延迟 ≥ 1**。网络因此严格因果：任何反馈环都有良定义的语义，同步更新与神经元顺序无关，循环的假设–保证推理也可以靠对时间的归纳证明是可靠的。代价是网络不能对同一步的输入作出反应，这一点由定理 3 精确刻画。
2. **原语用 DSL 本身写成**（神经元 + 突触 + 合同），不能调用宿主语言。参数算术只允许整数 `+ - *`，并用白名单 AST 解析器检查（`tests/test_dsl.py` 检验了无逃逸）。Mission 02 的 IR 同样没有逃逸口（`test_ir_has_no_escape_hatch`）。
3. **名称不是证据**。没有合同的原语会被拒绝；`pairdet`（看起来像"连续两次脉冲检测器"）的直觉合同会被验证器用反例 `in=1110` 驳倒。Mission 02 的任务书同样禁止把"记忆""注意""推理"等功能标签当作已发现的原语。
4. **结论分级**。VERIFIED_BOUNDED(T) ≠ VERIFIED_UNBOUNDED；TIMEOUT、UNKNOWN、RESOURCE_LIMIT 都不算通过；CEGIS 的 UNREALIZABLE 只覆盖模板的参数范围，定理 3 的 UNREALIZABLE 覆盖任意规模。Mission 02 起，每条结论另外标注证据等级：[L] 文献、[P] 纸面论证、[M] 机器检查、[E] 统计实验。
5. **LLM 只提议**。草图中的选择洞 `?{…}` 和整数洞 `?[lo,hi]` 由工具填充和验证；两个 Skill 都禁止 LLM 自行宣布通过。
6. **规格与构造分离**。Mission 02 的参考语义 `cog.tasks` 就是规格，构造代码只能把它当黑盒探测，或者读自然语言描述（`test_constructors_never_import_the_spec`）。
7. **预注册与冻结**。Mission 02 的假设在编写任何原语代码之前写入 `mission-02/hypotheses.md`，之后不改动；未见任务的种子由冻结源码的哈希导出，A-LLM 的程序在任何裁判运行之前提交。
8. **协议先于实验，修改以修正案记录**。Mission 03 的每个实验都先在 `mission-03/CHALLENGE_PROTOCOL.md` 中锁定竞争解释、信息来源、预算与预测并提交，再编写或运行代码。看到失败后对判据或先验的修改以编号修正案提交，原判据下的结果照常保留；被推翻的预测在 `SCIENTIFIC_STATUS.md` §5 中逐条列出。
9. **外部持出集的访问规则**。ARC 评测集只由冻结后的脚本运行一次；开发阶段只用自造的合成任务调试，训练集只读取结果标签。运行器只输出任务编号与结果，不输出网格内容。

## 文档

Mission 01：

- [prior-art.md](prior-art.md)：文献审计与新颖性对照（每条引用都标了核查状态）
- [research-hypotheses.md](research-hypotheses.md)：实验前写下的假设 H1–H8 与证伪条件
- [theory.md](theory.md)：形式语义、定理 1–5 及证明，以及"什么被证明了、以什么方式"
- [evidence-ledger.md](evidence-ledger.md)：逐条证据、对假设的判定，以及 Phase 6 的六个问题
- [limitations.md](limitations.md)：限制与偏差
- `experiments/results/SUMMARY_ABC.md`、`experiments/results/HYPOTHESES_CHECK.md`、`experiments/D_unseen/SUMMARY.md`：由原始 JSON 自动生成的表格

Mission 02：

- [RESEARCH_NORTH_STAR.md](mission-02/RESEARCH_NORTH_STAR.md)：锁定的研究问题与禁止宣布为成功的情况
- [hypotheses.md](mission-02/hypotheses.md)：预注册的假设 M2-H1 至 M2-H7、竞争假设与证伪条件
- [G0-audit.md](mission-02/G0-audit.md)：对 Mission 01 的审计、可信计算基与差距分析
- [prior-art-map.md](mission-02/prior-art-map.md)：文献对照，分为"已有""可借鉴""尚不确定"三类
- [cognitive-domain-specs.md](mission-02/cognitive-domain-specs.md)：任务族、难度层级与证伪标准
- [primitive-candidates.md](mission-02/primitive-candidates.md)：原语发现过程、冻结的原语与被淘汰的候选
- [compositional-semantics.md](mission-02/compositional-semantics.md)：IR、时序代数、P1–P5 与证据等级划分
- [protocols/UNSEEN_PROTOCOL.md](mission-02/protocols/UNSEEN_PROTOCOL.md)：未见任务协议及其修正案
- [negative-results.md](mission-02/negative-results.md)：否定结果与具有欺骗性的成功
- [SCIENTIFIC_VERDICT.md](mission-02/SCIENTIFIC_VERDICT.md)：首轮科学判定、成本账本与下一轮假设
- `mission-02/experiments/unseen/SUMMARY.md`：由原始 JSON 自动生成的未见任务表格

Mission 03：

- [UNKNOWNNESS_AUDIT.md](mission-03/UNKNOWNNESS_AUDIT.md)：未知性审计、知识来源与泄漏图、泄漏假说的检验
- [COMPETING_HYPOTHESES.md](mission-03/COMPETING_HYPOTHESES.md)：四条机制层路线、两个零假说与路线选择
- [PRIOR_ART_EVIDENCE.md](mission-03/PRIOR_ART_EVIDENCE.md)：用于产生竞争假说的先前工作（每条标注核查状态）
- [CHALLENGE_PROTOCOL.md](mission-03/CHALLENGE_PROTOCOL.md)：挑战协议、锁定的预测与 10 个修正案
- [EXPLORATION_LEDGER.md](mission-03/EXPLORATION_LEDGER.md)：第 0–8 轮探索记录（观察、竞争解释、实验、反例、决策）
- [SCIENTIFIC_STATUS.md](mission-03/SCIENTIFIC_STATUS.md)：最终科学状态、成本账本与复现命令
- [OPEN_QUESTIONS.md](mission-03/OPEN_QUESTIONS.md)：各假说的最终状态与下一轮的鉴别实验
- [EVIDENCE_INDEX.md](mission-03/EVIDENCE_INDEX.md)：每条结论对应的脚本与原始输出

## 版本与冻结记录

开发环境的命令沙箱禁止写入 `.git/config`。经用户明确许可，所有 git 操作都在用户的终端面板中执行（不受沙箱限制）。Mission 02 起，每一轮都在独立分支上开发，完成后快进合并到 main，没有改写历史。

- **Mission 01**：提交历史按阶段记录，依次为工具链、A–C 组结果、冻结、D 组、最终评估。D 组的冻结点同时由 SHA-256 清单和一次提交标记。
- **Mission 02**（`mission-02` 分支）：原语与工具冻结（`b49a21a`，树哈希 `1c40ea5a…`，清单见 `mission-02/experiments/unseen/freeze-manifest.json`）；由冻结种子生成未见任务（`bccacf5`）；在任何裁判运行之前提交 A-LLM 程序（`c5dbafe`）；评测结果与科学判定（`b109e0e`）。
- **Mission 03**（`mission-03` 分支）：协议与预测的提交都早于相应实验。依次为未知性审计（`6922a75`）；竞争假说与锁定 P1 预测的挑战协议（`45a459a`）；修正案 1–6（`94747ea`、`63da6e7`、`2e53d15`）；先验封闭性实验的代码在观察任何持出任务之前冻结（`e6d80fa`）；ARC 协议（修正案 9）锁定于任何 ARC 工具与任务查看之前（`765de36`）；ARC 解算器冻结（`fa98aa8`，清单 `mission-03/experiments/arc/arc_freeze.json`）之后才运行持出集；最终状态（`d86db38` 及之后）。

## 许可

代码与文档以 [MIT License](LICENSE) 发布。`mission-03/external/arc-agi-1/` 中的 ARC-AGI-1 任务数据按其原许可 Apache-2.0 再分发，许可证原文随数据保留。
