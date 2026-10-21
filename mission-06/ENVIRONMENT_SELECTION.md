# Mission 06 Gate 1：外部环境的可行性与选型

**状态（2026-10-21 更新）：Gate 1 通过。主域 AppWorld、异质域 ALFWorld 已部署、隔离、试点并划分；WorkArena++ 因外部批准未到而 BLOCKED，保留为附加域（§10、`MISSION06_FREEZE_PLAN.md`）。** 以下 §1–§6 为当时的可行性报告原文，后续各节按时间追加。初版状态： 本文件是可行性报告与选型建议。在用户做出 §6 的决定之前，不安装、不下载、不建立账号，也不读取任何任务内容。全部事实来自官方页面（2026-10-21 读取），只读文档、Hugging Face 公开卡片与 Docker Hub 元数据；没有读过任何任务答案、评分标签或任务专用代码。

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

## 7. WorkArena 部署试点 P1–P3（2026-10-21；预注册 §G1-P；未接触任何 ServiceNow 实例）

用户决定：D1 = 用户自己申请门控实例池；P1 的下载已获批准。

| 步 | 预测 | 结果 | 判定 |
|---|---|---|---|
| P1 安装 | 成功；全部 arm64 原生；venv 加浏览器 < 1.5 GB | 固定版本全部安装（`env/workarena_install.txt`）。原生扩展为 arm64（numpy、pillow）或 universal2（greenlet、lxml）。Chromium 125.0.6422.26（Playwright build 1117）为 arm64 Mach-O。占用：venv 445 MB + 浏览器 406 MB = 851 MB，另保留 135 MB 的 zip 作出处 | **成立**，带两处部署偏差（见下） |
| P2 本地冒烟 | 无头 Chromium 可用；观察与动作可用 | 在本地 `file://` 表单上：reset 2.8 s；构造器在 AXTree 中找到文本框（bid 7）与按钮（bid 8）；`fill` 与 `click` 无错误；随后的 AXTree 中出现 "saved: pilot record"；截图 720×1280×3。每步约 1.7 s | **成立**（在沙箱之外运行，见下） |
| P3 隔离 | 0 处越界 | 构造器收到的 15 个键恰好是 BrowserGym 的全部观察键，都在白名单内。奖励、terminated、truncated 与 `info`（`task_info`）只出现在裁判日志中。构造器侧导入 `browsergym.workarena` 被导入钩子拒绝。静态扫描 0 处违规 | **成立** |

**部署偏差与约束：**
1. **Chromium 的下载。** 经本机沙箱代理时，Playwright 自带的下载器失败：主 CDN 在 TLS 握手时被重置，两个镜像在约 90 % 处断开。改为用 `curl` 从同一镜像（`playwright-akamai.azureedge.net`，同一文件）下载：
   - 一次完整，141,141,655 字节，zip 自检通过；
   - SHA-256 `e708fe899c9453b59203203c527ae2bbdb3045a83727203151480681533e7d3c`。

   按 Playwright 的目录约定解压，并写入 `INSTALLATION_COMPLETE` 标记。FFMPEG（build 1009，只用于录像）没有安装。
2. **浏览器必须在本会话的命令沙箱之外运行。** 在沙箱内启动时，Chromium 因 `bootstrap_check_in … MachPortRendezvousServer: Permission denied` 立即退出。那次运行原样保存为 `experiments/g1/pilot_p2p3_sandboxed_run.json`。P2、P3 的正式结果来自用户终端标签页中的运行（同一代码、同一 venv）。今后所有浏览器运行都照此办理。
3. **P3 判据收紧。** 沙箱内那次运行中，P3 在一个观察都没收到时也判为成立，判据是空的。重跑之前改为：必须真的收到含 AXTree 的观察，否则为 NOT_EVALUABLE。

**尚未进行：** P4（实例可达）需要用户的令牌，并另行同意。

## 8. ALFWorld 部署试点 A1–A3 与 P-ALF-1（2026-10-21；预注册 §G1-A；下载经用户批准）

