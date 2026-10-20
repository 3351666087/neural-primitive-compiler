# Mission 03 先前工作对照（用于产生竞争假说，不是综述）

**核查状态**：[V] 本轮用网络检索核对了作者、题目、出处与主要结论（只读摘要与书目信息，未必读过全文）；[V-M2] 已在 `mission-02/prior-art-map.md` 中核对；[S] 只有二手来源确认，引用前需核对原文。
**分类**：**已有**（问题已被解决或刻画，本研究不能宣称新）；**可借鉴**（提供方法或判据）；**尚不确定**（与本研究问题的关系仍是开放的）。

## 1. 从范例或行为归纳机制（H-A）

| 工作 | 结论与实验条件 | 对本研究的意义 | 分类 | 核查 |
|---|---|---|---|---|
| Gold, *Complexity of automaton identification from given data*, Information and Control 37(3):302–320, 1978 | 给定有限观测，判定是否存在至多 k 个状态的一致 DFA 是 NP 完全的 | 被动数据下的机制识别在最坏情况下是难的；A0 零假说的理论来源 | 已有 | [V]（结论经二手来源确认，[S]） |
| Angluin, *Learning regular sets from queries and counterexamples*, Information and Computation 75(2):87–106, 1987 | 有成员查询与等价查询（反例）时，DFA 可在多项式时间内学会 | Mission 02 的单格探测相当于成员查询；L3 表明在本域它不是必要的 | 已有 | [V] |
| Rivest & Schapire, *Inference of finite automata using homing sequences*, Information and Computation 103(2):299–347, 1993 | 不能重置时用归航序列学习自动机；仍需教师给出反例 | H-D（不可重置、部分可观测）的已知理论基础 | 已有 | [V] |
| Alur, Radhakrishna, Udupa, *Scaling enumerative program synthesis via divide and conquer*（EUSolver），TACAS 2017 | 先枚举在部分输入上正确的项，再用决策树学习区分它们的谓词；赢得 SyGuS 2016、2017 一般赛道 | 条件命令的"守卫 + 分支"解释正是这一方法；它是 H-A 的强符号基线 | 可借鉴（基线） | [V] |
| Cropper & Morel, *Learning programs by learning from failures*（Popper），Machine Learning 110:801–856, 2021 | ILP：生成、测试、由失败产生约束；能学递归程序 | 关系规则与递归（不动点）的强符号基线；H-C、H-A 的对照 | 可借鉴（基线） | [V] |
| Ellis et al., DreamCoder（arXiv 2006.08381；PLDI 2021 版本题目不同，待核对） | 唤醒–睡眠交替的程序归纳与库学习，在多个领域重新发现可复用概念 | 库学习是"从证据中长出原语"的已有路线；本研究必须与它区分 | 已有 / 可借鉴 | [V-M2]，出处细节 [S] |
| Kemp & Tenenbaum, *The discovery of structural form*, PNAS 2008 | 在一个"结构形式的文法"（树、环、格等）上做贝叶斯模型选择，从数据中发现结构的**种类** | 与 A2（按行为定律选择构造 schema）最接近：都是先选"种类"再拟合参数 | 可借鉴 | [V]（只核对了书目与摘要开头） |
| Chollet, *On the measure of intelligence*（ARC），arXiv 1911.01547, 2019 | 用少量输入输出范例定义网格任务；训练集 400 个，评测集公开 400 个 + 私有 | 第三方、目标级、带范例的挑战来源；许可证需核对（二手来源称 Apache-2.0）；公开题目可能已进入 LLM 训练数据 | 可借鉴（外部挑战） | [V]（许可证 [S]） |
| icecuber（Kaggle ARC 2020 冠军）；Hodel 的 ARC DSL 与 re-arc | 手写 142 种网格变换的 DSL + 至多 4 层的暴力搜索，私有测试集约 20.6 %；Hodel 的 DSL 只用训练集设计 | "手写词汇 + 搜索"在第三方目标级任务上的强基线，以及它的成本（约 1 万行代码、每题数百万个候选网格） | 已有（基线） | [S] |

## 2. 行为定律、性质测试与局部性（H-A 的 A2、A3）

