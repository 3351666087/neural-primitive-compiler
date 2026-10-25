# Mission 08 数据

原始数据放在 `data/raw/`，**不提交 Git**（`.gitignore`）。每个文件的固定来源与 SHA-256 写在 `src/m08/raw.py` 的 `FILES` 表中；读取时逐个核对哈希，不一致即报错。

```bash
python3 -I -m m08.raw fetch     # 下载缺失的文件并核对哈希
python3 -I -m m08.raw check     # 只核对
```

（`m08` 包的路径由 `reproduce/setup_env.sh` 写入虚拟环境的 `.pth` 文件。）

## 来源与许可证

| 目录 | 内容 | 来源（固定到提交或记录） | 许可证 | 大小 |
|---|---|---|---|---|
| `cect_2026/` | Witvliet 2021 的 8 个连接组（xlsx）、Cook 2019 SI 5、Brittin 2021 SI 3、WormAtlas 神经元名单、Varshney 表 | OpenWorm ConnectomeToolbox，提交 `2ba2ff11` | 镜像代码 MIT；数据保留原始状态（Witvliet、Cook 无开放许可证） | 5.1 MB |
| `nemanode_20261025/` | Witvliet 1–8 与 White 1986 JSH、N2U 的连接（JSON，含缝隙连接）、细胞表、数据集年龄 | NemaNode API，2026-10-25 下载（API 无版本，以哈希为版本） | 未声明数据许可证 | 1.2 MB |
| `wormneuroatlas_0.0.7.3/` | Randi 2023 信号传播图谱 `funatlas.h5`（WT、unc-31）、神经元位置、谱系、神经元编号 | francescorandi/wormneuroatlas，提交 `b2e13d88` | 图谱数据来自 CC BY 4.0 论文；软件 GPL-3.0（不使用其代码） | 18.4 MB |
| `randi_2023_esm/` | Randi 2023 的 Source Data（图 2、图 3、扩展数据图 7） | Springer 静态内容 | CC BY 4.0 | 2.3 MB |
| `pathak_2020_si/` | Pathak 2020 S5 表：出生时间 | PLOS 补充材料 s021 | CC BY 4.0 | 22.5 KB |
| `skuhersky_2022/` | Skuhersky 2022 神经元位置图谱（两个版本） | github.com/bluevex/elegans-atlas（main） | 论文 CC BY 4.0；仓库无许可证 | 13.6 KB |
| `brittin_2021_zenodo4383277/` | Brittin 2021 接触组邻接（L4、成年，XML；压缩包解到 `adjacency_x/`） | Zenodo 4383277 | CC BY 4.0 | 0.9 MB（压缩） |
| `brainbuilding_d762ed07/` | Richter & Schneidman 2025 仓库的四个输入文件（位置、出生时间、Cook 细胞类别、突触计数矩阵） | schneidmanlab/BrainBuildingPaper，提交 `d762ed07` | **无许可证**：只在本地用于核对输入一致，不复制其代码 | 0.8 MB |

计划在 Gate 3 加入（果蝇 T4 支线）：flyvis `fib25-fib19_v2.2.json`（MIT，0.62 MB）与 Groschner et al. 2022 Edmond 数据的最小子集（CC BY 4.0，约 26.9 MB）。

## 核对过的一致性

- Pathak S5 表与 Richter & Schneidman 的 `time_of_birth.xls` 逐格相同（文件字节不同，差别在元数据）。
- Skuhersky `LowResAtlasWithHighResHeadsAndTails.csv` 与 Richter & Schneidman 的 `NeuronPosition3D.csv` 在 236 个同名神经元上数值完全相同；其余 64 个只是运动神经元的命名不同（AS1 对 AS01）。
- NemaNode 的 Witvliet 与 White JSON 与 Gate 1 审阅代理独立下载的副本逐字节相同。
- 两个 Witvliet 成年个体在 180 个共同神经元上各有 1,933 个有连接的有序对，共有 1,279 个，与 Richter & Schneidman 正文一致（`tests/test_loader.py`）。

## 留出数据

哪些数据集在冻结之前不得读取，见 `DATA_SPLITS_AND_CUSTODY.md`；加载器经 `src/m08/custody.py` 强制执行。
