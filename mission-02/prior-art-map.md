# Prior-Art Map（Mission 02）

**核查标记**：**[V]** 2026-10-20 网络检索核对了书目和核心结论；**[V-]** 存在性已核对，细节（会议、页码）未完全核对；**[M]** 来自已有知识，本轮未重新核对。Mission 01 已核对的条目见 `../prior-art.md`。

**分类**：**已有**（本项目做的事已被他人做过）、**可借鉴**（方法可以直接采用）、**尚不确定**（与本项目问题相关但结论未定）。

| 领域 | 文献 | 与 Mission 02 的关系 | 分类 |
|---|---|---|---|
| 程序综合 / 库学习 | Ellis 等, *DreamCoder: Growing generalizable, interpretable knowledge with wake-sleep Bayesian program learning*, arXiv 2006.08381（2020）**[V-]**（发表会议：常见引用为 PLDI 2021，检索中有一个来源写作 Phil. Trans. R. Soc. A，未核实） | 通过压缩已解程序来学习 DSL 原语，包括绘图领域 | **已有**：我们"从实现中压缩出原语"正是这条路线；我们的规模小得多 |
| | Bowers, Olausson, Wong, Grand, Tenenbaum, Ellis, Solar-Lezama, *Top-Down Synthesis for Library Learning*（Stitch），POPL 2023 **[V]** | 基于压缩度（MDL）的快速抽象学习 | **可借鉴**：我们的"描述长度"度量沿用这一视角 |
| | Cao, Kunkel, Nandi, Willsey, Tatlock, Polikarpova, *babble: Learning Better Abstractions with E-Graphs and Anti-unification*, POPL 2023（PACMPL 7, Art. 14）**[V]** | 反统一 + 等价理论下的库学习 | **可借鉴**：`cog.auto` 中的命令族抽象是一种极简的反统一 |
| | Grand 等, *LILO: Learning Interpretable Libraries by Compressing and Documenting Code*, ICLR 2024 **[V]** | LLM 提议 + Stitch 压缩 + 自动命名 | **已有**："LLM 提议 / 符号压缩"的分工 |
| | Plotkin 1970 "A note on inductive generalization"；Reynolds 1970 **[M]** | 反统一的经典定义 | **已有** |
| 神经模块网络 | Andreas, Rohrbach, Darrell, Klein, *Neural Module Networks*, CVPR 2016 **[M]** | 按问题结构组装模块（模块需要训练） | **已有**：组合思想；区别在于我们的模块权重冻结、合同可验证 |
| 神经电路综合 | Neftci 等 PNAS 2013 **[V]**；Fugu（Aimone 等 2019）**[V]**；Corelet（Amir 等 2013）**[V]**；NEF / Nengo **[M]**（见 Mission 01 prior-art） | FSM → 脉冲网络；可组合的脉冲"砖块" | **已有** |
| 假设–保证合同 | Abadi & Lamport TOPLAS 1995 **[V]**；Benveniste 等, *Contracts for System Design* 2018 **[M]** | 循环推理的可靠性条件 | **已有**；我们的 P4 是这一框架的实例 |
| 参数化验证 | Emerson & Namjoshi, *Reasoning about Rings*, POPL 1995（IJFCS 2003 扩展版）**[V]**；Apt & Kozen 1986（参数化验证一般不可判定）**[M]** | cutoff：任意规模的问题归约到有限规模 | **可借鉴**：我们用"未解释坐标类型 + 量词"的 Z3 证明代替 cutoff；这属于一类特殊的局部性论证，**尚不确定**能推广多远 |
| 组合泛化 | Lake & Baroni, *Generalization without Systematicity*, ICML 2018（SCAN）**[V]**；Hupkes, Dankers, Mul, Bruni, *Compositionality Decomposed*, JAIR 2020 **[V]**；Kim & Linzen, COGS, EMNLP 2020 **[M]** | 学习型网络在系统组合上的失败与测试分类 | **可借鉴**：我们的 L3 测试（新组合、新尺寸、新身份）对应 Hupkes 等的 systematicity / productivity / substitutivity |
| 变量绑定 | Smolensky, *Tensor Product Variable Binding…*, Artificial Intelligence 46:159–216, 1990 **[V]**；Plate HRR 1995 **[M]**；Kleyko, Rachkovskij, Osipov, Rahimi, VSA 综述 Part I/II, ACM Computing Surveys 2022/2023 **[V]**；Greff, van Steenkiste, Schmidhuber, *On the Binding Problem in Artificial Neural Networks*, arXiv 2012.05208 **[V]** | 乘积（张量）绑定与叠加的干扰问题 | **已有**：我们的"对象 × 值"one-hot 表就是 TPR 的局部化特例；叠加编码的失败是已知结论（E1 只是校准） |
| 等变性 | Ravanbakhsh, Schneider, Póczos, *Equivariance Through Parameter-Sharing*, ICML 2017 **[V]**；Cohen & Welling G-CNN 2016 **[M]** | 参数（权重）的对称性 ⇔ 群等变 | **已有**：我们的"布线自同构 ⇒ 等变"引理是这一结论在脉冲网络上的直接版本，**不新** |
| 神经–符号推理 | Garcez & Lamb, *Neurosymbolic AI: the 3rd wave*, 2023 **[M]**；DeepProbLog（Manhaeve 等 2018）**[M]** | 符号结构与神经实现的结合 | **尚不确定**：这些框架里的神经部分通常需要训练 |
| 架构发育 | Najarro, Sudhakaran, Risi, NDP, ALIFE 2023 **[V]**；Gaier & Ha WANN, NeurIPS 2019 **[V]**；HyperNEAT **[M]** | 由程序或搜索生成网络结构，不逐个训练权重 | **已有**："不训练权重、改为搜索结构" |
| 智能的度量 | Chollet, *On the Measure of Intelligence*, arXiv 1911.01547, 2019（ARC）**[V]** | 智能 = 技能获取效率；ARC 是一个程序综合式基准 | **尚不确定**：我们的空间任务族与 ARC 的网格变换同类，但规模和开放性都小得多 |

**定位**：Mission 02 的组成部分（类型化索引空间、乘积编码、置换/坐标映射路由、反统一的库学习、参数化合同）各自都**有先例**。可能的增量只在于：把它们放在同一个可执行、可验证的脉冲基底上，并对"未见任务的严格直接构造"做冻结后的检验。