| 工作 | 结论与实验条件 | 意义 | 分类 | 核查 |
|---|---|---|---|---|
| Goldreich, Goldwasser, Lehman, Ron, Samorodnitsky, *Testing monotonicity*, Combinatorica 20(3):301–337, 2000 | 布尔函数单调性的随机测试器，查询复杂度 O(n/ε) | 定律可以用少量**查询**判定；但被动数据中可比较的输入对极少，这是 A2 的关键风险 | 可借鉴 | [V] |
| Naor & Stockmeyer, *What can be computed locally?*, SIAM J. Computing 24(6):1259–1277, 1995 | 局部可检验标注（LCL）；哪些问题有与网络规模无关的局部算法；一般情形不可判定 | "哪些能力能用局部结构构造"有现成的理论框架；H-B 中局部生成的边界 | 已有 | [V] |
| Mordvintsev et al., *Growing Neural Cellular Automata*, Distill 2020 | 用梯度训练局部更新规则，从单个细胞长出并维持目标图案 | A3（局部迭代规则）的神经实现；但它对每个目标图案训练权重，违反本研究的路线 A | 可借鉴（对照） | [V]（细节来自二手来源） |
| Wiskott & Sejnowski, *Slow feature analysis*, Neural Computation 14(4):715–770, 2002 | 从时间上缓慢变化的信号中无监督地学习不变量 | 时间连续性可以为被动观测提供"邻近的可比较样本"；A2 被动版本的可能出路 | 尚不确定 | [V] |
| Ravanbakhsh et al. 等变性；Cohen & Welling G-CNN | 由参数共享得到群等变性 | 等变先验（Mission 02 引理 E）的已知来源 | 已有 | [V-M2] |

## 3. 集合值目标与生成性选择（H-B）

| 工作 | 结论与实验条件 | 意义 | 分类 | 核查 |
|---|---|---|---|---|
| Freuder, *A sufficient condition for backtrack-free search*, JACM 29(1):24–32, 1982 | 约束图宽度为 i 且达到 (i+1)-相容时，搜索无需回溯；树结构 + 弧相容即可 | "传播后选择"何时无需搜索的经典充分条件；B2 的理论依据 | 已有 | [V]（具体条件经二手讲义确认，[S]） |
| Barto & Kozik, *Constraint satisfaction problems solvable by local consistency methods*, JACM 61, 2014 | 固定约束语言的 CSP 能被局部相容判定，当且仅当它"不能计数"（有界宽度的刻画） | B2 在**有限模板 CSP** 上的完整边界；连通性、面积等"绘画式"约束不是有限模板，边界未知 | 已有 / 尚不确定 | [V] |
| Bulatov, FOCS 2017；Zhuk, *A proof of the CSP dichotomy conjecture*, JACM 67(5), 2020 | 有限模板 CSP 要么多项式可解，要么 NP 完全，由多态（代数定律）决定 | 生成任务的可构造性由约束的**代数定律**决定，这与 A2 的思路同源 | 已有 | [V] |
| Edmonds, *Matroids and the greedy algorithm*, Math. Programming 1:127–136, 1971 | 贪心对所有权重最优当且仅当可行集是拟阵 | B1/B2 中"贪心选择不会走进死路"的精确判据 | 已有 | [V] |
| Karth & Smith, *WaveFunctionCollapse is constraint solving in the wild*, FDG 2017 | 流行的图案生成算法 WFC 本质上是带传播的约束求解，有时需要回溯 | "局部传播 + 选择"的生成器在实践中会遇到死路；B2 的真实反例来源 | 可借鉴 | [V] |

## 4. 这些工作产生了哪些竞争假说

1. 程序综合与 ILP（EUSolver、Popper、DreamCoder）说明：只要有一个表达力足够、带类型的 DSL，"从范例归纳机制"就是搜索问题。**零假说 H-0 的强形式由此而来**：本研究的原语若只在搜索空间的形状上不同，就只是另一种 DSL。
2. Gold 与 Angluin 说明：被动数据下识别是难的，查询使它变易。Mission 02 的 A-auto 成功可能来自类似查询的特权；L3 部分否定了这一点（单格探测不必要），但整幅状态读出仍是一种特权。
3. Kemp–Tenenbaum 与性质测试说明：可以先确定机制的**种类**（形式、定律），再拟合参数。这产生了 A2：按行为定律选择构造 schema。它的风险也由性质测试文献给出：定律测试需要可比较的输入，被动数据里很少。
4. CSP 二分定理、Freuder、Barto–Kozik、Edmonds 说明：在有限模板约束上，"无需搜索的构造"何时存在已被代数定律完全刻画。**因此 H-B 的新问题只能在模板之外**：连通性、面积、全局对称这类绘画式约束。
5. NCA 说明局部规则可以生成复杂形态，但需要逐目标训练；它给出 A3 的表示，同时提醒我们 A3 的知识来源可能是训练。
