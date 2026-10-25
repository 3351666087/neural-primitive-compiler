# Mission 08 Gate 1：数据可行性

本文件回答任务书 §4.2 与 §4 的硬退出条件：是否找到至少一个合法可用、含真实回路关系的数据子集，以及一条独立验证路径。来源、许可证与大小由 Gate 1 的数据审阅代理（两份结构化报告见 `audit/g1_reads.json`）与本文件的直接核对共同确认；标"已核对"的条目由本文件经 API、哈希或下载核对过。所有原始文件放在 `data/raw/`（不提交 Git），哈希与固定来源见 `data/README.md` 与 `src/m08/raw.py`。

## 1. 结论

| 层级 | 状态 | 数据 | 独立验证路径 |
|---|---|---|---|
| G-STRUCT（结构 / 发育） | **可行** | *C. elegans*：Witvliet et al. 2021 的 8 个等基因个体（0–50 h），White et al. 1986 的 JSH（L4，40 h）与 N2U（成年，54 h） | 冻结之前不读取的整只动物：White JSH 与 N2U（不同实验室、不同年代的电镜重建），以及 Witvliet 的若干整阶段（见 `DATA_SPLITS_AND_CUSTODY.md`） |
| G-FUNCTION（功能 / 干预）· 线虫 | **可行** | Randi et al. 2023 信号传播图谱：单神经元光遗传刺激 + 全脑钙成像，WT 113 只、unc-31 18 只动物 | 与电镜动物完全独立的动物与模态；有遗传扰动（unc-31） |
| G-FUNCTION · 果蝇（任务书优先评估的支线） | **可行** | 视觉运动通路 T4 ON 回路：flyvis 的 FIB-25/FIB-19 共识连接组（MIT）；Groschner et al. 2022 的在体膜片钳记录（CC BY 4.0） | T4 的记录、T4 感受野与 GluClα RNAi 扰动记录在冻结之前不读取；输入神经元（Mi1、Tm3、Mi4、Mi9、C3）的记录可作为驱动 |
| G-CONSTRUCT | **数据上不阻塞，但依赖 G-FUNCTION** | 同上 | 没有独立的"能力要求"数据集；按任务书 §7 路线 C，只在 G-FUNCTION 通过后做小规模检验（`PRE_REGISTRATION.md`） |

硬退出条件满足：两条证据支线都有合法、无需登录的数据与独立验证路径。按任务书 §4.2，两条支线使用不同物种，**不拼接成跨物种规律**。

## 2. 结构 / 发育线（*C. elegans*）

| 数据 | 内容 | 访问 | 许可证 | 大小 | 角色 |
|---|---|---|---|---|---|
| Witvliet et al. 2021，8 个连接组 | 神经环与腹神经节；化学突触与缝隙连接计数；年龄 0、5、8、16、23、27、50、50 h（NemaNode `/api/datasets`，已核对） | NemaNode API、WormWiring、OpenWorm cect 镜像，均无需登录 | **文章不是开放获取（Springer TDM）；数据没有声明开放许可证** | NemaNode JSON 共 0.79 MB；cect xlsx 共 0.29 MB（已核对） | 开发与留出（按个体） |
| White et al. 1986 JSH（L4）与 N2U（成年） | 同一神经环区域的旧电镜重建，2020 年 Zhen 实验室补注肌肉 | NemaNode API | 未找到数据许可证 | 0.11 + 0.12 MB（已核对） | **实验室外的留出个体**（不同年代、注释者与切片） |
| Cook et al. 2019 SI 5 | 全动物合成连接组（N2U、JSH 等多组电镜的重注释） | cect 镜像、WormWiring | 无开放许可证（合理使用声明） | 4.2 MB | 只作参考；与 White 共享电镜数据，**不作为独立个体** |
| Brittin et al. 2021 接触组 | JSH 与 N2U 的膜接触邻接（XML） | Zenodo 4383277 | **CC BY 4.0**（已核对） | 0.88 MB（已核对） | 接触（Peters 规则）基线；与 White 是同一批动物，只作协变量 |
| Pathak et al. 2020 S5 表 | 由 Sulston 谱系图手工转录的出生时间（280 个神经元） | PLOS 补充材料 | **CC BY 4.0** | 22.5 KB（已核对；内容与 Richter & Schneidman 仓库中的 `time_of_birth.xls` 逐格相同） | 输入特征（与连接组独立） |
| Skuhersky et al. 2022 位置图谱 | NeuroPAL 动物（每个神经元 ≥ 7 只）的平均胞体三维坐标，300 个神经元 | github.com/bluevex/elegans-atlas | 论文 CC BY 4.0；仓库无许可证 | 6.8 KB（已核对；`LowResAtlasWithHighResHeadsAndTails.csv` 与 Richter & Schneidman 的输入数值相同，只有运动神经元命名不同） | 输入特征 |
| Cook 2019 细胞类别表 | 15 个功能类别（SN1–6、IN1–4、MN1–5 等） | Richter & Schneidman 仓库（转载 Cook SI） | 无开放许可证 | 27.6 KB | 文献类型（**部分依据连接定义**，见 `BIOLOGICAL_ASSUMPTIONS.md`） |
| WormAtlas 神经元名单与谱系名 | 302 个神经元的名称、谱系与分类 | cect 镜像 | 未声明 | 44 KB | 神经元集合与类别 |

