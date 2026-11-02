# AX637/AX637R 参考文档路由

| 主题 | 来源 | 本地文档 | 状态 |
|---|---|---|---|
| NAND、MTD、UBI/UBIFS 与烧录原则 | NAND FAQ 与 Linux FAQ | [`nand-filesystem-faq.md`](nand-filesystem-faq.md) | 共性文档副本；QNX 条目不适用 AX637 |
| Flash scan | M57 flash scan 指南 | [`flash-scan.md`](flash-scan.md) | 共性方法副本；AX637 实际 Kconfig、命令和参数须以源码为准 |
| Flash 适配 | NAND FAQ 与 Linux FAQ | [`flash-adaptation.md`](flash-adaptation.md) | 共性框架副本；具体参与层须按 AX637/AX637R 构建链核对 |
| AX637/AX637R 平台范围 | 当前 checkout 的平台目录、U-Boot/Linux 配置 | `platforms/ax637.md` | AX637 与 AX637R 共用路由；demo/客户板差异待确认 |
| QNX `ax_mtd`/ETFS、virtual flash、MCAL/EB FLS | M57 专属资料 | 不纳入 AX637 reference | 不适用 |

## 平台范围

本目录同时覆盖 AX637 和 AX637R。两者共享 Linux NAND 方法，但 AB/non-AB、分区 JSON、DDR/安全配置和具体镜像布局必须分别核对。当前 checkout 可见的 demo 配置不代表所有客户板或量产配置。

AX637/AX637R 当前按 Linux 主域和 Safety/RTOS 启动链处理；没有将 M57 的 QNX `ax_mtd`、`mtdpart`、ETFS、virtual flash 或 MCAL/EB FLS 内容作为本平台事实。
