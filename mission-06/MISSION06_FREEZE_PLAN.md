# MISSION06_FREEZE_PLAN（Gate 1 冻结，2026-10-21）

本文件规定在任何开发结果出现之前冻结的一切。冻结之后，改动只能以带日期的修正追加，并在 `EXPERIMENT_PRE_REGISTRATION.md` 中登记。草案阶段的版本见 git 历史（提交 `53ac6b8` 至 `8c55b88`）。

**Gate 1 的判定：通过。** 主域（AppWorld）与异质域（ALFWorld）都已部署、隔离、试点并划分。原主域 WorkArena++ 因第三方批准迟迟未到而 BLOCKED（用户决定不等待），其安装、隔离与开发 / 持出划分全部保留，获批后可作为附加的网页工作流域。

**用户决定一览：**

| 编号 | 决定 |
|---|---|
| D1 | WorkArena：用户申请门控实例池（未获回复，BLOCKED） |
| D2 | 主动探索视为研究：只在开发集、只用开发种子、每次运行登记上限、不训练权重；由裁判侧代码强制 |
| D3 | ALFWorld 下载：已完成 |
| D4 | B2：Anthropic Opus 5.5，经由本会话的子 agent |
| D5 | WorkArena 的持出由隔离会话保管：已完成，125 个持出族 |
| 工作模式 | 下载、编辑、删除、终端、阶段推进、推送与合并都自主进行，事后报告（见记忆 `autonomous-workflow`） |

## 1. 环境与版本

| 项目 | 主域：AppWorld | 异质域：ALFWorld 文本版 | 附加（BLOCKED）：WorkArena++ |
|---|---|---|---|
| 代码 | `appworld` 0.1.3.post1（wheel sha256 前缀 `db77f80039825023`） | `alfworld` 0.4.2、`textworld` 1.6.2（arm64 wheel）、`fast-downward-textworld` 20.6.4 与 `jericho` 3.3.1（本机编译，不装 spaCy） | `browsergym-core` 0.14.3、`browsergym-workarena` 0.5.3、`playwright` 1.44.0、Chromium 125（build 1117，sha256 `e708fe89…`） |
| 数据 | `data-0.2.0.bundle`（S3，34,908,601 字节，ETag `e879e1fc…-5`） | `json_2.1.1_json.zip`（sha256 `25171f16…`）、`json_2.1.3_tw-pddl.zip`（sha256 `5df77ea7…`） | 门控实例池（未获批准） |
| 解释器 | CPython 3.12.13 arm64（uv） | 同左 | 同左 |
| 位置 | `env/venv-aw`；数据 `env/appworld`（gitignore：许可禁止明文再分发） | `env/venv-alf`；数据 `env/alfworld-data`（gitignore） | `env/venv-wa`、`env/ms-playwright` |
| 安装记录 | `env/appworld_install.txt`、`appworld_pip_report.json` | `env/alfworld_install.txt`、`alfworld_pip_report_*.json`、`alfworld_data_sha256.txt` | `env/workarena_install.txt` 等 |

## 2. 划分与持出保管

| 域 | 开发 | 持出 | 保管 |
|---|---|---|---|
| AppWorld | train（89）+ dev（56），按 `wc -l` 计 | test_normal（167）+ test_challenge（416）；后者含开发中未出现的应用 | 官方划分；裁判侧加载器只放行开发 ID（`experiments/aw/aw_judge.py`，G1-AW3-b 已测）；测试任务的内容与标准答案只在裁判侧 |
| ALFWorld | train（3,553 局）与 valid_seen（140 局） | valid_unseen（官方的未见房间） | 只解压了开发部分；valid_unseen 仍封存在压缩包里（解压出的文件数为 0） |
| WorkArena++ | 216 个工作流族（23 个桶）+ 33 个 L1 任务；种子 ≥ 10 | 125 个工作流族（19 个桶）；正式评测用种子 0–9 | 隔离会话保管 `heldout.json`（只读）；本会话只持有 `dev.json`（哈希已核对） |

