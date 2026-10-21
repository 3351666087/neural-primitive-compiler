# Mission 06 Gate 1：外部环境的可行性与选型

**状态：BLOCKED（等待用户决定）。** 本文件是可行性报告与选型建议。在用户做出 §6 的决定之前，不安装、不下载、不建立账号，也不读取任何任务内容。全部事实来自官方页面（2026-10-21 读取），只读文档、Hugging Face 公开卡片与 Docker Hub 元数据；没有读过任何任务答案、评分标签或任务专用代码。

## 1. 本机资源（2026-10-21 实测）

| 项目 | 值 |
|---|---|
| 机器 | MacBook Air（Mac16,12），Apple M4，10 核（4 性能 + 6 能效），16 GB 内存 |
| 磁盘 | 228 GiB，**可用 8.7 GiB**（已用 96 %） |
| 虚拟化 | `docker` CLI、`colima`（现有 VM 磁盘 9.4 GB）、`qemu-system-aarch64`；没有 VirtualBox、VMware、podman |
| Python | 项目 venv：Python 3.12.13，Z3 5.3.1（`z3.get_version_string()`），numpy 2.5.4 |
| 网络 | Bash 沙箱经过滤代理，访问新主机需逐个声明 |
| 云 | 用户配置了 rclone 远端 `gdrive:`。用户的决定（2026-10-21）：在 Gate 1 给出各环境的精确磁盘需求之前，不移动任何文件 |

## 2. 候选环境（官方来源）

### 2.1 WorkArena / WorkArena++（BrowserGym），主域候选

- **代码与许可**：BrowserGym 与 WorkArena 均为 Apache-2.0（ServiceNow，2024）。安装：`pip install browsergym-workarena`，然后 `playwright install`。BrowserGym 需要 Python > 3.9。来源：github.com/ServiceNow/BrowserGym、github.com/ServiceNow/WorkArena。
- **环境本体是远程 ServiceNow 实例，不在本机。**
  - 官方途径是 Hugging Face 上的门控数据集 `ServiceNow/WorkArena-Instances`：填表、接受条款、等待批准，再用 `HUGGING_FACE_HUB_TOKEN` 认证。
  - 配置（`config.py`）只支持 ServiceNow 版本 `washingtondc`，实例清单为 `instances_v2.json`。
- **条款**（数据集卡片原文要点）：
  - 实例"exclusively for benchmarking, evaluation, and research"；"must not be used for training, production workloads"；
  - 公平使用："Avoid excessive automated queries"；
  - 可能"reset, wiped, or decommissioned at any time without notice"，可能被限流。
- **替代：** 安装器 `workarena-install` 识别个人开发者实例（`dev\d{6}.service-now.com`）。但 README 没有说可以用它代替官方实例池，且只支持 `washingtondc` 版本。
  - 安装器会大幅改动实例：关闭密码策略、删除 admin 的全部用户偏好、安装主题与更新集、重建列表视图与表单、建立知识库。只应在专门的沙箱实例上运行。
- **任务结构**（WorkArena++ 论文 arXiv:2407.05291 v2）：
  - L1：33 个原子任务。
  - L2、L3：同一组 341 个工作流，共 682 个任务。L2 给出明确步骤；L3 通过工单与知识库给出目标，不给步骤。
  - 五类能力：规划与问题求解 66、信息检索 39、数据驱动决策 156、复杂记忆 28、不可行任务识别 52。
  - 任务由原子任务"chained together"组合而成：oracle 与 validator 也由子任务的 oracle、validator 组合而成。
  - 种子 0–9 保留用于评测，其余种子可用于调参。
- **难度与基线**：L2 上 GPT-4o-v 3.8 ± 1.3 %、GPT-4o 3.0 ± 1.1 %；L3 上所有代理均为 0；人类 93.9 %（98 个实例的子集）。
- **磁盘**：只需 Python 包与 Playwright 的 Chromium，估计 < 1.5 GB。这是估计，需要在试点中实测。
- **需要的东西**：
  - 用户的 Hugging Face 账号与门控批准，以及接受条款。本会话不能建立账号或接受条款，必须由用户本人完成。
  - 对 `*.service-now.com` 与 `huggingface.co` 的网络访问。

### 2.2 WebArena / WebArena-Verified，主域候选

