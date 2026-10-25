# Mission 08 Gate 5：干预与偏离记录

冻结：`FREEZE_MANIFEST.sha256`（50 个文件），提交 26a41b9，2026-10-25T04:29Z 生成并推送到 `origin/mission-08` 之后，裁判才读取任何留出数据。每个裁判的结果文件都记录了运行时的提交号（`commit` 字段）与输入文件的哈希；`src/m08/custody.py` 在每次读取留出数据之前重新核对清单中的全部哈希。

## 1. 重跑

| 裁判 | 次数 | 原因 | 类型 | 影响 |
|---|---|---|---|---|
| T4（`experiments/g5_t4.py`） | 第 1 次失败 | `fig4_T4_vm_gfp.npy` 下载不完整（3,122,408 / 3,168,128 字节，`ContentTooShortError`）；`fig3_T4v.npy` 已完整下载，MD5 与 Edmond 列表一致 | 基础设施重跑 | 失败发生在任何计分之前；日志保留为 `run/g5_t4_attempt1_download_incomplete.log`；不完整的文件被删除（冻结的代码遇到已存在的文件时只核对 MD5，不重新下载） |
| T4 | 第 2 次失败 | 沙箱代理下的 TLS 错误（`SSL: UNEXPECTED_EOF_WHILE_READING`） | 基础设施重跑 | 同上，没有计分；日志 `run/g5_t4_attempt2_ssl_eof.log` |
| T4 | 第 3 次完成 | 在终端标签页（不经沙箱代理）运行同一冻结代码 | — | 三个文件的 MD5 都与 Edmond 列表一致，SHA-256 记录在 `results/g5/t4.json` |
| 结构、功能 | 各 1 次 | — | — | 没有重跑 |

## 2. 冻结之后的分析（不进入判决）

| 文件 | 内容 | 原因 |
|---|---|---|
| `experiments/g5_posthoc_t4.py` → `results/g5/posthoc_t4.json` | GFP 与 GluClα RNAi T4 细胞的静息电位、PD 与 ND 峰值、DSI 的四分位数 | T-d 的实测部分方向与预期相反，需要说明是哪一部分造成的。标为事后描述，不改变 T-d |

## 3. 已知的偏离

1. **F-e 的区间没有计算。** §3.2 要求 F-e"报告差值与区间"；冻结的功能裁判只计算了两个品系上 A-real 相对 A-none 的 AUPRC 增益之差（点估计），没有区间。由于两个品系上 A-real 都远低于 A-none（增益 −0.276 与 −0.195），这一比较在 F-a 不成立时没有解释价值，因此不事后补算；如实记为偏离。
2. **T-d 对照组的选择。** 作者在图 4 中只保留有输入电阻数据的 GFP 细胞；我们按预注册使用所有有电压记录的 GFP 细胞（33 个）。冻结之前已经记录（`DATA_SPLITS_AND_CUSTODY.md` §4）。