本文件的直接核对：两个 Witvliet 成年个体在 180 个共同神经元上各有 1,933 个有连接的有序神经元对，两者共有 1,279 个，与 Richter & Schneidman 正文的数字完全一致（`tests/test_loader.py`，数据接口正对照）。

**已知的混杂与限制**（详见 `BIOLOGICAL_ASSUMPTIONS.md`）：Witvliet 的发育阶段与电镜技术、制备批次混杂；只有一对同龄个体（7、8）；位置是成年图谱，被用于所有阶段；White 与 Witvliet 的注释约定不同——Cook 2019 对 N2U 的重注释新增了 1,109 个连接（Witvliet 2021 正文，复核代理核对），因此 White 个体上的检验是一个**注释迁移条件**，单独报告，不与同流程的 W7 / W8 检验合并（`DATA_SPLITS_AND_CUSTODY.md`）。Creamer 等与 Randi 等的解剖基线都用了 JSH、N2U 与 W7、W8 的连接组；本轮的功能线也用 W7、W8，三者共享结构输入。

其他可能的来源（本轮不用）：Yim et al. 2024 的耐久幼虫连接组（CC BY 4.0，单只动物，突触由 CNN 自动检测，没有缝隙连接；同时是阶段与流程的迁移）；*Pristionchus pacificus* 连接组（Cook et al. Science 2025）是冻结规则跨物种迁移的唯一合理检验，本轮不做，因此不得有任何跨物种结论；果蝇幼虫 L1 与 L3 的伤害感受回路比较（Gerhard et al. eLife 2017，CATMAID 数据，访问与许可证未核实）。

## 3. 功能 / 干预线 · 线虫（Randi et al. 2023）

| 数据 | 内容 | 许可证 | 大小 | 角色 |
|---|---|---|---|---|
| Source Data Fig. 2（MOESM5） | WT 168 × 168 的平均 ΔF/F 与 q 矩阵 | **CC BY 4.0**（文章许可证，已核对） | 1.0 MB | 功能目标 |
| Source Data Extended Data Fig. 7（MOESM15） | unc-31 的 ΔF/F 与 q 矩阵 | CC BY 4.0 | 0.29 MB | 扰动对照 |
| Source Data Fig. 3（MOESM6） | 作者的解剖模型预测 ΔV 与测量值 | CC BY 4.0 | 1.0 MB | 已发表的解剖基线 |
| wormneuroatlas `funatlas.h5` | 300 × 300 的 dFF、q、q_eq、观测次数 occ1、每次观测的 dFF_all、核函数（WT 与 unc-31） | 数据来自 Randi 2023（CC BY）；软件 GPL-3.0 | 18.3 MB | 观测次数与逐次观测，用于可靠性上限与划分 |