- **代码**：Apache-2.0，812 个任务（v0.2.0 标注）。WebArena-Verified 逐个复核了任务、答案与评测器，去掉了 LLM 判分，可以离线回放网络轨迹评分，另有 258 个 "hard" 子集。
- **环境本体必须自托管**：shopping、shopping_admin、reddit、gitlab、wikipedia、map 六个站点。官方推荐 AWS AMI（t3a.xlarge，1000 GB EBS）；自建地图后端约下载 180 GB。
- **WebArena-Verified 的精简镜像**（Docker Hub `am1n3e/*`，压缩大小）：

  | 镜像 | 大小 | 架构 |
  |---|---|---|
  | gitlab | 22.01 GB | amd64 |
  | shopping | 5.42 GB | amd64 |
  | reddit | 4.57 GB | amd64 |
  | shopping_admin | 1.25 GB | amd64 |
  | map | 1.19 GB（另需地图数据） | amd64 |
  | wikipedia | 0.05 GB（另需 zim 数据） | arm64 |

- **本机结论：BLOCKED。**
  - 除 wikipedia 外，镜像全部只有 amd64，在 M4 上需要 x86 仿真；
  - 仅 shopping + shopping_admin + reddit 的压缩镜像就已约 11 GB，解压后更大，超过 8.7 GB 可用空间。
- **可行路线（都需要用户决定）：**
  - (a) 腾出约 60–100 GB 磁盘（估计值，含解压与 colima VM 增长）并接受仿真性能；
  - (b) 用户提供 x86 云主机（费用与账号属于用户）；
  - (c) 只取 shopping_admin + map 的子集。这会改变任务分布，必须先说明为什么不算降低难度。

### 2.3 ALFWorld（文本版），异质挑战域候选

- **代码与许可**：
  - ALFWorld 为 MIT；TextWorld 为 MIT；Fast Downward 为 GPL-3.0；
  - ALFRED / AI2-THOR 资产的许可没有在页面上写明，需要在下载前确认。
- **安装**：`pip install alfworld`（0.4.2，2025-01-06）。只装文本版时依赖只有 `textworld[pddl]>=1.6.1` 与 `pyyaml`，不需要 AI2-THOR 或 GPU。
- **Apple Silicon**：
  - TextWorld 1.7.0（2026-01-30）只有 x86-64 的 wheel（manylinux 与 macosx_10_13_x86_64），没有 macOS arm64 wheel；
  - ALFWorld README 建议在 arm Mac 上用 `CONDA_SUBDIR=osx-64`（Rosetta 下的 x86 Python）；
  - 需要试点确认：要么从源码构建，要么用 x86 环境。
- **数据**：`alfworld-download` 从 GitHub Releases 下载：
  - json 68.7 MB、pddl 33.3 MB、tw-pddl 34.8 MB；
  - 默认还下载 MaskRCNN 检测器 170 MB（文本版不需要，可以只下载所需文件）。

  合计约 0.14–0.31 GB。
- **任务**：
  - 3,553 个训练游戏；验证集中，140 个"见过的房间"、134 个"未见过的房间"；
  - 六类任务（pick_and_place、look_at_obj_in_light、pick_clean_then_place、pick_heat_then_place、pick_cool_then_place、pick_two_obj）。任务类型名来自对论文的记忆，**需要在试点中由官方文件核对**。
- **泄漏风险**：
  - 每个游戏目录里有 `traj_data.json`（专家计划，含 PDDL 动作）与 `initial_state.pddl`（完整隐藏状态）；
  - 文本环境的 `infos` 可以提供 `admissible_commands`。

  构造器侧必须看不到前两者；第三者只能作为明确标注的特权消融条件。

### 2.4 OSWorld（可选），不建议

- 369 个任务（官方支持 361 个），Apache-2.0。在 Apple 芯片上需要 VMware Fusion；VM 镜像的大小页面上没有写明。部分任务需要 Google 账号与代理。
- 以本机磁盘与虚拟化条件，不进入候选。

## 3. 选型的科学理由（锁定之前的建议）

**主域建议：WorkArena++（L2 与 L3），L1 作为原子技能层。**

1. **非玩具、真实业务语义**：ServiceNow 的记录、列表、表单、仪表板、知识库与工单，有前置条件与副作用。
2. **天然对应任务书 §4 的智能成分：**
   - 组合（L2/L3 由原子任务链接而成）；
   - 长程记忆（"复杂记忆"类）；
   - 关系与变量绑定（按检索到的值进行后续操作）；
   - 诚实弃权（不可行任务类，`report_infeasible`）；
   - 部分可观测（L3 需要从知识库检索步骤）。
