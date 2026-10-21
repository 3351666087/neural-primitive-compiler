# 保管人报告与核对（G1-S；2026-10-21）

保管人会话（"Mission 06 held-out custodian"）以全新上下文启动，唯一的指令是 `CUSTODIAN_BRIEF.md` 原文（SHA-256 `d98cdaa47165d80f2d2b27942cf116e353ea8268e0ec0ba84d3f0691623ed249`）。工作目录为 `/Users/null3351/Code/m06-custodian`，位于研究仓库之外。研究会话只读取了它的最终报告，没有读取它的命令输出。

## 报告原文（第三步打印的 JSON）

```json
{
 "MANIFEST_overall_sha256": "8dc8ce29e1197f7666417a1aee9ed1d156752a742d268bbb1cce9564bf2a94eb",
 "dev.json_sha256": "d8f892f5e70cb8e3e2d924059a61c440bc62bf0757324049f468c7669047e1ec",
 "counts": {
  "planning_and_problem_solving": {"dev_families": 41, "heldout_families": 25, "dev_buckets": 4, "heldout_buckets": 3, "heldout_fraction": 0.379},
  "information_retrieval": {"dev_families": 25, "heldout_families": 14, "dev_buckets": 5, "heldout_buckets": 3, "heldout_fraction": 0.359},
  "data_driven_decision_making_and_reasoning": {"dev_families": 100, "heldout_families": 56, "dev_buckets": 7, "heldout_buckets": 6, "heldout_fraction": 0.359},
  "sophisticated_memory": {"dev_families": 15, "heldout_families": 13, "dev_buckets": 2, "heldout_buckets": 4, "heldout_fraction": 0.464},
  "contextual_understanding_infeasible_tasks": {"dev_families": 35, "heldout_families": 17, "dev_buckets": 5, "heldout_buckets": 3, "heldout_fraction": 0.327},
  "total": {"dev_families": 216, "heldout_families": 125, "l1_atomic_dev": 33}
 },
 "tool_sha256": "98ed945ad4f6a7daf657d3abe244b060b70378309272e0ca71c2d68344591720"
}
```

文件大小：`MANIFEST.json` 1,262 字节，`dev.json` 78,134 字节，`heldout.json` 44,681 字节（只读）。

## 核对

| 项目 | 结果 |
|---|---|
| 工具哈希与冻结值一致 | 是 |
| 自测通过 | 是（保管人报告） |
| 开发 + 持出 = 341；L1 = 33 | 216 + 125 = 341；33 |
| S-a：每类持出比例 ∈ [0.30, 0.52] | 0.327–0.464，**成立** |
| S-b：总持出族数 ∈ [107, 148] | 125，**成立** |
| S-c：不联网、不接触实例 | 由工具构造保证（`HF_HUB_OFFLINE=1`，只读包内登记表），没有独立的网络监控；记为"按构造" |

## 之后

- `dev.json` 进入仓库之前，要核对其 SHA-256 等于 `d8f892f5e70cb8e3e2d924059a61c440bc62bf0757324049f468c7669047e1ec`。
- `heldout.json` 留在保管人目录中，Gate 4 时由用户决定交给裁判，并核对 `MANIFEST.json` 中记录的哈希。

## dev.json 入库（2026-10-21，经用户批准）

- 只复制了 `/Users/null3351/Code/m06-custodian/dev.json`，放到 `mission-06/external/workarena_split/dev.json`；未接触 `heldout.json`。
- 读取之前核对 SHA-256：`d8f892f5e70cb8e3e2d924059a61c440bc62bf0757324049f468c7669047e1ec`，与保管人报告一致。
- 内容与报告一致：
  - 216 个开发族，各类别为 41 / 25 / 100 / 15 / 35，分别在 4 / 5 / 7 / 2 / 5 个桶中；
  - 33 个 L1 原子任务；
  - 每个族都有 L2 与 L3 的 ID；
  - 没有种子或其他持出字段。