**A1 安装：成立。**
- 88 s 完成。`fast-downward-textworld` 与 `jericho` 在本机编译，`libdownward.so` 与 `libfrotz.so` 都是 arm64；`textworld` 1.6.2 为原生 arm64 wheel。
- `pip check` 只报告预期中的 "jericho requires spacy"。
- 数据包的 SHA-256：
  - `json_2.1.1_json.zip`：`25171f16e20ad7b048c47275c45b0babf3aa1cbab29cec97387922350a9844bc`
  - `json_2.1.3_tw-pddl.zip`：`5df77ea759f2211a4106082839ddbbb790f1ba4e7d097ed732cf453f72aa36cf`
- 只解压了 train 与 valid_seen：1.62 GB，3,553 个与 140 个游戏，与官方计数一致。**valid_unseen 仍封存在压缩包中**（解压出的文件数为 0）。
- 占用：venv 109 MB，数据 1.6 GB；本机剩余 4.3 GB。

**A2 冒烟：成立。** 训练集中 10 个游戏，reset 的中位数为 0.98 s，5 步约 0.23 s。

**A3 隔离：成立。**
- 越过边界的只有字符串（文本观察）；
- `alfworld`、`textworld` 在构造器侧的导入被钩子拒绝；
- 静态扫描 0 处违规。

**P-ALF-1（60 个训练游戏 × 20 步；锁定预测全部成立）：**

| 编号 | 预测 | 结果 | 判定 |
|---|---|---|---|
| ALF1-a | U_P ≤ 0.05 | 0.0014（58,064 个查询；只有 `use` 灯有较多未知，0.32） | 成立 |
| ALF1-b | W_P ≤ 0.02 | 0.0083 | 成立 |
| ALF1-c | U_M ≥ 0.5 | 0.619（1,244 步）；POST-HOC，只算目标解析成功的 55 局：0.584 | 成立 |
| ALF1-d | S0 ≤ 0.1 | 0.0 | 成立 |
| ALF1-e | W_M = 0 | 0（59 次实际核对） | 成立 |

**POST-HOC 诊断（`experiments/g1/posthoc_alf.py`，不改变判定）：**
1. **W_P 的 482 个错误全部涉及与代理当前所在处同址的容器。** ALFWorld 中，多个容器可以共享一个位置（例如 shelf 3、shelf 4 与 tvstand 1）。到达时的文本只提到走向的那一个，同址关系从不出现在观察中。这条关系也可以从合法命令推出：到达后，同址容器的 go to 不合法，而其上的 take、open 合法。设计者写的信念规则"一个容器一个位置"是错的，这是一个隐性的设计者先验。
2. 目标解析器漏掉的 5 局都是同一句式 "look at X under the desklamp"（没有冠词）。

**结论（用于 Gate 2/3）：**
- **原始动作层：** 适用性几乎完全可由观察判定。唯一的系统误差来自一个未被告知的环境结构（同址关系），它可以由交互推出。这是 H-DISC 的候选：B 能否从"go to 不合法 / take 合法"的观察中发现同址关系，并让它进入构造？
- **达成器层：** "取得目标物体"的前置条件在 58–62 % 的步上不可判定，第 0 步全部不可判定。Mission 05 的合同类型（在当前状态上可判定的适用性谓词）不能原样迁移到达成器层，需要：
  - 环境契约中的存在公理（每局可解），记为信任；
  - 定义在信念上的进度度量，例如尚未访问的容器数。

  这是 Gate 2 的第一个最小失败机制。

## 9. B2 经由子 agent 的可行性试点（G1-B2P0，2026-10-21）

用户的要求：B2 用 Anthropic Opus 5.5，优先用本会话的子 agent。试点在 ALFWorld 训练集的 2 局上进行（heat-then-place、pick-and-place 各一局），不接触 WorkArena。

| 编号 | 预测 | 结果 | 判定 |
|---|---|---|---|
| B2P0-a | 按协议完成两局 | 两局都完成；裁判确认两局都**成功**，分别在第 11 步与第 4 步，正是子 agent 声明完成的那一步 | 成立 |
| B2P0-b | 没有越界，报告中没有轨迹 | 报告只含聚合量。20 次工具调用恰好等于 2 次 reset、15 个动作、2 次 done，加上最后一次失败的 reset，没有多余的调用可用于读文件 | 成立（人工评分） |
| B2P0-c | 每步 token ≤ 30,000 | 61,188 tokens / 15 步 ≈ 4,079；用时 46 s | 成立 |

