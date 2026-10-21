# Mission 07 先前工作对照

核查方式：2026-10-21 检索每篇文献的出版信息与摘要。**[V]** 表示出版信息与核心结论已按摘要或出版页核对；**[S]** 表示只核对了出版信息，内容来自二手来源；未读全文的细节不作为证据使用。

## 1. 自主目标（autotelic）与目标探索过程

| 文献 | 核查 | 观察到的结论（据摘要） | 与 Mission 07 的关系 |
|---|---|---|---|
| Colas, Karch, Sigaud, Oudeyer. *Autotelic Agents with Intrinsically Motivated Goal-Conditioned RL: A Short Survey*. JAIR 74:1159–1199, 2022. DOI 10.1613/JAIR.1.13554；https://arxiv.org/abs/2012.09830 | V | 综述能表示、生成、选择并解决自身问题的智能体；给出目标表示的类型学与学习表示、选择目标的方法 | 任务书 Q1 的标准参照：自主目标本身不是新现象 |
| Forestier, Portelas, Mollard, Oudeyer. *Intrinsically Motivated Goal Exploration Processes with Automatic Curriculum Learning*. JMLR 23(152), 2022；https://jmlr.org/papers/v23/21-0808.html | V | IMGEP：目标是参数化的适应度函数，按内在奖励（学习进展）选择目标；模块化变体在对象层面分开目标空间；课程产生作为踏脚石的技能（例如嵌套工具使用） | 最接近 H2 的已知机制："技能作为踏脚石"已被报告，但不涉及目标**表示**的扩展 |
| Péré, Forestier, Sigaud, Oudeyer. *Unsupervised Learning of Goal Spaces for Intrinsically Motivated Goal Exploration*. ICLR 2018；https://arxiv.org/abs/1803.00781 | V | 两阶段：先从观察中学习潜在空间，再在其中采样目标；学到的表示可以接近、有时超过工程化表示 | **任务书基线 4 的原型**：目标空间由学到的表示决定，但表示学习与目标追求分开 |
| Laversanne-Finot, Péré, Oudeyer. *Curiosity Driven Exploration of Learned Disentangled Goal Spaces*. CoRL 2018，PMLR 87:487–504；https://arxiv.org/abs/1807.01521 | V | 解缠的目标空间优于纠缠的；按模块的学习进展采样目标，并用同一信号找出可独立控制的特征 | "可控特征的发现"与 H2 的 S₁ 相近；仍是预先训练的表示 |
| Colas, Teodorescu, Oudeyer, Yuan, Côté. *Augmenting Autotelic Agents with Large Language Models*. CoLLAs 2023，PMLR 232:205–226；https://proceedings.mlr.press/v232/colas23a.html | V | LMA3：用语言模型做重标注、目标生成（含子目标分解）与奖励函数；在文本环境 CookingWorld 中学到许多技能，没有手写目标、奖励或课程 | 任务书禁止的"外挂 LLM 目标生成器"的已发表形态；只能作为单独计账的分支 |

## 2. 好奇心与探索

| 文献 | 核查 | 观察到的结论 | 关系 |
|---|---|---|---|
| Pathak et al. *Curiosity-driven Exploration by Self-supervised Prediction* (ICM)，ICML 2017 | S | 内在奖励为学到的特征空间中前向模型的预测误差；已知易受"嘈杂电视"影响 | 基线 3（预测误差好奇心） |
| Burda, Edwards, Storkey, Klimov. *Exploration by Random Network Distillation*. ICLR 2019；https://iclr.cc/virtual/2019/poster/1093 | S | 奖励为预测固定随机网络输出的误差 | 基线 3 的另一形式 |
| Ecoffet, Huizinga, Lehman, Stanley, Clune. *First return, then explore*. Nature 590:580–586, 2021；https://arxiv.org/abs/2004.12919 | V | 探索失败的两个原因："脱离"（忘记如何回到有希望的状态）与"脱轨"（没有先回到状态再探索）；Go-Explore 保存状态存档并先返回再探索 | 生态环境中"踏脚石"状态的到达问题；存档本身是一种记忆结构 |

## 3. 开放式学习与自我修改