**开发集的标准答案：** AppWorld 公开 train / dev 的解法与测试，ALFWorld 的游戏目录中有专家计划。它们只放在裁判侧，不作为构造器的输入。设计者只在事后诊断中查阅，并标为 POST-HOC。

## 3. 隔离

- **进程分离：** 环境、任务对象、评测、标准答案、合法命令列表、奖励与完成标志都在裁判进程。构造器进程只收到合法观察：
  - AppWorld：指令、监督者资料、执行输出；
  - ALFWorld：文本观察；
  - WorkArena：BrowserGym 的观察键。

  三者都已由试点验证。
- **构造器进程中的导入钩子**拒绝 `appworld`、`alfworld`、`textworld`、`browsergym.workarena` 以及各裁判模块。另有静态扫描。
- **AppWorld 自带的执行沙箱**拦截文件系统访问（G1-AW3-c）。
- **交互账本：** `experiments/aw/interaction_ledger.jsonl` 与 `experiments/g1/interaction_ledger.jsonl`，只含 ID 与计数。
- **特权消融单列**：ALFWorld 的 `admissible_commands`、AppWorld 的 `expose_internals` 等，若要使用，作为明确标注的特权条件单独报告。
- **触发权：** 正式持出评测（Gate 4）由用户触发，只运行一次；冻结提交与哈希先于读取。

## 4. 基线

| 编号 | 内容 | 状态 |
|---|---|---|
| B1 | 同库的经典方法：AppWorld 上为程序搜索 / HTN 风格的组合器，ALFWorld 上为 PDDL 风格的规划器。同技能、同观察、同预算，记录搜索 CPU 与知识库成本 | Gate 2 起由本会话实现；所用知识不得弱于构造器 |
| B2 | Opus 5.5，经由本会话的子 agent（D4）。观察与动作同构造器；只报告聚合量；轨迹留在裁判侧，设计者不读 | ALFWorld 可行性已验证（G1-B2P0） |
| B3 | 消融：去证书、去发现的规律、去记忆、去恢复、去抽象、去神经后端 | 本会话实现 |
| B4 | 官方公开结果：AppWorld 排行榜（例如 GPT-4o ReAct 48.8 / 30.2 TGC；最强代理 85–91 / 72–86）；ALFWorld 论文 | 只作参照，写明语义、硬件与知识的不可比之处 |

## 5. 预算

| 项目 | 上限 |
|---|---|
| Gate 2 | 本机 CPU 4 h；AppWorld 每次运行的执行次数事先登记（默认 ≤ 300），合计 ≤ 3,000 次；ALFWorld 每局 ≤ 50 步 |
| Gate 3 | 本机 CPU 8 h；AppWorld 执行合计 ≤ 8,000 次 |
| Gate 4 | 每个任务 ≤ 50 次执行或动作 |
| B2（子 agent） | 默认每个 Gate 合计 ≤ 3,000,000 tokens，每个任务 ≤ 50 个动作；按子 agent 报告的 token 数记入 `experiments/b2/cost_ledger.jsonl`。用户未给出具体上限，此为本会话设的默认值，用户可随时改 |

超出预算即记 RESOURCE_LIMIT，保存部分结果。

## 6. 失败时的处理

- 环境不可用：BLOCKED，并记录原因；不换成简单的点击练习或自造环境（任务书 §2）。
- 结果不好：不改科学目标、不改阈值；只能以新修正与新预测继续。
- 测量工具的缺陷（如 G0-M1）：按锁定判定报告，另做 POST-HOC 诊断，在下一次修正中修复。

## 7. 知识与污染

见 `KNOWLEDGE_PROVENANCE.md`。要点：
- AppWorld（2024）与 ALFWorld（2020）的论文与公开文档可能在本会话的预训练中。
- AppWorld 的任务内容加密分发，测试解法不公开，本会话没有读过任何测试任务。
- B2 的预训练先验（例如家居物品的位置）是相对构造器的知识差异，比较时单独记账。