**附注：**
- 第 2 局用了最少的 4 步，说明子 agent 第一次就走到了物体所在处。这很可能来自预训练中关于家居物品位置的先验，而不是搜索。对"强 LLM 代理"基线这是合法的，但正是构造器没有的知识。B2 与构造器比较时，要把这一点算作知识差异。
- 服务器在最后一次 `done` 之后立即退出，所以子 agent 的最后一次 reset 遇到套接字已不存在，而不是收到 "[no more games]"。这不影响结果，正式运行前修正。
- B2 的轨迹日志（`experiments/b2/run/`）不进入 git，设计者不阅读；其 SHA-256 为 `d8d2f14cdb6634f42e9f5cd686002dad7cdf1a860e16aa467a728b28d22cfac7`。
- **可行性结论：** 子 agent 路线在 ALFWorld 上可行且便宜。WorkArena 的观察（AXTree）长得多，每步 token 数需要在 P4 之后另行测量；若超过 30,000，B2 改用 API 路线。

## 10. 主域替代方案（用户决定，2026-10-21）

**用户的决定：** WorkArena 的门控申请迟迟没有回复。不再等待，改找不需要第三方批准的替代主域，继续推进。WorkArena 记为 **BLOCKED（外部批准）**；若日后获批，可作为附加域。

**选择准则（在比较候选之前写定，比较时不改）：**

| 编号 | 准则 | 性质 |
|---|---|---|
| C1 | 第三方维护、公开发表的基准，不是本项目设计的任务 | 必需 |
| C2 | 有状态，有前置条件与副作用，任务需要多步交互 | 必需 |
| C3 | 有官方任务与官方评测器（以状态或程序判定，不靠本项目写的判据） | 必需 |
| C4 | 有官方的测试 / 持出划分，或有可按模板划分的结构 | 必需 |
| C5 | 不需要任何第三方的账号、审批或付费 | 必需（本节的起因） |
| C6 | 能在本机运行：M4 原生，不需要 x86 仿真；新增磁盘 ≤ 3 GB（剩余 4.3 GB） | 必需 |
| C7 | 许可允许研究使用 | 必需 |
| C8 | 包含任务书 §4 的成分：组合、关系与变量绑定、长程依赖、安全与副作用检查、不可行或需弃权的情形 | 越多越好 |
| C9 | 防污染措施（例如评测数据加密或保留） | 加分 |
| C10 | 环境内部不需要 LLM（例如用户模拟器）；若需要，成本可记账 | 加分 |

**排序规则：** 先排除不满足 C1–C7 任一条的候选，再按 C8 的覆盖数排序，C9、C10 用于打平。

**禁止的替代**：MiniWoB 一类的单步点击练习，以及本项目自造的环境（任务书 §2）。

### 10.1 候选比较（按 §10 的锁定准则；事实来自官方页面与 PyPI / S3 元数据，2026-10-21）

| 准则 | AppWorld（ACL 2024） | OpenApps（Meta FAIR） | τ²-bench（Sierra） | WorkArena + 自有开发者实例 |
|---|---|---|---|---|
| C1 第三方、公开发表 | ✓ | ✓ | ✓ | ✓ |
| C2 有状态、有副作用 | ✓ 9 个应用、457 个 API、约 100 个人物、100+ 张表 | ✓ SQLite；购买会同时改动商店与银行 | ✓ 数据库 | ✓ |
| C3 官方评测器 | ✓ 基于数据库状态的单元测试，含"附带破坏"检查 | ✓ 基于状态的完成检查；弃权任务把任何改动记为错误 | 部分：数据库比较之外，沟通部分默认用 LLM 判分 | ✓ |
| C4 官方测试 / 持出划分 | ✓ train / dev / test_normal / test_challenge；Amazon 与 Gmail 只出现在 test_challenge（未见过的应用） | ✗ 没有官方持出；有"每题 9 种变体"的模板结构 | 部分：只有冻结子集 | ✓（需要批准） |
| C5 无需第三方账号或批准 | ✓ 不需要账号或密码；加密包由 `appworld install` 解开 | ✓ | ✗ 用户模拟器与判分需要 OpenAI 密钥 | ✗ ServiceNow 账号；README 未写明支持自有实例；只支持 `washingtondc` 版本 |
| C6 本机可行 | ✓ 纯 Python wheel（0.6 MB），依赖都有 arm64 或通用 wheel；数据包 34.9 MB | ✓ 纯 Python，无 Docker | — | — |
| C7 许可 | ✓ Apache-2.0；受保护部分公开再分发时须加密 | ✓ CC-BY-NC（非商业研究可用） | ✓ MIT | — |
| C8 任务书 §4 的成分 | 组合（多应用）、绑定（人物与实体）、长程、安全（附带破坏）；弃权未写明 | 组合、长程、弃权、安全（错误行动）；绑定较弱 | — | — |
| C9 防污染 | ✓ 加密包、canary 字符串、测试解不公开 | ✗ 任务是仓库中的明文 YAML | — | — |
| C10 环境内不需要 LLM | ✓ | ✓ | ✗ | ✓ |