本文件在 Gate 1 只读取了 `funatlas.h5` 的数据集名称与形状，没有读取任何数值。

**先例**（`PRIOR_ART_AND_NOVELTY.md`）：Randi 等报告解剖模型预测的幅度 R² < 0；Creamer, Leifer & Pillow（bioRxiv 2024/2025）用约束在连接组上的线性动力系统拟合同一批原始记录，因果相互作用达到数据自身可重复性的 92 %（PMC 收录的版本；v4 摘要为 82 %），打乱的连接组差得多。因此"连接组能预测功能"不是新问题；本轮能问的是**由紧凑规则生成的结构**是否携带同样的功能信息。

## 4. 功能 / 干预线 · 果蝇（T4 ON 运动回路）

| 数据 | 内容 | 许可证 | 大小 | 角色 |
|---|---|---|---|---|
| flyvis `fib25-fib19_v2.2.json` | 65 个细胞类型、605 条带符号的类型间连接与六边形偏移；T4 的输入 Mi1(+)、Tm3(+)、Mi4(−)、Mi9(−)、C3(−)、CT1(−) | MIT（已核对 GitHub API） | 0.62 MB（已核对） | 结构来源 |
| Groschner et al. 2022（Nature 603:119–123）Edmond doi:10.17617/3.8G | 在体膜片钳：T4 33 个细胞（ON/OFF × PD/ND，1 kHz）；输入 Mi1 24、Tm3 12、Mi4 19、Mi9 29、C3 16 个细胞；GluClα RNAi 下的 T4 15 个细胞；T4 感受野 46 个细胞 | **CC BY 4.0**（已核对 Dataverse API） | 最小子集约 26.9 MB（全集 5.9 GB，不下载） | 独立功能目标与扰动 |

风险：机制已知（Groschner 自己拟合了电导模型；Lappalainen 的任务训练模型预测了 T4 的方向选择性），所以与已知机制一致只能算复现（H0-KNOWN）；Mi9 的抑制符号已经写在连接组标签里；输入与 T4 的记录来自不同的动物。`fig1d_receptive_fields.npy` 是 pickle 对象，不加载。

## 5. 不可用或不需要的数据

| 数据 | 原因 |
|---|---|
| FlyWire Codex 下载 | 需要 Google 登录与 api_token：按规则不使用 |
| neuPrint（hemibrain、MANC、MCNS） | 需要登录与令牌 |
| Zenodo 5637219 | 只有三维模型（1.1 GB），没有连接表；不需要 |
| FlyWire 全脑（Zenodo 10676866，852 MB 起）、Shiu 全脑表（101 MB）、MAOL（117 MB） | 全脑或大文件；任务书禁止不必要的全脑下载。T4 支线不需要它们 |
| flyvis 预训练模型 | 下载器内嵌作者的 Google Drive API 密钥；本轮的 T4 检验不需要任务训练模型，因此不运行 |
| Sintel（5.6 GB） | 只用于训练 flyvis；不训练，不下载 |
| CeNGEN 表达矩阵（10–15 MB） | 许可证不明；遗传规则基线（SCM、双线性模型）列为可选，见 `BASELINE_PARITY.md` |
| Atanas 2023、Kato 2015、Uzel 2022 | 过大或位置、许可证未核实；不在最小路径中 |

## 6. 磁盘与许可证

- 已下载 58 MB（`data/raw/`），加上 T4 子集约 27 MB，合计约 85 MB，远低于 10 GB 上限。本机剩余磁盘约 3.6 GiB，足够。
- 许可证处理：CC BY 4.0 的数据（Randi、Brittin、Pathak、Groschner）按署名使用；没有开放许可证的数据（Witvliet、White、Cook、Skuhersky 仓库、Richter & Schneidman 仓库）只在本地用于研究，不提交 Git，不再分发，仓库中只保存来源与哈希。
- Richter & Schneidman 的仓库没有许可证：本轮**不复制、不运行**其代码；只下载了四个输入数据文件，用于核对我们的输入与他们的一致。复现按论文方法独立实现（`FAILURE_TAXONOMY.md` C8）。
