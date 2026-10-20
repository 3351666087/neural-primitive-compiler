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
> 真正的困难不在"能不能"，而在**规模**：合成是 Σ₂ᴾ 难的，验证是 PSPACE 难的；精确合同的组合推理不能消除状态爆炸；时间动力学换来的是神经元数量上的简洁，而不是新的计算能力。
> 现有证据**不支持**把这条路线外推到更广泛的智能功能。

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

## 文档

- [prior-art.md](prior-art.md)：文献审计与新颖性对照（每条引用都标了核查状态）
- [research-hypotheses.md](research-hypotheses.md)：实验前写下的假设 H1–H8 与证伪条件
- [theory.md](theory.md)：形式语义、定理 1–5 及证明，以及"什么被证明了、以什么方式"
- [evidence-ledger.md](evidence-ledger.md)：逐条证据、对假设的判定，以及 Phase 6 的六个问题
- [limitations.md](limitations.md)：限制与偏差
- `experiments/results/SUMMARY_ABC.md`、`experiments/results/HYPOTHESES_CHECK.md`、`experiments/D_unseen/SUMMARY.md`：由原始 JSON 自动生成的表格

## 关于 Git

开发环境的命令沙箱禁止写入 `.git/config`。获得用户明确许可后，所有 git 操作改在用户的终端面板中执行（不受沙箱限制）。提交历史按阶段记录：工具链 → A–C 结果 → 冻结 → D 组 → 最终评估。D 组的冻结点同时由 SHA-256 清单和一次提交标记。
