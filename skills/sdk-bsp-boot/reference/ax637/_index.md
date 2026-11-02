# reference/ax637 文档路由

本目录只存放 AX637 / AX637R board/SDK 层文档。M57 架构公共文档统一放在 `reference/m57/`，本目录不重复维护与 M57 共用的文档。

## 文档路由表

| 文档用途 | 实际路径 | 说明 |
| --- | --- | --- |
| AX637 SDK 使用说明（安装/编译/内存/分区/U-Boot/BOOTROM/OTA） | `reference/ax637/00 - AX SDK 使用说明.md` | 图片在 `reference/ax637/ax_sdk_usage_00_assets/`；含 only_nand/only_emmc 差异 |
| AX637 boot 类问题汇总 | `reference/ax637/637-boot类问题.md` | 图片在 `reference/ax637/637-boot类问题_assets/`；源为 Wiki 页面 637-input-reference |
| M57 SDK 使用说明（架构公共） | `reference/m57/00 - AX SDK 使用说明.md` | 与 AX637 版并列的独立文档，不可互相替代 |
| M57 SBL 启动特性介绍 | `reference/m57/M57 SBL启动特性介绍.md` | SBL 的 AB 管理、RTOS OCM+DDR 引导、复位 main 域 |

## 为什么这样分

- AX637 与 M57 的 `00 - AX SDK 使用说明` 是两份独立文档：平台配置、内存调整方式、分区默认值、串口波特率等存在差异，必须按平台分别引用。
- SBL 启动特性（AB 管理、RTOS 引导、复位 main 域）来自 M57 架构层文档，AX637 复用；若 AX637 有差异，已在 `platforms/ax637.md` 中说明。
- 文档转换的中间工作目录不是对外文档，维护与路由时不引用。

## 维护规则

1. 新增文档先判断是否属于 M57 架构公共层；是则放 `reference/m57/`，AX637 通过 `platforms/ax637.md` 引用。
2. 修改 `reference/m57/` 内容时需确认 AX637 是否同样适用；若 AX637 有差异，必须在 `platforms/ax637.md` 中标注。
3. 本表是 `platforms/ax637.md` §参考文档、`skill-card.md` §Sources 与 `README.md` §平台矩阵的事实来源，调整路径时三处同步。
