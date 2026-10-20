# Mission 03 证据索引

每条结论对应的原始文件。所有路径相对于 `mission-03/experiments/`。

| 结论 | 脚本 | 原始输出 |
|---|---|---|
| L1：查表解码器逐字节复现 16 个 A-LLM 程序 | `p0_leakage/run_leakage.py` | `p0_leakage/leakage.json`（`L1`）、`p0_leakage/run.log` |
| L2：通用仿射先验 23/25；加盒形定义域后 25/25 | `p0_leakage/run_leakage.py`、`p0_leakage/l2_closure.py` | `leakage.json`（`L2`）、`l2_closure.json`、`l2_closure.log` |
| L3：去掉单格探测，A-auto 仍为 10/16 | `p0_leakage/run_leakage.py` | `leakage.json`（`L3`） |
| P1 原判据：UA0 无一致守卫，UA2 超出预算 | `p1_composition/run_p1.py` | `p1_composition/run.log`（含停止记录） |
| P1 修正案 1：UA0 仍无一致守卫，UA2 超出预算 | `p1_composition/run_p1_amend1.py` | `p1_composition/run_amend1.log`（含停止记录） |
| P1 修正案 3–4：DEV 4/4，UA0 端到端 N = 3–11 通过 | `p1_composition/cond_fit.py`、`run_amend34.py` | `p1_amend34.json`、`run_amend34.log`；修正案 6 代码重跑：`p1_amend34_v6.json`、`run_amend34_v6.log` |
| 确认实验 v1：C0 超出预算，停止 | `p1_composition/run_confirm.py` | `confirm_tasks.json`、`run_confirm.log` |
| 确认实验（修正案 6）：6/6 | `p1_composition/run_confirm2.py` | `confirm2.json`、`run_confirm2.log` |
| `same`：16,434 个组合中唯一一致者，第三规模全对 | `p1_composition/run_t2.py` | `p1_t2.json`、`run_t2.log` |
| 概念发明：G-free 不可识别，G-region 唯一可识别；盒形先验推广失败 | `p1b_concept/run_concept.py` | `p1b_concept/concept.json`、`p1b_concept/run.log` |
| 协议、预测与 6 个修正案的提交顺序 | — | `git log mission-03`：协议提交早于先导实验；每个修正案都在相应结果之前单独提交 |
| ARC-AGI-1 公开任务的来源、许可与完整性（400 + 400 个任务，结构检查全部通过） | `arc_intake/manifest.py` | `../external/arc-agi-1/MANIFEST.json`、`../external/ARC_PROVENANCE.md` |
