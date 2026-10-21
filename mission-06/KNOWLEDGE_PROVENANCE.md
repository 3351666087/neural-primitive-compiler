# Mission 06 知识来源账（初版，Gate 0/1）

每一项知识的来源都记为以下之一：设计者（本会话或此前的 LLM 会话，含预训练知识）、第三方（环境作者的公开文档）、证据（由实验产生）。成本栏记录代码行数或人工 / LLM 设计成本；未知时写 UNKNOWN，不记为零。

## 1. 从 Mission 05 继承的知识（全部由设计者写入）

| 知识 | 位置 | 来源 | 证据等级（G0 审计后） |
|---|---|---|---|
| LINE 环境语义（裁判侧） | `mission-05/experiments/judge/env.py` | 设计者 | 定义 |
| 宏模型：选择规则、交换搬运、可满足性 | `lib/model.py`、`g3/dsl.py` | 设计者 | 与环境 + 编译出的选择一致：G0-M1 [M/E] |
| ACH-DSL 的语言（类型、区域、pick） | `g3/dsl.py` | 设计者 | 定义 |
| 交换引理 | 修正案 3 | 设计者，手证 | [P]（手证），G0-M1 检验其在环境中的实现 |
| 适用性引理（"达成器总能移动"） | 修正案 3 称其为 [P]，但无书面证明 | 设计者 | Mission 05 实为 [M]（N ≤ 7 的宏模型穷举）。G0 的 APP-R 给出机械化的松弛证明，或给出反例 |
| Z3 损伤、保持、下降的编码 | `g3/z3_dsl.py`、`r7/zplus.py`、`r8/zpp.py` | 设计者 | [P]，相对于编码本身；编码与宏模型的一致性 [M]（N ≤ 7） |
| 势函数文法、规则文法（B 的假设空间） | `lib/potentials.py`、`lib/brule.py` 等 | 设计者 | 定义（B 在其内学习） |
| CIR、编译模板（OR、AND、ATLEAST、CMR） | `lib/compile_cir.py`、`src/cog/prims.py` | 设计者（Mission 02 冻结） | T-K：类 C_K 上 [P]（手证 + Z3 引理 + 逐网络前提检查） |
| 目标池（98 个开发目标） | `pilots/run_pa3.py` | 设计者 | 定义 |
| G3、G4 的持出达成器 | `external/g3_heldout`、`g4_heldout` | 隔离的 LLM 会话（同一模型家族） | 已用过；此后只作 POST-HOC 审计 |

## 2. Mission 06 新写入的知识

| 知识 | 位置 | 来源 | 成本 | 备注 |
|---|---|---|---|---|
| APP-R 的松弛编码（区间类、计数、见证、窗口的必要条件） | `experiments/g0/app_r.py` | 设计者（本会话） | 约 330 行；开发约 1 小时墙钟（只用新随机规格） | 修正案 G0-1 记录了从开发中加入的窗口约束；它们是领域专用的必要条件，不是通用方法 |
| 编译器定理 T-K 与前提检查 | `COMPILER_THEOREM.md`、`experiments/g0/compile_*.py` | 设计者（本会话） | 约 600 行 | 手证部分未经机器检查 |
| 环境事实（安装、许可、条款、任务结构） | `ENVIRONMENT_SELECTION.md` | 第三方官方文档 | — | 只读文档、公开卡片与镜像元数据 |
| 外部环境的预训练知识 | — | 本会话的预训练（WorkArena 2024、WorkArena++ 2024、ALFWorld 2020 均公开） | UNKNOWN | 本会话可能知道任务类型、PDDL 域与常见解法。凡由本会话写入的外部技能、检测器、适配器规则，都记为"设计者 / 预训练先验"，不记为"由证据发现" |
| ALFWorld 文本观察的措辞、动作语义、目标句式（P-ALF-1 的信念判定器） | `experiments/g1/belief.py` | 设计者（本会话对 ALFWorld 的预训练知识）；未对照官方文法文件核实 | 约 150 行 | 判定规则可能与环境的真实语义不符，W_P 正是对它的检验；例如"冷却是否要求冰箱关着"未知 |
| BrowserGym 观察键白名单、隔离边界 | `experiments/g1/harness.py` | 第三方文档（BrowserGym README）+ 设计者 | 约 120 行 | P3 实测：白名单恰好等于 BrowserGym 的全部观察键 |

