# Mission 08 Gate 5：资源账本

所有确认运行都在本机 CPU 上完成（Apple M4，10 核，16 GB）。CPU 时间取自各结果文件的 `cpu_s`（进程用户 + 系统时间，含子进程），峰值内存取自 `peak_rss_mb`。

## 1. 确认运行（冻结提交 26a41b9）

| 运行 | 结果文件 | CPU 秒 | 墙钟秒 | 峰值内存 MB |
|---|---|---|---|---|
| 结构裁判（≥ 1 个突触，自助法 2,000 次） | `results/g5/structure.json` | 924.5 | 927.2 | 812 |
| 结构敏感性分析（≥ 3 个突触） | `results/g5/structure_min3.json` | 823.0 | 823.8 | 845 |
| 线虫功能裁判 | `results/g5/function.json` | 387.4 | 388.1 | 180 |
| T4 裁判（第 3 次；前两次下载失败，未计分） | `results/g5/t4.json` | 0.1 | 9.4 | 57 |
| T4 事后描述 | `results/g5/posthoc_t4.json` | 0.04 | 0.05 | 64 |
| 判决映射 | `results/g5/verdict.json` | < 1 | < 1 | — |
| **合计** | | **约 2,136 秒 = 0.59 CPU 核时** | | |

上限 40 CPU 核时（`PRE_REGISTRATION.md` §9）。

## 2. 全任务累计

| 阶段 | CPU 核时 | 说明 |
|---|---|---|
| Gate 3 | 1.91 | 有记录（`results/g3/*.json`） |
| Gate 4 | 2.03 + 约 0.4 | 有记录的部分加上中止或被覆盖的空跑 |
| Gate 5 | 0.59 | 本表 |
| **合计** | **约 4.9** | 开发 ≤ 24、确认 ≤ 40 |

## 3. GPU 与费用

- GPU：**未使用**。全程 `CPU_ONLY`；判定 D1、D2、D3 都是 `CPU_CONTINUE`（`GPU_RESOURCE_DECISION.md`），没有提出过开机申请。
- 费用：0 元。没有创建、开启或续用任何付费实例。

## 4. 存储与网络

- 下载的原始数据 `data/raw/` 共 114 MB（含冻结之后下载的 T4 记录 13.1 MB 与解压的 Brittin 接触 XML），不提交 Git。
- 本机磁盘剩余 1.7 GiB（2026-10-25，Gate 5 结束时）。
