# G3 生成者说明（冻结时随协议一起计算哈希）

> 本文件原样交给一个**独立会话**。该会话使用全新的上下文，只在指定的新文件夹中工作，不读取本仓库。

---

你的任务是为一项研究生成一组**隐藏的评测项**。请只在指定的新文件夹中工作，不要读取或打开其他项目（尤其是 `neural-primitive-compiler`），也不要在网上查找与之相关的内容。

## 1. 环境 LINE

- 一行 N 个格子（N 从 3 到 15）。每个格子或为空，或放着一个颜色为 1–4 的物体；同一颜色可以有多个物体。
- 有些空格子是**危险格**。一个带夹子的代理在格子之间移动，可以拿起或放下物体。
- **目标原子**：
  - `ORDER(c1, c2)`：每个颜色 c1 的物体都在每个颜色 c2 的物体左边；
  - `ZONE(c, side, w)`：每个颜色 c 的物体都在最左（`side = left`）或最右（`side = right`）的 w 个格子内，w 为 2 或 ⌊N/2⌋；
  - `GROUP(c)`：颜色 c 的物体占据一段连续的格子（没有或只有一个也算成立）。
- **安全约束**：
  - `NO_DROP_HAZARD`：不得把物体放在危险格上；
  - `NO_PICK(c)`：不得拿起颜色 c 的物体。

## 2. 达成器与 ACH-DSL

**达成器**是针对一种原子的策略：当原子不成立时，它选出一个**目的格 d** 与一个**来源格 s**（s 放着原子颜色的物体），然后由固定的搬运宏交换二者的内容。s 上的物体移到 d；若 d 原来有物体，该物体经由一个空余格最终到 s。原子成立时不移动。

达成器用 JSON 描述：

```json
{"id": "字符串（不要以 LIB- 开头）",
 "atom_type": "ORDER" | "ZONE" | "GROUP",
 "side": "left" | "right" | "any",
 "dest":   {"types": [...], "region": REGION, "pick": PICK},
 "source": {"types": ["OWN"], "region": REGION, "pick": PICK 或 "nearest_to_dest"}}
```

- `side` 只用于 ZONE，省略时为 `any`。`left` 表示只用于左侧区域的原子，`right` 同理。
- 字段只能是上面这些，另外可以有一个说明字段 `note`。

**格子类型**（相对于原子而言）：
- `OWN`：原子的颜色（ORDER 中为 c1）；
- `PARTNER`：ORDER 原子的第二种颜色 c2；
- `OTHER`：其他颜色、且可以被拿起（不受 NO_PICK 约束）的物体；
- `EMPTY`：可以放下物体的空格。有 NO_DROP_HAZARD 时不含危险格；没有时，所有空格都算。

`dest.types` 是 {`EMPTY`, `PARTNER`, `OTHER`} 的非空子集，其中 `PARTNER` 只用于 ORDER。`source.types` 必须恰好是 `["OWN"]`。

**REGION**：
- `"ALL"`：全部格子。
- `"ZONE"` 与 `"NOT_ZONE"`：原子的区域及其补集（只用于 ZONE 原子）。
- `"WINDOW_G1"`、`"NOT_WINDOW_G1"`、`"WINDOW_G2"`、`"NOT_WINDOW_G2"`：OWN 颜色的**窗口**及其补集，可用于任何原子。
  - 窗口长度 c 等于 OWN 物体的个数。
  - 一段长度为 c 的格子若其中每一格都既不是危险格（有 NO_DROP_HAZARD 时），也不是其他颜色中受 NO_PICK 约束的物体，则称为可用的一段。
  - G1 取起点最左的可用段，G2 取起点最右的可用段；没有可用段时窗口为空。
- `"LEFT_OF_DEST"`、`"RIGHT_OF_DEST"`：在 d 的左边或右边，只用于 source。
- `{"within": k, "of": "DEST"}`：与 d 的距离不超过 k（1 ≤ k ≤ 3），只用于 source。
- `{"and": [REGION, REGION]}`：两个区域的交，最多嵌套两层。

**PICK**：
- `"leftmost"`、`"rightmost"`、`"second_leftmost"`、`"second_rightmost"`：在区域内、类型属于 `types` 的格子中，取最左、最右、左数第二或右数第二的一个。
- source 还可以用 `"nearest_to_dest"`：取离 d 最近的一个，距离相同时取左边的。

**执行顺序**：先选 d，再选 s（s 的区域可以引用 d）。以下情况达成器不移动：任一规则找不到格子；原子的某个颜色受 NO_PICK 约束。

## 3. 你要做的

1. 自己设计并写出 **30 个达成器**，每种原子类型（ORDER、ZONE、GROUP）至少 8 个，彼此不同。
   - 尽量用到语言中的每一种构造：每种 PICK、每类 REGION（包括 `and` 与 `within`）、各种类型组合。
   - 大多数应当是你认为能从任何"原子不成立"的状态出发，最终达成该原子的设计。也可以包括一些你认为有风险或会失败的设计。
2. 鼓励你写自己的模拟程序来检验这些设计，但不要求。
3. 写出文件：
   - `achievers.json`：`{"specs": [ ... 30 个达成器 ... ]}`；
   - `metadata.json`：`{"<id>": {"intended": "achieves" | "risky" | "fails", "notes": "..."}}`，记录你对每个设计的预期；
   - `MANIFEST.json`：两个文件各自的 SHA-256，以及整体哈希。整体哈希是字符串 `"achievers.json:<sha256>\nmetadata.json:<sha256>\n"` 的 SHA-256。
4. 向研究会话报告时，**只给出整体哈希与每种原子类型的达成器个数**。在研究会话告诉你冻结已完成之前，不要描述任何达成器、设计思路或元数据。