| AppWorld 的接口与数据流（裁判包装、观察白名单） | `experiments/aw/aw_judge.py` | 第三方文档（README、PyPI、公开源码中的常量）+ 接口内省（只打印签名与字段名） | 约 120 行 | 没有阅读应用实现、评测测试或任何测试任务 |
| AppWorld 的预训练知识 | — | 本会话的预训练可能包含 AppWorld 论文（2024）、网站与公开 API 文档 | UNKNOWN | 任务内容加密分发；测试解法不公开 |

## 3. Gate 2–4 登记（ALFWorld 构造器、发现与基线）

| 知识 | 位置 | 来源 | 成本 | 证据等级 |
|---|---|---|---|---|
| 目标解析器（10 条句式 → 6 种目标形式）、原子 IN / IN2 / CLEAN / HEAT / COOL / HOLDING / LIT | `experiments/g2/alf_core.py` | 设计者（预训练中关于 ALFWorld 目标句式的知识），未查阅游戏文件 | 约 60 行 | 定义；60/60 开发局解析成功（G2） |
| 达成器宏（取得、放入、处理、开灯）与"两两保持"表 | 同上 | 设计者 | 约 120 行 | 合同为公理 [AX]：没有证明，也没有有界检查 |
| "一个容器一个位置"（隐含在信念更新与 `go to` 的监控中） | `experiments/g1/belief.py`、`alf_core.py` | 设计者的隐性先验 | 0 行（隐含） | **错误**：P-ALF-1 的反例、G2-ALF 的 23 次监控弃权 |
| 同址规律 L_co | `experiments/g3/g3_core.py` | **证据**：B 的区分实验（20 个发现局，11/11 支持，0 矛盾）。竞争假说 H_co / H_un / H_noise 与探针 `examine` 由设计者写定 | 102 行（G3 全部改动） | [E] |
| 位置先验 P_loc（53 种物体类型，391 次目击） | `experiments/g3/g3_discovery.json` | **证据**：发现局中观察到的列举句计数 | 456 步交互 | [E] |
| 恢复（操作反馈不符时重发 ≤ 2 次） | `experiments/g4/g4_core.py` | 设计者；只在开发局（训练集）上开发 | 45 行 | 定义 |
| 非确定执行的扰动（操作以 0.2 的概率无效） | `experiments/g4/perturb.py` | 设计者（裁判侧），模仿环境对无效命令的回复 | 约 20 行 | 定义 |
| B2 提示词 | `experiments/b2/B2_PROMPT_ALF.txt`（SHA-256 前 16 位 730b9697d40f4cad） | 设计者 | 1,875 字符 | G1 起逐字不变 |
| B2 的知识 | Opus 5.5 的预训练 | 预训练（ALFWorld 2020 公开；可能见过任务与解法） | UNKNOWN | 污染风险无法排除；B2 与设计者是同一模型 |

**设计者代码合计（ALFWorld 构造器）：** 信念 157 行 + 核心 239 行 + G3 102 行 + G4 45 行 = 543 行。其中由证据产生、而不是由设计者写定的知识只有 L_co 的采纳与 P_loc 的计数。

## 4. AppWorld 的登记

- `experiments/aw/p_aw0.py`、`experiments/g4/aw_profile.py`：裁判侧测量，读取公开的开发集解法与各分割的 `answer.json`、`metadata.json`，只输出聚合量。不作为任何构造器的输入。
- AppWorld 上没有构造器：引理 X1（预注册 §G4.5）说明冻结核心的目标语言表达不了其任务。
