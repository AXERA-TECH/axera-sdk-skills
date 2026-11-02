# M57 参考文档路由

| 主题 | 当前来源 | 本地文档 | 状态 |
|---|---|---|---|
| NAND 与文件系统 FAQ | nand文件系统FAQ | [`nand-filesystem-faq.md`](nand-filesystem-faq.md) | 已整理；含 Linux 共性和 M57 专属条目 |
| Linux NAND FAQ | linux下nand及文件系统FAQ汇总 | [`nand-filesystem-faq.md`](nand-filesystem-faq.md)、[`flash-adaptation.md`](flash-adaptation.md) | 已整理，需按具体 board 复核 |
| M57 FAQ 总索引 | M57 FAQ计划 | 本索引与 evals 任务映射 | 已定位 |
| Flash scan | M57 flash scan功能使用指南 | [`flash-scan.md`](flash-scan.md) | 已整理；参数需按源码和目标 board 复核 |
| Flash 适配、MCAL/EB FLS | FAQ 与当前启动链配置 | [`flash-adaptation.md`](flash-adaptation.md) | M57 路由保留 MCAL/EB 条件步骤，需按目标构建链核对 |
| QNX `ax_mtd`、ETFS 与 virtual flash | QNX ax_mtd知识库v1.0 | [`qnx-ax-mtd.md`](qnx-ax-mtd.md) | M57 专用，已整理 |
| 本地源码与配置 | `kernel/`、`SafetyIsland/`、`build/platforms/axera/`、`tools/mk*fs/` | 平台文档中的证据引用 | 需按具体 board 交叉核对 |

文档保留来源标题（不含内部 URL）；本地内容是面向排障的整理稿，不替代目标 SDK、Flash 数据手册、buildfile 或源码。涉及擦写、重分区和烧录前必须完成平台与 geometry 确认。