| 文献 | 核查 | 观察到的结论 | 关系 |
|---|---|---|---|
| Schmidhuber. *PowerPlay: Training an Increasingly General Problem Solver by Continually Searching for the Simplest Still Unsolvable Problem*. Frontiers in Psychology 4:313, 2013；https://arxiv.org/abs/1112.5309 | V | 搜索（新任务, 求解器修改）对，直到修改后的求解器解决新任务与全部旧任务而原求解器不能；按描述与验证的简单性排序 | **H2 循环的形式原型**："新结构使新任务可解，新任务驱动结构修改"已有明确算法；不涉及环境中的隐藏机制与因果识别 |
| *OMNI: Open-endedness via Models of human Notions of Interestingness*，2023；https://arxiv.org/abs/2306.01711 | S（作者未核对） | 用在人类数据上训练的基础模型判断什么值得探索 | 有趣性来自预训练先验，不是内生 |
| Faldor, Zhang, Cully, Clune. *OMNI-EPIC*. ICLR 2025；https://arxiv.org/abs/2405.15568 | V | 基础模型以代码生成环境与奖励函数，并检查任务是否新颖、有价值 | 同上；作为 LLM 分支的对照 |
| Wang et al. *Voyager: An Open-Ended Embodied Agent with Large Language Models*. TMLR 2024；https://arxiv.org/abs/2305.16291 | V | 自动课程、可执行代码的技能库与迭代提示；技能库可在新世界中复用 | 结构（技能库）随目标增长的 LLM 形态；技能是代码缓存，按任务书须经 H0-RENAME 检验 |

## 4. 稳态、主动推断与内部状态

| 文献 | 核查 | 观察到的结论 | 关系 |
|---|---|---|---|
| Keramati, Gutkin. *Homeostatic reinforcement learning for integrating reward collection and physiological stability*. eLife 3:e04811, 2014；https://elifesciences.org/articles/04811 | V | 把初级奖励定义为满足生理需求；证明寻求奖励等价于生理稳定这一目标；对时间折扣给出形式依据 | H1-STATE 的已知基础：内部需求驱动的目标选择不是新现象 |
| Friston, Rigoli, Ognibene, Mathys, FitzGerald, Pezzulo. *Active inference and epistemic value*. Cognitive Neuroscience 6(4):187–214, 2015；DOI 10.1080/17588928.2015.1020053 | V | 策略价值分解为外在价值（偏好）与认知价值（信息增益）；认知价值先占主导，信息耗尽后外在价值接管 | "为了获得结构而行动"的已有理论；可作为结构获取触发方式的竞争解释 |

## 5. 果蝇神经组织：功能机制假说的来源

| 文献 | 核查 | 观察到的结论 | 抽取的功能假说 |
|---|---|---|---|
| Aso, Rubin. *Dopaminergic neurons write and update memories with cell-type-specific rules*. eLife 5:e16135, 2016；https://elifesciences.org/articles/16135 | V | 蘑菇体不同区室的多巴胺能神经元类型在记忆形成的训练要求、衰减、容量与可塑性上不同；同一类型按与气味的时间关系可写入或削弱记忆 | **F-MB**：并行的、学习规则不同的记忆区室（快速 / 稳定），在非平稳环境中同时保留新近与长期关联 |
| Krashes et al. *A neural circuit mechanism integrating motivational state with memory expression in Drosophila*. Cell 139:416–427, 2009；DOI 10.1016/j.cell.2009.08.035 | V | dNPF（NPY 同源物）通过六个投射到蘑菇体特定区域的多巴胺能神经元，按饥饿状态开关食物记忆的表达 | **F-STATE**：内部状态门控已有记忆的表达，在观察相同的情况下改变选择（H1-STATE） |
| Seelig, Jayaraman. *Neural dynamics for landmark orientation and angular path integration*. Nature 521:186–191, 2015；DOI 10.1038/nature14446 | V | 椭球体的群体活动合并视觉地标与自身运动线索，在没有线索时以持续活动维持方向估计，动力学类似环形吸引子 | **F-CX**（与下一条合并）：持续的方位记忆 |
| Mussells Pires et al. *Converting an allocentric goal into an egocentric steering signal*. Nature 626:808–818, 2024；DOI 10.1038/s41586-023-07006-3 | V | 中央复合体比较以世界坐标编码的航向（EPG）与目标角（FC2），由 PFL3 产生身体坐标的转向；破坏 PFL3 的传递降低朝任意目标方向定向的精度 | **F-CX**：一种"以世界坐标存储的目标"的结构。没有它，"回到视野之外的记忆位置"这一类目标在当前观察的谓词中无法表达；有了它，这一类目标变得可表达。这是一个天然的"结构 → 目标类"候选 |
| Dorkenwald et al. (FlyWire). *Neuronal wiring diagram of an adult brain*. Nature 2024；https://www.nature.com/articles/s41586-024-07558-y | V | 成年雌性果蝇全脑 139,255 个神经元、5,450 万个突触的连接图，附细胞类型与神经递质预测 | 只作为结构参照；不要求复刻 |

