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

## 4. 冻结文件与只追加记录中的数字勘误

Gate 6 由一个独立的复核代理把各文档中的数字与结果 JSON 逐条对照（约 640 条）。非冻结文档中的不一致已直接更正。`G4_PILOT_RESULTS.md` 在冻结清单中，改动它会使 `custody.frozen()` 失败；`GPU_RESOURCE_DECISION.md` 与 `GPU_SESSION_LEDGER.md` 只追加。这些文件中的错误在此更正，原文不改：

| 文件与位置 | 原文 | 更正 | 出处 |
|---|---|---|---|
| `G4_PILOT_RESULTS.md` §4 表，k = 16 一行 | AUROC 0.82–0.84，AUPRC 0.32 | AUROC 0.82–0.83，AUPRC 0.31–0.32 | `results/g4/selection.json` `B3_k.per_proxy.16` |
| 同表，B4 一行 | 与 1 只差 0.0001 | 与 1 只差约 0.00001 | `B4_C.mean_ll_gain` |
| §4 读法第 3 条 | 模型的互惠比例从 0.07（γ = 1）升到 0.15 | 从 0.07–0.08 升到 0.15–0.16 | `R1_gamma.fits[].model_reciprocity` |
| §4 第 4 条后的读法 | 成年上的增益略大（+0.008 → +0.010–0.012） | +0.008 → +0.010–0.011 | `results/g4/ablation_selected.json` |
| §5 资源 | 开发累计约 4.5 核时 | 约 4.3 核时（有记录的 3.94 加上估计的约 0.4） | `results/g3`、`results/g4` 的 `cpu_s` |
| `GPU_RESOURCE_DECISION.md` D3、`GPU_SESSION_LEDGER.md` 第 2 行 | 开发累计约 4.5 核时 | 约 4.3 核时（同上）；判定不受影响 | 同上 |

这些错误都不影响任何判据或判决（判决只读 `results/g5/*.json`）。
