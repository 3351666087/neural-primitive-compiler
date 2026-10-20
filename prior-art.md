# Prior Art（文献审计）

**核查标记**
- **[V]** 2026-10-20 通过网络检索核对了书目信息（作者、题目、出处），并核对了与本项目相关的核心结论摘要。
- **[V-]** 检索确认了论文存在与大意，但出处、作者顺序或具体定理未完全核实。
- **[M]** 来自我的已有知识，本轮未重新核对。这些都是领域内被广泛引用的标准文献，但引用前仍应查原文。

本文件只总结与本项目问题直接相关的结论，不复述论文内容。

---

## 1. Spiking Neural P Systems 及其形式化验证

| 文献 | 结论 | 与本项目的关系 |
|---|---|---|
| Ionescu, Păun, Yokomori, *Spiking Neural P Systems*, Fundamenta Informaticae 71(2–3):279–308, 2006 **[V]** | 将脉冲神经元引入膜计算；后续工作称这类系统计算普适（universality 来自无界脉冲计数/寄存器机模拟） | 普适性依赖**无界**状态。本项目的整数积分发放模型是**有界**的，因此是有限状态（theory.md 定理 1）。两者计算能力不同，不能把 SN P 的普适性结果移植过来 |
| Pérez Jiménez, Valencia Cabrera, Orellana Martín, Ramírez de Arellano Marrero, *Towards a general methodology for formal verification on spiking neural P systems*, TCS 1011:114705, 2024 **[V]** | 提出从 SN P 计算中提取可验证特征的方法论 | 同属"脉冲系统形式化验证"，但针对 SN P 的规则语义，不涉及从规格合成网络 |
| Gheorghe 等：SN P → kernel P 系统映射，再用现有工具做模型检测 **[V-]**；Event-B / SPIN / ProB 映射 **[V-]**；Ibarra 等 2009，基于转移图环路的不变式 **[V-]** | 把 SN P 翻译到成熟验证器 | 与我们"自写三个引擎并相互对拍"的做法相近；它们关注验证而不是合成 |
| **De Maria, Bahrami, L'Yvonnet, Felty, Gaffé, Ressouche, Grammont, *On the use of formal methods to model and verify neuronal archetypes*, Frontiers of Computer Science, 2022 [V]**（早期版本：De Maria, Muzy, Gaffé, Ressouche, Grammont, HSB 2016 **[M]**） | 用同步语言 Lustre 编码六种"神经原型"（简单串联、多输出串联、并联、负反馈环、行为抑制、对侧抑制），用 Kind2 模型检测时序性质，并用 Coq 证明参数化性质；文中指出模型检测只对给定参数区间和有限输入有效 | **最接近的先行工作**："小神经回路 + 时序性质 + 形式验证"已经存在。本项目在这一点上**没有新颖性**。我们的差异只在于加入了从规格出发的合成（CEGIS/枚举）以及对可实现性边界的刻画 |
| 2024 年一项用 NuSMV 对 LIF 神经原型做 CTL/LTL 验证的框架 **[V-]**；Pham, De Maria, De Simone 的自动化流水线 **[V-]** | 同一路线的自动化 | 同上 |
| Banerjee, Ghosh, Banerjee, Mohalik, *SMT-Based Modeling and Verification of Spiking Neural Networks: A Case Study*, VMCAI 2023 **[V]**；Seong, Kim, Ko, *Towards Efficient Formal Verification of Spiking Neural Network*, arXiv 2408.10900, 2024 **[V]** | 用 Z3（线性实数算术）编码 SNN，验证已训练网络的鲁棒性 | 证明"SNN 的 SMT 编码"已有先例；它们验证已训练的分类器，而不做规格到网络的合成 |
| Narodytska 等，二值神经网络的 SAT 验证，AAAI 2018 **[M]**；Katz 等，Reluplex，CAV 2017 **[M]** | 离散/分段线性网络的 SAT/SMT 验证 | 我们的编码技巧（脉冲为布尔量，因此 `w·s = If(s, w, 0)` 是线性的）属于这条线上的常规做法 |

## 2. 神经程序综合与模块化神经网络

