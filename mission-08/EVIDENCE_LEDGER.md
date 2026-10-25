# Mission 08 证据账本

每一行是一条可单独核对的结论：内容、等级、数据、出处文件与字段。等级见 `SCIENTIFIC_VERDICT.md` 文件头；"开发"指 `DATA_SPLITS_AND_CUSTODY.md` 的开发数据，"确认"指冻结（提交 26a41b9）之后的留出数据。

## 1. 复现与接口

| # | 结论 | 等级 | 数据 | 出处 |
|---|---|---|---|---|
| R1 | 两只成年个体（W7、W8）在 180 个共同神经元上各有 1,933 个有连接的有序对、共有 1,279 个，与 Richter & Schneidman 一致 | [REP] | Witvliet 7、8 | `G3_BASELINE_REPRODUCTION.md` §0；`tests/test_loader.py` |
| R2 | 独立实现的 R1（W7 训练、W8 测试）：Cook 13 类 AUROC 0.777、推断 8 类 0.793（论文 0.78、0.81）；40 × 40 网格与 10 × 10 网格差 < 0.0002 | [REP]，开发 | 同上 | `results/g3/structure_dev_grid10.json`、`structure_dev_positive_grid40.json` |
| R3 | R1 的步内顺序与论文的递推只差 S⁺ → S⁺(1 − S⁻)；二元组模型在 γ = 1 时与单元模型逐对相同（误差 < 10⁻¹²） | [P]（代数）+ [M]（数值检验） | 无 | `src/m08/rs.py`；`tests/test_rs.py` |
| R4 | 三时期 R1 重现文献的发育密度轨迹 | [REP]，开发 | Witvliet 1、3、5–8 | `G3_BASELINE_REPRODUCTION.md` §1.4 |
| R5 | Randi 图谱的读取与 Source Data 图 2a 在 6,092 个开发格中 5,836 个逐值相同；按路径长度的功能连接比例与作者图 2e 同一趋势 | [REP]，开发 | Randi 2023 | `results/g3/function_dev.json` |
| R6 | T4 结构轴与 flyvis 文献偏好方向共线（偏差 1.6–17.7°） | [E]，开发 | flyvis 连接组 | `results/g3/t4_dev.json` |

## 2. 结构（G-STRUCT）

| # | 结论 | 等级 | 出处 |
|---|---|---|---|
| S1 | R1 的对数似然增益在 4 / 4 个留出个体上高于距离模型 B1（+0.015 至 +0.029 比特 / 对，区间都不含 0） | [E]，确认 | `results/g5/structure.json` diffs `R1-*-vs-B1` |
| S2 | B3（推断 16 类）在 4 / 4 个留出个体上高于 B1（+0.051 至 +0.058） | [E]，确认 | diffs `B3-vs-B1` |
| S3 | C(记忆, R1) 与 C(记忆, B3) 的对数似然在 4 / 4 个留出个体上高于 C(记忆, ER) | [E]，确认 | diffs `C(*)-vs-C(*,ER)` |
| S4 | 以记忆本身为参照：C(记忆, R1) 3 / 4（W2 区间含 0），C(记忆, B3) 4 / 4 | [E]，确认 | diffs `C(*)-vs-M2/M4` |
| S5 | 三种类型级先验（R1、B3、K1）都提高记忆的 AUPRC，四个个体全部区间不含 0（+0.019 至 +0.082） | [E]，确认 | diffs `*-auprc` |
| S6 | C(记忆, ER) 在 W2、JSH 上比记忆差（−0.023、−0.054）：修正案 A2.1"只会更严格"的说法在这两个目标上错误 | [E]，确认 | diffs `C(M2,ER)-vs-M2` |
| S7 | 规则单独的增益是记忆的 17–28 %（S-b 0 / 4） | [E]，确认 | `results/g5/verdict.json` |
| S8 | 三时期 R1 在 W2、W4 上不如年龄内插记忆（S-d 不成立） | [E]，确认 | diffs `R1-dev-vs-M2` |
| S9 | N2U 上规则保留开发代理任务增益的 92 %，记忆 81 %（S-e 成立） | [E]，确认 | `verdict.json` S-e |
| S10 | ≥ 3 个突触时成年 N2U 上的增益消失（R1 +0.0006，K2 −0.0014） | [E]，确认（敏感性） | `results/g5/structure_min3.json` |
| S11 | R1 与 Cook 块模型 B2 的预测秩相关 0.95–0.98 | [E]，确认 | secondary.family_spearman |
| S12 | 98–99 % 的化学连接落在同一动物有膜接触的对上（只占 31–32 % 的对）；log 接触 AUROC 0.93–0.94 | [E]，确认（接触条件） | contact_condition |
| S13 | 互惠：目标 0.19–0.22（密度² 的 105–171 倍），R1 0.04–0.07 | [E]，确认 | secondary.reciprocity |
| S14 | γ 从 1 到 15 不改善单边似然（0.0338 → 0.0337），互惠从 0.07–0.08 升到 0.30–0.32 | [E]，开发 | `results/g4/selection.json` |
| S15 | 同一动物的双侧镜像预测（AUPRC 0.44–0.56）弱于跨个体记忆（0.62–0.67） | [E]，确认 | secondary.mirror_bound |
| S16 | (β₀, S⁻) 在 1 % 似然带内完全不可辨识；似然比 1.92 带内 S⁻ ∈ [0.01, 0.045] | [E]，开发 | ambiguity_proxies |
| S17 | 只用独立特征的 K1 达到 B3（8 类）增益的 39 %（失败线 40 %），16 类时约 28 % | [E]，开发 | `results/g4/pilot.json`、`selection.json` |

## 3. 功能（G-FUNCTION）

| # | 结论 | 等级 | 出处 |
|---|---|---|---|
| F1 | 线虫留出列：A-real AUPRC 0.108，A-er 0.091（差的区间含 0），A-rewire 0.088，A-none 0.384 | [E]，确认 | `results/g5/function.json` |
| F2 | 加入缝隙连接后 A-er（0.131）不低于 A-real（0.125） | [E]，确认 | secondary |
| F3 | 逐次 ΔF/F 的分半可靠性 0.17（WT）、0.15（unc-31） | [E]，确认 | split_half_reference |
| F4 | 开发列上，Creamer 式拟合支持集模型对真实与随机支持集无区分力 | [E]，开发 | `G3_BASELINE_REPRODUCTION.md` §2 |
| T1 | T4：四个亚型的预测 DSI 为正、镜像为负；33 个细胞实测 DSI 全部为正（T-a） | [E]，确认 | `results/g5/t4.json` |
| T2 | 预测 DSI（0.021）比实测中位数（0.286）小一个数量级（T-b 不成立） | [E]，确认 | 同上 |
| T3 | RNAi 细胞峰值 DSI 0.409 高于对照 0.343（T-d 实测部分相反） | [E]，确认 | 同上 |
| T4 | RNAi 细胞静息电位高约 7.6 mV，PD、ND 峰值都较小 | [POST-HOC] | `results/g5/posthoc_t4.json` |

## 4. 未知与未检验

| # | 内容 | 等级 |
|---|---|---|
| U1 | 规则生成的结构是否携带功能信息（F-c） | [U]：依赖未满足 |
| U2 | 由功能约束选择规则是否优于直接搜索（H3） | [U]：未运行 |
| U3 | 类型级规则对弱连接的预测是否在更多个体上成立 | [U]：只有 4 个留出个体 |
| U4 | 逐只动物的功能时间序列是否能区分真实与随机结构 | [U]：本轮未做 |
| U5 | 线虫规则能否迁移到其他回路或物种 | [U]：未检验 |
