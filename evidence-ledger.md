# Evidence Ledger

每条证据给出：可复现的出处（测试、命令或原始 JSON），证据类型，以及适用范围。

**证据类型**
- **[机器检查]**：本仓库工具实际执行验证得到的结论。
- **[纸面]**：theory.md 中的论证，未经过证明助手检查。
- **[实验]**：在本机测得的数值。单次运行，计时有波动。

所有原始数据位于 `experiments/results/*.json`、`experiments/llm_sketches/abc_results.json` 和 `experiments/D_unseen/results.json`。

<!-- SECTIONS BELOW ARE FILLED IN AS EVIDENCE ARRIVES -->

## 1. 语义与验证基础设施

| ID | 结论 | 证据 | 类型 / 范围 |
|---|---|---|---|
| E-S1 | 同一输入序列产生同一输出；结果与神经元顺序无关 | `tests/test_semantics.py::test_determinism_and_order_independence`（60 个随机网络，随机排列） | [机器检查]，随机样本 |
| E-S2 | 严格因果：t 时刻及以前的脉冲不依赖 ≥ t 的输入 | `test_strict_causality` | [机器检查]，随机样本 |
| E-S3 | 电位始终处在声明的范围内；从静息出发时具有时移不变性 | `test_potentials_stay_in_declared_range`、`test_time_shift_invariance_from_rest` | [机器检查] |
| E-S4 | 三个模拟器（参考解释器、numpy 批量、有限状态步进）逐脉冲一致 | `test_three_simulators_agree` | [机器检查] |
| E-S5 | 三个规格求值器（numpy、增量监视器、Z3 编码）一致；打印后再解析可还原原公式 | `tests/test_spec.py`（150 + 150 + 80 个随机公式） | [机器检查] |
| E-S6 | 三个验证引擎在 300 个随机（网络, 规格）上从不矛盾：241 个反例、34 个无界证明，另有 25 个在有界意义下通过、却在无界意义下被反驳 | `tests/test_verify.py::test_engines_agree_on_random_problems` 及开发期的 300 例统计 | [机器检查]；那 25 例直接说明了为什么不能把有界验证当作无界证明 |
| E-S7 | 每个引擎报告的反例都经参考解释器回放确认；有界通过 ≠ 无界通过（5 级计数器例子） | `test_wrong_spec_gives_replayable_counterexamples`、`test_bounded_verification_is_not_unbounded` | [机器检查] |
| E-S8 | 资源上限和超时以 RESOURCE_LIMIT / TIMEOUT 报告，从不算作通过 | `test_resource_limits_are_reported_not_hidden`、`test_bmc_timeout_is_not_a_proof` | [机器检查] |
| E-S9 | Z3 5.3.1 在 Apple M4（arm64）、Python 3.12 上安装运行正常，没有依赖问题 | `make install` 输出 | 环境事实 |

## 2. 原语与 DSL

| ID | 结论 | 证据 | 类型 / 范围 |
|---|---|---|---|
| E-P1 | 13 个原语的合同全部通过无界验证，BMC(10) 也一致 | `tests/test_primitives.py`（45 个参数实例） | [机器检查]，**仅参数网格内**（例如 counter 只到 k ≤ 6） |
| E-P2 | **名称不是证据**：`pairdet` 的直觉合同 `out <-> prev(in & prev(in))` 被反例 `in = 1,1,1,0` 驳倒；真实合同带自引用 `!out` | `test_name_is_not_evidence_pairdet` | [机器检查] |
| E-P3 | `latch_lite` 只在假设 `!(set & rst)` 下正确；去掉假设即得反例 | `test_latch_lite_needs_its_assumption` | [机器检查] |
| E-P4 | `counter` 的正确性依赖电位下限 vmin = 0；把下限改成 −3 后合同被驳倒（组合限制来自语义，而不是名称） | `test_counter_depends_on_its_floor` | [机器检查] |
| E-P5 | 没有合同的原语被 DSL 拒绝；参数算术无法逃逸到宿主语言（`__import__`、属性访问、`**` 等均被拒绝） | `test_primitive_without_contract_is_rejected`、`test_parameter_arithmetic_has_no_escape_hatch` | [机器检查] |
| E-P6 | 组合错误（端口未连接、未知原语、输出直连输入、零延迟）都在展平阶段被拒绝 | `tests/test_dsl.py` | [机器检查] |

## 3. 理论与搜索的一致性

| ID | 结论 | 证据 | 类型 / 范围 |
|---|---|---|---|
| E-T1 | 经典构造（定理 2）在随机函数式规格上，凡编译成功的都通过了无界验证 | `test_classical_construction_is_correct_or_provably_impossible` | [机器检查]，随机样本 |
| E-T2 | 凡定理 3 判定为不可实现的，1 神经元 CEGIS 也返回 UNSAT（无矛盾） | 同上；`test_unrealizable_agrees_with_theorem3`（奇偶校验，n = 1, 2） | [机器检查] + [纸面] |
| E-T3 | 延迟 1 的奇偶校验不可实现，见证为两段历史：空历史后输出随 a 递增，历史 `[1]` 后随 a 递减 | `npc realize examples/parity_latency1.npc --spec parity_latency1` | [纸面] 定理 3（任意规模）+ [机器检查] 见证 |
| E-T4 | 组合验证的结论从不与单体验证矛盾（40 个随机组合，含环）；假设无法消解时返回 UNKNOWN | `tests/test_compose.py` | [机器检查] |

## 4. 开发过程中发现的问题（如实记录）

| ID | 问题 | 处理 |
|---|---|---|
| E-dev-1 | `compose_dag` 的观察等价剪枝有漏判：一个候选若在样例上恰好全零，就与"静默信号"等价而被剪掉，但静默信号从未作为输出检查过规格。结果是 `counter(k=3)[a,r]` 被错过，搜索报告 EXHAUSTED（**一个错误的"穷尽"结论**） | 已修复（对每个新信号先检查规格，再去重），并加入回归测试 `test_compose_dag_regression_silent_signal`。教训：EXHAUSTED/UNREALIZABLE 这类"否定"结论同样依赖实现的正确性 |
| E-dev-2 | 写 C1 草图时发现 DSL 不支持在原语**类型**上留选择洞（`?{latch, latch_lite}`） | 在冻结前加入此功能，并补测试 `test_primitive_type_choice_hole` |
| E-dev-3 | 早期 `Result.summary` 对反例也打印"every length (finite-state proof)"这一范围描述，容易被误读 | 改为"spec refuted by a concrete input trace" |
