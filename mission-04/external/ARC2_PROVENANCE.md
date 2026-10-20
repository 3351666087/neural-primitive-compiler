# ARC-AGI-2 公开评测集：来源、许可与访问记录

## 来源

| 项目 | 值 |
|---|---|
| 仓库 | https://github.com/arcprize/ARC-AGI-2 |
| 源提交 | `f3283f727488ad98fe575ea6a5ac981e4a188e49`（2025-05-15，下载时 `main` 的头提交） |
| 获取方式 | GitHub contents API 列出该提交下的 `data/evaluation/`，再从 `raw.githubusercontent.com/arcprize/ARC-AGI-2/<源提交>/…` 逐个下载；2026-10-20，经用户同意 |
| 收录内容 | `data/evaluation/` 的 120 个任务文件（共 1,364,679 字节）与仓库的 `LICENSE` |
| 未收录 | 训练集、README 与其他文件 |
| 修改 | 无 |
| 完整性 | 每个文件的大小与 git blob 哈希都与目录清单一致；结构检查全部通过：359 个训练对、167 个测试对（都带输出），没有多余的键。清单为 `arc-agi-2/data/evaluation/MANIFEST.json`，整体哈希 `8cd3ee83601d31d550187dd629f04dba67e3e58c2e9fb6f4272f04fff907ac13`；`LICENSE` 的 SHA-256 为 `8360699be7ffadd4b460e4287c1f7d0ada282518ee8e375fff603b1b3ecbb43f` |

## 许可

Apache License 2.0（GitHub API 报告的 `spdx_id` 为 `Apache-2.0`；许可证原文随数据保留在 `arc-agi-2/LICENSE`）。数据按原许可再分发，内容未修改。

## 独立性与污染风险

| 风险 | 程度 | 处理 |
|---|---|---|
| 任务由第三方设计，与本仓库的生成器、词汇与先验无关 | 有利 | 作为 Mission 04 的确认挑战 |
| 自 2025 年起公开，可能进入了 LLM 的预训练数据 | 中到高 | 被检验的方法不调用 LLM；结果不能作为"LLM 从范例中发现表示"的证据 |
| 方法的设计者（本会话）对 ARC-AGI-2 的难度有公开资料层面的先验 | 中 | 记录在 `CONFIRMATION_ARC2.md` 的预测说明中 |
| 只有公开评测集，没有隐藏的半私有集 | — | 承认它不是隐藏的；但在本次之前，本仓库从未读取过它 |

## 访问记录

1. 冻结在先：协议、运行脚本、学到的偏好与全部方法文件的哈希于提交 `5648e97` 记录，之后才下载任何任务文件。
2. 下载与校验时，本会话没有查看任何网格内容；校验脚本 `experiments/c1_arc2/intake.py` 只输出计数、编号与是否通过。
3. **一次操作失误**：下载校验之后，我误把 `confirm.py freeze` 又运行了一次，`freeze.json` 被重写。与提交 `5648e97` 相比，只有 `frozen_at` 时间戳变了，12 个文件的哈希完全相同。这说明从冻结到下载，没有任何被冻结的文件被改动。随后从该提交恢复了原文件。
4. 确认运行只由冻结的 `confirm.py confirm` 进行一次，运行前核对冻结哈希与本清单。