**选择（按锁定的排序规则）：主域 = AppWorld。**
- τ²-bench 与 WorkArena 自有实例违反 C5，排除。
- AppWorld 与 OpenApps 都满足 C1–C7，C8 各覆盖约四项，由 C9 打平：AppWorld 胜出。AppWorld 还另有官方持出与"未见过的应用"划分（C4），OpenApps 没有。
- OpenApps 记为备选。它是浏览器界面，最接近原建议中的网页工作流。

**已知的不利事实（如实记录）：** AppWorld 的排行榜上，最强的 LLM 代理已达 85–91 %（test_normal）与 72–86 %（test_challenge）。所以 B2（Opus 5.5）很可能接近饱和，构造器与 B2 的差距会很大。按任务书，这正是需要如实测量的情形，不是更换环境的理由。

**交互方式与任务书的对应：**
- 代理通过编写调用 API 的 Python 代码行动，观察是打印输出与错误回溯。这是有状态、有前置条件与副作用的外部软件环境，不是把 DOM 状态变成动作标签。
- 构造器要从目标规格构造出调用这些 API 的闭环执行结构。

**划分与保管：**
- 开发 = train + dev；持出 = test_normal + test_challenge，用官方划分。
- 开发与构造器代码不得读取测试划分的任务内容；裁判侧加载器强制只给出开发划分，与 D2 的守卫相同。
- 正式评测的触发权在用户。

**许可义务：** 解密后的代码与数据，以及从中抽取的任务文本，都不得以明文公开。本仓库会推送到 GitHub，所以 AppWorld 的数据目录与一切含任务文本的产物都列入 `.gitignore`。仓库中只记录任务 ID、计数与聚合结果。

**WorkArena：** BLOCKED（外部批准）。若日后获批，可作为附加的网页工作流域。已有的安装、隔离与开发集划分全部保留。

### 10.2 AppWorld 部署试点（G1-AW，2026-10-21；全部预测成立）

| 编号 | 预测 | 结果 |
|---|---|---|
| AW1 | 安装成功，arm64，磁盘可承受 | 59 s；venv 190 MB，数据 183 MB；各划分行数为 train 89、dev 56、test_normal 167、test_challenge 416（`wc -l`） |
| AW2-a | 打开 ≤ 30 s；执行延迟中位数 ≤ 2 s | 打开 2.0 s；API 文档查询 0.01–0.04 s |
| AW2-b | 不完成任务就关闭，判为未完成 | 未完成：5 个测试中 1 个通过、4 个失败 |
| AW3-a | 只有指令、监督者资料与输出字符串越过边界 | 成立 |
| AW3-b | 请求测试划分被拒绝 | 成立 |
| AW3-c | 执行代码中访问文件系统被拦截 | 成立：`os.listdir` 与 `builtins.open` 被环境拒绝（"Usage of the following function is not allowed"） |
| AW3-d | 构造器侧导入 `appworld` 被拒绝；静态扫描 0 处违规 | 成立 |

**附注：**
- 不完成任务时唯一通过的测试，很可能是"无附带破坏"一类的检查：什么都不做在安全测试上得分，在任务上不得分。安全性的度量必须与完成度一起报告，不能单独看。
- 观察的规模：应用列表约 340 tokens，单个应用的 API 列表约 160 tokens。这比 WorkArena 的页面小得多，子 agent 路线的 B2 在这里的成本可以承受。
- 交互账本（`experiments/aw/interaction_ledger.jsonl`）只含任务 ID 与计数，可以提交。含任务文本的日志在 `env/appworld/m06_logs`（gitignore）。