3. **难度真实且未被饱和**：公开强代理在 L3 上为 0，人类为 94 %。即使我们的系统失败，失败本身也有信息量。
4. **官方组合结构与 Mission 05 的问题直接相交**：基准作者用"组合原子任务的 oracle 与 validator"来构造复合任务。这既是对 H-COMP 的现成参照（第三方的组合方式），也是需要防火墙的强泄漏源。
5. **磁盘需求小**，与本机资源相容。

**异质域建议：ALFWorld 文本版。**
- 物体、容器、空间、可见与不可见状态、工具使用（加热、冷却、清洗），因果结构与网页工作流显著不同；
- 有官方的"见过 / 未见过房间"划分；
- 数据小，本机可运行（需要验证 Apple Silicon 安装）。

**为什么不算人为设计的玩具：** 两个环境的任务、评分器、版本都由第三方维护。我们只写观察与动作适配器（成本记账）。

**为什么不先选 WebArena：** 本机磁盘与架构使它无法部署。若用户提供资源，WebArena-Verified（离线确定性评分、无 LLM 判分）是很好的第二主域，可在后续 Gate 加入。

## 4. 任务族划分与持出保管（草案，需在冻结前确定）

- **WorkArena++。** 按工作流族（341 个工作流的组合结构 / 类别 / 原子技能对子）划分，而不是按种子划分：
  - 开发族只用种子 ≥ 10；
  - 持出族在冻结前不实例化、不查看；
  - 正式评测用官方保留的种子 0–9。

  持出族清单由独立者（用户或隔离会话）在不告诉本会话内容的情况下选定，只报告清单哈希。
- **ALFWorld。** 开发用训练集与 valid_seen 的部分任务类型；正式持出用 valid_unseen（官方未见房间），另把一个任务类型整体留到持出，以检验新组合深度。
- **裁判与构造器的进程隔离：**
  - 环境与任务对象（含 `cheat`、`validate`、ALFWorld 的 `infos['won']`、PDDL 与专家计划）只存在于裁判进程中；
  - 构造器进程通过本地接口只拿到合法观察（AXTree / DOM / 截图；或文本观察），并发送动作。

## 5. 泄漏与污染审计（初稿）

| 来源 | 风险 | 处理 |
|---|---|---|
| 执行模型（本会话）的预训练 | WorkArena（2024）、WorkArena++（2024）、ALFWorld（2020）都是公开的；本会话可能知道任务类型、PDDL 域、常见解法 | 记入 `KNOWLEDGE_PROVENANCE.md`：凡由本会话写入的技能、检测器、文法都是"设计者 / 预训练先验"，计入成本；持出族由独立者选择 |
| 基准自带的 oracle（`cheat`）与 validator | 直接给出动作序列与成功判据 | 只在裁判进程；构造器代码静态检查不得导入任务类（同 G0-T1 的扫描） |
| ALFWorld 的 `traj_data.json`、`initial_state.pddl` | 专家计划与完整隐藏状态 | 数据目录对构造器进程不可读；读取即违规 |
| `admissible_commands` | 合法但强的动作提示 | 主条件不用；作为特权消融条件单列 |
| 公开排行榜、论文中的解法 | 方法层面的污染 | 不阅读任务级解法；方法文献只用于基线（B1、B4） |

## 6. 需要用户决定的事项

| 编号 | 决定 | 选项 |
|---|---|---|
| D1 | 主域访问方式 | (a) 用户申请 `ServiceNow/WorkArena-Instances` 门控访问并接受其条款，令牌由用户放入环境变量；(b) 用户提供一个 `washingtondc` 版本的个人开发者实例（会被安装器大幅改动）；(c) 改为 WebArena-Verified，并提供磁盘或 x86 云主机 |
| D2 | WorkArena 条款与 B 的探索 | 条款禁止把实例用于"training"。B 的主动实验是"从环境观察中发现规律"，是否落在条款允许的"research"之内，需要用户判断。保守做法：B 的主动探索限定在开发种子 ≥ 10，交互次数设上限并记账 |
| D3 | ALFWorld 的试点下载 | 允许在独立目录中 `pip install alfworld` 与 TextWorld（约数十 MB），并只下载 json、pddl、tw-pddl 三个数据包（约 0.14 GB），用于 30–60 分钟的部署试点 |
| D4 | 强基线 B2（LLM 代理） | 需要模型 API 与费用预算；没有预算则 B2 的对应结论记为 INCONCLUSIVE |
| D5 | 持出保管人 | 用户本人，或一个隔离的独立会话（同 Mission 05 的 G3/G4 做法） |
