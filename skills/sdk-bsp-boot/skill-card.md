# Skill Card: sdk-bsp-boot

| Field | Value |
| --- | --- |
| name | sdk-bsp-boot |
| owner | Axera BSP Team |
| kind | workflow (reference + diagnosis) |
| riskLevel | high — 分区/SBL/metadata 大小会影响可启动性，内存与分区改动需重新编译烧写验证 |
| platforms | M57 架构（AX637 / AX637R）；可扩展至其他 M57 架构子平台 |
| reviewCycle | 每次 SDK 启动链路、分区默认值、U-Boot 引导方式或参考文档变更时 |

## Use case

回答 Axera SDK 的启动链路、U-Boot 引导内核方式、内存（Linux/CMM/Inline ECC）与 FLASH 分区规划、BOOTROM/BootCnt/OTA，以及基于串口日志的启动类问题定位。

## Platform matrix

| 平台 id | 说明 | 自动检测触发条件 | 主文档 |
| --- | --- | --- | --- |
| ax637 | AX637 / AX637R SDK（基于 M57） | `SafetyIsland/rt-thread/bsp/m57/configs_ax637`、`configs_ax637r` | `platforms/ax637.md`（extends `m57`） |
| m57 | Axera M57 SDK（M57 架构） | `SafetyIsland/mcal` | `platforms/m57.md` |

新增平台：`routing.yaml` 条目 + `platforms/<id>.md` + `reference/<id>/` + `evals` 矩阵条目。

## Known risks

- AB 场景 SBL 分区大小必须用 SDK 默认值（NAND 768K / eMMC 128K），改小会导致 RomCode 找不到 B 分区。
- NAND 分区需为 block size 整数倍并预留坏块 block；NAND 上 hsm 附在 SBL 镜像后，SBL 实际占 256K。
- AX637 与 M57 的内存/CMM 调整入口一致（平台 `config.mk` 的 `SYSTEM_MEMORY_SZ` / `LINUX_MEMORY_SZ`）；不要套用早期文档的 DTS 节点 / `load_modules.sh` 说法。
- BootCnt 仅 M57 支持，AX637 / AX637R 不支持，勿向 AX637 套用 M57 的 BootCnt 方案。
- only_nand 分区表在 metadata 分区、only_emmc 在 1M GPT 空间，分区表位置不同，不可套用。
- 串口波特率 trunk 已按安防/边缘 115200、车载 921600 区分，ep 分支修改需与客户确认。

## Sources

- `platforms/m57.md`、`platforms/ax637.md`
- `reference/ax637/_index.md`
- `reference/m57/00 - AX SDK 使用说明.md`
- `reference/m57/M57 SBL启动特性介绍.md`
- `reference/ax637/00 - AX SDK 使用说明.md`
- `reference/ax637/637-boot类问题.md`