| 文献 | 结论 | 关系 |
|---|---|---|
| **Lindner, Kramár, Farquhar, Rahtz, McGrath, Mikulik, *Tracr: Compiled Transformers as a Laboratory for Interpretability*, NeurIPS 2023 [V]**；Weiss, Goldberg, Yahav, *Thinking Like Transformers* (RASP), ICML 2021 **[M]** | 把 RASP 程序**编译**为 Transformer 权重，不经训练 | "由规格/程序直接编译出网络、无需训练"在 Transformer 上已经实现。本项目的"编译"同样不新 |
| **Neftci, Binas, Rutishauser, Chicca, Indiveri, Douglas, *Synthesizing cognition in neuromorphic electronic systems*, PNAS 110(37):E3468–E3476, 2013 [V]**；Rutishauser & Douglas, Neural Computation 2009 **[M]** | 把行为任务写成状态机，经 soft winner-take-all 中间层映射到脉冲硬件 | **"FSM → 脉冲网络"的综合已有先例**，而且是在真实硬件上。我们的经典构造（fsm.py）是同一思想在理想离散模型上的版本 |
| Aimone, Severa, Vineyard, *Composing Neural Algorithms with Fugu*, arXiv 1905.12130, 2019 **[V]** | 用 "bricks"（封装的脉冲算法）和 "scaffold"（计算图）组合脉冲算法，并编译到多种后端 | 与本项目的"原语 + DSL 组合"高度相似。差异：Fugu 不要求每个 brick 带可机器检查的合同 |
| Amir 等, *Cognitive Computing Programming Paradigm: A Corelet Language for Composing Networks of Neurosynaptic Cores*, IJCNN 2013 **[V]** | 面向 TrueNorth 的可嵌套组合语言（corelet），带可复用库 | 组合式神经编程语言已有工业先例 |
| Eliasmith & Anderson, *Neural Engineering*, 2003 **[M]**；Nengo (Bekolay 等, 2014) **[M]** | NEF 把函数和动力学"编译"进脉冲群体（用最小二乘求解码器，属于优化而非梯度训练） | 连续/统计意义上的"规格到脉冲网络"编译的主流框架；它不提供形式化保证 |
| Andreas, Rohrbach, Darrell, Klein, *Neural Module Networks*, CVPR 2016 **[M]** | 按问题结构组装可复用的神经模块（模块本身需要训练） | 原语组合的思想来源之一；NMN 的模块没有形式合同 |
| Reed & de Freitas, NPI, ICLR 2016；Balog 等, DeepCoder, ICLR 2017；Ellis 等, DreamCoder, PLDI 2021；Graves 等, NTM 2014 / DNC 2016 **[M]** | 用神经网络辅助或学习程序 | 是"神经网络做综合"，而本项目是"综合神经网络"，方向相反 |
| Romera-Paredes 等, FunSearch, Nature 2024；Wu, Barrett, Narodytska, Lemur, ICLR 2024 **[M]** | LLM 提出候选，由评估器或验证器裁决 | Phase 4 的"LLM 提议 / 验证器裁决"分工完全沿用这一范式 |

## 3. 自动机综合、SMT/CEGIS 与组合式验证