## 6. 主体性的定义

| 文献 | 核查 | 观察到的结论 | 关系 |
|---|---|---|---|
| Barandiaran, Di Paolo, Rohde. *Defining agency: Individuality, normativity, asymmetry, and spatio-temporality in action*. Adaptive Behavior 17(5):367–386, 2009；DOI 10.1177/1059712309343819 | V | 主体须满足三条：自身界定个体性、作为环境中活动的主动来源（交互不对称）、按规范调节活动 | 本 Mission 的智能体由设计者划定边界、规范由设计者给定的生存约束提供，按这一定义**不满足"个体性"**；在 `AGENCY_DEFINITION.md` 中写明 |
| Kenton, Kumar, Farquhar, Richens, MacDermott, Everitt. *Discovering Agents*. Artificial Intelligence 322:103963, 2023；https://arxiv.org/abs/2208.08345 | V | 因果定义：若行动对世界的影响不同时系统会改变其策略，则系统是智能体；给出从数据中发现智能体的因果发现算法 | 一个必要而弱的检验：改变机制后目标选择是否随之改变 |

## 7. 基准

| 文献 | 核查 | 观察到的结论 | 关系 |
|---|---|---|---|
| Hafner. *Benchmarking the Spectrum of Agent Capabilities* (Crafter)，ICLR 2022；https://arxiv.org/abs/2109.06780 | V | 22 个成就（采集、制作、觅食、战斗、睡眠等），每个智能体 100 万步预算，按成就成功率与聚合分数评估 | 外部生态的候选；成就只作为裁判侧评估 |
| Matthews et al. *Craftax: A Lightning-Fast Benchmark for Open-Ended RL*. ICML 2024，PMLR 235；https://proceedings.mlr.press/v235/matthews24a.html | V | Craftax-Classic 是 Crafter 的 JAX 重写，最快 250 倍；完整 Craftax 扩展了机制，现有探索方法在其上进展甚微 | 外部生态的首选（官方符号观察；本机预检见 `G1_FEASIBILITY.md`） |

## 8. 已知结论与本 Mission 可能的新颖性

| 主张 | 状态 |
|---|---|
| 智能体可以在没有逐回合任务的情况下自选目标 | **已知**（autotelic、IMGEP、LMA3） |
| 内部需求变量使相同观察下的选择不同 | **已知**（稳态强化学习；果蝇饥饿门控） |
| 学到的表示决定目标空间 | **已知**（Péré 2018；Laversanne-Finot 2018） |
| 获得的技能成为后续目标的踏脚石 | **已知**（IMGEP 的嵌套工具使用；Voyager 的技能库） |
| "新任务—求解器修改"的循环 | **已知的形式原型**（PowerPlay） |
| 在环境的**隐藏机制**下，用前瞻日志、受限不可表达性证明与配对干预，判定新结构是否改变了**可表示的目标类**（而不只是成功率），并做两轮 | **未见先例的部分在识别方法上**，不在算法上；须在 Gate 2 用最强基线检验它是否只是已知机制的副产品 |
| 哪些组织条件（持久记忆、需求变量、结构获取的触发方式、目标语言是否随结构增长）对这一循环是必要的 | 待检验 |
