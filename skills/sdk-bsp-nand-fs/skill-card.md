# Skill Card: sdk-bsp-nand-fs

| Field | Value |
|---|---|
| name | sdk-bsp-nand-fs |
| owner | Axera BSP Team |
| kind | workflow (reference + diagnosis) |
| riskLevel | high — 分区、擦写、坏块处理和烧录可能造成数据丢失或无法启动 |
| platforms | M57（Linux/QNX）、AX637/AX637R（Linux 主域 + Safety/RTOS 启动链） |
| reviewCycle | 每次 SDK、NAND driver、Flash geometry、文件系统或烧录流程变更时 |

## Use case

统一处理 Axera 平台 NAND/Flash 与文件系统问题。覆盖 Flash scan、NAND 适配、ECC/坏块、Linux MTD/UBI/文件系统、分区元数据、AXDL/FDL 烧录和启动后验证；M57 额外覆盖 QNX ETFS，AX637/AX637R 不覆盖 QNX 文件系统。

## Platform matrix

| 平台 id | 范围 | 平台文档 | 参考路由 |
|---|---|---|---|
| `m57` | M57 NAND/Flash、Linux/QNX 文件系统与启动介质差异 | `platforms/m57.md` | `reference/m57/` |
| `ax637` | AX637/AX637R NAND、ONLY_NAND/相关启动与文件系统差异 | `platforms/ax637.md` | `reference/ax637/` |

## Known risks

- Flash ID、page/block geometry、ECC、接口线数或 scan 参数错误，可能导致识别错误、读写失败、数据损坏或性能异常。
- NAND 坏块、分区边界、镜像大小和文件系统预留不一致，可能导致烧录失败、挂载失败或启动失败。
- Linux MTD/UBI 语义与 M57 QNX `ax_mtd`/`mtdpart`/`etfs` 语义不能互换；AX637/AX637R 不使用后者作为文件系统运行时入口。
- 分区元数据、SBL/U-Boot 定义、AXDL/FDL/OTA 包和系统启动后的实际布局可能发生漂移，必须回读核对。

## Sources

- 部门 SDK BSP Skills 实施计划（M57 & AX637）
- nand文件系统FAQ
- M57 FAQ计划
- `platforms/m57.md`、`platforms/ax637.md`