| 文献 | 结论 | 关系 |
|---|---|---|
| Büchi & Landweber 1969；Pnueli & Rosner, POPL 1989；Finkbeiner & Schewe, *Bounded Synthesis*, STTT 2013 **[M]** | 反应式综合的可判定性与复杂度；有界综合按实现规模递增搜索 | 我们"逐个增加神经元数"的搜索就是有界综合在本模型上的翻版 |
| Solar-Lezama 等, *Combinatorial Sketching for Finite Programs*, ASPLOS 2006 **[M]**；Alur 等, *Syntax-Guided Synthesis*, FMCAD 2013 **[M]** | CEGIS 与草图（sketch）综合；SyGuS 框架 | synth.py 中的 `cegis` 和 `sketch` 直接沿用 |
| Udupa 等, *TRANSIT: Specifying Protocols with Concolic Snippets*, PLDI 2013 **[V]**（书目已核；"观察等价剪枝"归属于它出自记忆 **[M]**）；Albarghouthi, Gulwani, Kincaid, *Recursive Program Synthesis*, CAV 2013 **[M]** | 枚举式综合中的观察等价剪枝 | `compose_dag` 使用这一技术。开发中我们发现并修复了一个它引入的漏判错误（见 evidence-ledger E-dev-1） |
| Heule & Verwer, 用 SAT 精确识别 DFA, ICGI 2010 **[M]** | 最小自动机识别的 SAT 编码 | 与"最少神经元网络"的 UNSAT 下界证明属同类 |
| Biere, Cimatti, Clarke, Zhu, BMC, TACAS 1999；Sheeran, Singh, Stålmarck, k-induction, FMCAD 2000；Kroening & Strichman, 完备性阈值/递归直径, VMCAI 2003 **[M]** | 有界模型检测，以及它何时能升级为完全证明 | 我们严格区分 VERIFIED_BOUNDED 和 VERIFIED_UNBOUNDED；后者来自完整的显式状态搜索 |
| de Moura & Bjørner, Z3, TACAS 2008 **[M]** | SMT 求解器 | 本机 Apple Silicon 上 z3-solver 5.3.1 运行正常（未遇到依赖问题） |
| Havelund & Roşu, *Synthesizing Monitors for Safety Properties*, TACAS 2002 **[M]** | 过去时 LTL 的增量监视器（每个子公式一个状态比特） | `spec.Monitor` 的实现方式 |
| **Abadi & Lamport, *Conjoining Specifications*, TOPLAS 17(3):507–534, 1995 [V]**（SRC RR-118, 1993）；Misra & Chandy 1981；McMillan 1999 **[M]**；Benveniste 等, *Contracts for System Design*, 2018 **[M]** | 假设–保证推理；Abadi–Lamport 要求保证比假设"多成立一步"，从而使循环推理可靠 | compose.py 的 strict 合同模式就是这一条件；所有延迟 ≥ 1 恰好让循环（反馈）组合的归纳论证成立 |
| Lustre（Halbwachs 等 1991）与 Kind 2 **[M]** | 同步数据流语言与模型检测器 | 本项目的时间语义与同步语言相同；DSL 可以视为一个极小的同步语言 |

## 4. 神经计算的普适性与复杂度

| 文献 | 结论 | 关系 |
|---|---|---|
| McCulloch & Pitts 1943；Kleene, *Representation of Events in Nerve Nets and Finite Automata*, 1956；Minsky, *Computation: Finite and Infinite Machines*, 1967 **[M]** | 有限阈值单元网络 ≡ 有限自动机（正则事件） | 定理 1、定理 2 就是这些结果在本模型（整数电位、泄漏、延迟 ≥ 1）上的重述，**不新** |
| **Alon, Dewdney, Ott, *Efficient Simulation of Finite Automata by Neural Nets*, JACM 1991 [V]** | m 状态自动机所需神经元数 K(m)：下界 Ω((m log m)^{1/3})，构造上界 O(m^{3/4}) | 我们的 one-hot 构造用 O(m·2^|输入|) 个神经元，远非最优；最优构造的存在说明"神经元数"作为代价度量很依赖构造方式 |
| **Horne & Hush, *Bounds on the Complexity of Recurrent Neural Network Implementations of Finite State Machines*, NIPS 6, 1993 [V]** | 无限制时 O(√m) 个节点；权重限于 {−1,1} 时 O(√(m log m))；扇入限于 2 时 O(m)；在一定假设下有匹配下界 | 同上 |
| Indyk, *Optimal Simulation of Automata by Neural Nets*, STACS 1995, LNCS 900:337–348 **[V]**（书目已核；"Θ(√m) 最优"这一结论出自引用它的论文，未在原文核实） | 最优模拟 | 同上 |
| Siegelmann & Sontag, JCSS 1995 **[M]**；Maass 1996/1997 **[M]** | 有理数权重 RNN 图灵完备（需要无界精度）；脉冲网络的计算能力 | 依赖无界精度或无界时间编码；本模型显式禁止 |
| **Šíma & Orponen, *General-Purpose Computation with Neural Networks: A Survey of Complexity Theoretic Results*, Neural Computation 15(12):2727–2778, 2003 [V]** | 按离散/连续、前馈/循环等维度梳理复杂度结果 | 定理 4 中的复杂度结论属于这份综述覆盖的标准类型 |
| 简洁图可达性的 PSPACE 完全性：Galperin & Wigderson 1983；Papadimitriou & Yannakakis 1986；Lozano & Balcázar 1990；Balcázar, Lozano, Torán 1992 **[V-]** | 电路描述的图上可达性是 PSPACE 完全的 | 用于无界验证的 PSPACE 下界（theory.md 定理 4b；我们另给出直接归约草图） |
| Smith, *(Newtonian) Space-Time Algebra*, arXiv 2001.04242；*Research Agenda: Spacetime Computation and the Neocortex*, IEEE Micro 2017 **[V]**；Madhavan, Sherwood, Strukov, Race Logic, ISCA 2014 **[M]** | 以脉冲时刻编码值的计算代数 | 与 Q2"时间是否带来表达优势"直接相关：时间编码改变的是**表示与代价**，不改变可计算类 |
| Muroga, *Threshold Logic*, 1971；Parberry, *Circuit Complexity and Neural Networks*, 1994；Pfleeger 1973（不完全确定 FSM 最小化 NP 完全）**[M]** | 阈值逻辑与电路复杂度 | 定理 3 的单调性论证属于阈值函数的基本性质 |

