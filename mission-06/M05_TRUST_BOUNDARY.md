# Mission 05 的可信基：独立复核、oracle 剥离与反例搜寻（Mission 06 Gate 0）

预注册：`EXPERIMENT_PRE_REGISTRATION.md` §G0（锁定 `c0f23d8`），修正案 G0-1；代码先于结果提交于 `100e8fe`。评分：`experiments/g0/score_g0.py` → `g0_scores.json`。

## 1. 逐字段信息流（G0-T1）

```
                         CONSTRUCTOR SIDE（构造器侧）                                    JUDGE SIDE（裁判侧）
  lib/model.py ─┬─> g3/dsl.py (select_dsl)                                      judge/env.py
  (宏模型:选择、  │        │                                                       ├─> cir_interp.py (J1-sym, J2)
   交换、可满足)  │        ├─────────────> g3/truth.py ──[applicability_cex]──┐      ├─> net_loop.py   (J1-net)
                │        │               (N = 3..7 穷举，                    │      ├─> instances.py  (V_train, V_unseen, V_mc6)
                │        │                只导入构造器侧模块)                  │      └─> feasibility.py
                │        │                                                  ▼
                │        └─> g3/z3_dsl.py ─> r7/zplus.py ─> r8/zpp.py ──> 表 {damage, progress, preserves}
                │                (Z3：损伤、保持、下降)          progress.ok = 下降已证 ∧ applicability_cex is None
                │                                                          │  （标签 "TZ"）
                │                                                          ▼
                │                                         g3/construct.py：A-P / A-P′（只读表）
                │                                                          │  计划 [(原子, 规格)]
                │                                                          ▼
                └──────────────────────────────> g3/cir_dsl.py → lib/cirgen.py → CIR ──> lib/compile_cir.py → IF 网络
                                                                                   │                     │
                                                                                   ▼                     ▼
                                                                         J1-sym, J2（CIR 解释器）   J1-net（抽样锁步）
```

由静态扫描（AST）与动态访问日志确认：

1. 构造器路径上读取的真值**值**只有 `applicability_cex`，读者只有三个表构造函数：`a_dsl.a_tables`、`zplus.a_tables_plus`、`zpp.a_tables_pp`。它们另外读取 `preserves` 的键（由原子决定的模式列表，不含真值）。
   - 动态日志：三者只访问 `<instance> / applicability_cex` 与 `<instance> / preserves / <键>`。
2. `construct.py`、`cir_dsl.py`、`compile_cir.py` 与 B 的学习器都不读取任何真值字段。
   - 以 N ≤ 5 的真值建表后，把裁判的全部入口替换成抛异常的函数，再运行 A-P 与 A-P′：98 个目标中构造 59 个，**裁判调用 0 次**。
3. `truth.py` 没有标注所属侧，只导入构造器侧模块。所以"真值"是构造器自己的宏模型的有界穷举，与裁判的环境无关。Mission 05 中"0 个危险条目"一类的可靠性数字，衡量的是 Z3 编码与宏模型的一致性。
4. 裁判侧模块不导入任何构造器代码，与 Mission 05 的声明一致。但 `construct.py` 在模块层导入了裁判模块（`cir_interp`、`instances`），供其中的 `judge_plan` 使用。构造与判定在同一个模块、同一个进程里，分离靠约定，不靠进程或权限。上面第 2 条的动态测试表明，构造函数实际上没有调用裁判。
5. Mission 06 的新模块中，标为 CONSTRUCTOR SIDE 的（`app_r.py`、`concretize.py`）不导入真值或裁判模块（静态检查：0 处违规）。

## 2. 证据等级地图（每条声称）

| 环节 | Mission 05 的说法 | G0 之后的等级 | 依据 |
|---|---|---|---|
| 交换引理（搬运 = 交换内容） | 手证 [P] | [P]（手证）；在环境中的实现见 G0-M1 | §5 |
| 损伤上界、两两保持、进度的下降部分 | Z3 对一切 N 证明 | [P]，相对于手写编码；编码与宏模型的一致性 [M]（N ≤ 7） | Mission 05 |
| 进度的适用性部分 | 修正案 3 称为"计数引理 [P]"；代码用 N ≤ 7 的真值 | Mission 05 实为 [M]。G0：见 §3 | G0-A1..A5 |
| 组合引理（优先级组合的终止与正确性） | Z3 [P]（L1，m ≤ 5） | 不变 | `judge/j2.py` |
| A-P′ 的共享势函数论证 | — | 资源检查只覆盖 N ≤ 15、K ≤ 7（算术检查） | `construct.py` |
| 规格 → CIR（选择的编译） | 由 J1/J2 的结局间接检验 | 见 G0-M1 | §5 |
| CIR → 网络（compile_cir） | 抽样锁步 [E] | 类 C_K 上 [P]（T-K：手证 + Z3 引理 + 逐网络前提检查）；见 §4 | G0-K1、K2 |
| 控制器在环境中的成功 | J1-sym（N ≤ 15，抽样）、J2（N = 6 穷举） | [E] / [M]；规模外见 §6 | G0-S1、S2 |

（§3–§7 在结果之后填写。）
