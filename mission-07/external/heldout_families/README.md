# 留出机制族 β、γ

由与研究会话隔离的会话按 `mission-07/BETA_AUTHOR_BRIEF.md` 撰写（2026-10-21/22），原件保存在仓库之外；研究会话在冻结提交 c5ddc36 推送之后才核对哈希并读取（`mission-07/CUSTODY.md`、`mission-07/G4_NOTES.md`）。确认运行结束后复制到这里，以 MIT 许可随仓库发布。四个文件的 SHA-256 与 `CUSTODY.md` 中登记的值相同：

| 文件 | SHA-256 |
|---|---|
| family_beta.json | 41c050373310a512c13d33f10ff84d9f5e8a509ffe6a85cc3bc2863d00ca5bfb |
| demos_beta.json | abbe165d84a5c81bd0d9ef171aabaa4aa27ac3596c224f798f8fc8e82169b50e |
| family_gamma.json | 2a43a5dfc5537d06307a4f4bca2b91fd78c16d294b59e120a5eabc0608faa911 |
| demos_gamma.json | c09fd24b5f43582123b71ed2bee1f6486525d2ad9b9af8438727ace5e77d9995 |

`experiments/eco/g4_jobs.py` 从保管目录读取并在每次读取前核对哈希；复现时可把这四个文件放回 `/Users/null3351/Code/m07-custodian/`，或改写 `g4_jobs.CUSTODIAN`。