## 5. 神经发育程序与架构生成

| 文献 | 结论 | 关系 |
|---|---|---|
| **Najarro, Sudhakaran, Risi, *Towards Self-Assembling Artificial Neural Networks through Neural Developmental Programs*, ALIFE 2023 [V]** | 用一个只做局部通信的"发育程序"生长网络，再用进化/强化/监督方法优化 | 架构由程序生成，但发育程序本身仍需优化，也没有形式保证 |
| **Gaier & Ha, *Weight Agnostic Neural Networks*, NeurIPS 2019 [V]** | 搜索架构，使其在共享随机权重下也能完成任务，无需逐权重训练 | **"不做任务级权重训练"已有先例**。WANN 的代价是架构搜索；我们的代价是约束求解。两者都把"训练"换成了"搜索" |
| Stanley & Miikkulainen, NEAT, 2002；Stanley, D'Ambrosio, Gauci, HyperNEAT, 2009；Mordvintsev 等, Neural Cellular Automata, Distill 2020 **[M]** | 神经进化与间接编码 | 都是统计优化，不提供可验证合同 |

---

## 新颖性审计（逐项对照）

| 本项目组件 | 最接近的先行工作 | 我们的差异（如有） |
|---|---|---|
| 整数 IF 语义 + 模拟器 | 同步语言、Loihi 类离散神经元、Lustre 神经原型 | 无实质新颖性 |
| 时序规格语言（过去时 LTL + 计数） | ptLTL 监视器文献 | 无；`modcount` 和窗口计数是为表达计数器合同加入的便利算子 |
| 原语 + 合同 + 验证 | De Maria 等的神经原型、Fugu bricks、Corelet | 合同由机器在无界意义上检查，并有"名称不能作为证据"的反例测试；方法本身不新 |
| SMT/BMC + 显式状态可达性 | 标准模型检测 | 三引擎互相对拍属于工程纪律，不是新方法 |
| CEGIS / 草图 / 枚举综合 | Sketch、SyGuS、TRANSIT | 应用到这一神经基底上；方法不新 |
| 经典 FSM → 网络构造 | Kleene、Minsky、Neftci 等 2013 | 适配到"所有延迟 ≥ 1"的模型；不新 |
| **延迟 1 的精确可实现性刻画（定理 3）** | 阈值函数单调性（经典） | 我们在有限的检索中**没有找到**针对"严格因果整数 IF 网络"的这一显式陈述，但它是经典事实的直接推论。我们**不声称**它是新定理，只声称它可以机器检查，并且与搜索结果一致 |
| 组合验证（strict 合同 + 反馈） | Abadi–Lamport 1995 | 无理论新颖性；实验给出的是对其收益的**否定性**测量（H4） |

**结论**：本项目的价值不在新方法，而在于把一条研究路线放进可复现、可证伪的实验框架中，并定位它在哪里成立、在哪里遇到真正的困难。
