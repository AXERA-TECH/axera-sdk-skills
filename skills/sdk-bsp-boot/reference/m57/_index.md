# reference/m57 文档路由

本目录存放 M57 架构层公共文档。AX637 / AX637R 通过 `platforms/ax637.md`（`extends: m57`）复用本目录文档；其 board/SDK 层专有文档见 `reference/ax637/`，不重复维护架构公共内容。

## 文档路由表

| 文档用途 | 实际路径 | 说明 |
| --- | --- | --- |
| M57 SDK 使用说明（安装/编译/内存与分区/U-Boot 移植/BOOTROM/BootCnt/OTA） | `reference/m57/00 - AX SDK 使用说明.md` | 图片在 `reference/m57/ax_sdk_usage_00_assets/`；BootCnt 见 §13 |
| M57 SBL 启动特性介绍 | `reference/m57/M57 SBL启动特性介绍.md` | SBL 的 AB 管理、RTOS OCM+DDR 引导、复位 main 域及客户 FAQ（§1.2 / §2 / §3） |
| AX637 / AX637R board/SDK 层文档 | `reference/ax637/_index.md` | AX637 专有差异文档，不属本目录，禁止跨平台混用路径与默认值 |

## 为什么这样分

- M57 是架构层：启动链路、构建框架、内存与分区机制、BOOTROM、BootCnt 与 OTA 均在本目录文档描述；AX637 复用并在 `platforms/ax637.md` 中标注差异。
- SBL 启动特性（AB 管理、RTOS 引导、复位 main 域）来自本目录 `M57 SBL启动特性介绍.md`，AX637 复用；若 AX637 有差异，已在 `platforms/ax637.md` 中说明。
- 文档转换的中间工作目录不是对外文档，维护与路由时不引用。

## 维护规则

1. 新增文档先判断是否属于 M57 架构公共层；是则放本目录，AX637 通过 `platforms/ax637.md` 引用。
2. 修改本目录内容时需确认 AX637 是否同样适用；若 AX637 有差异，必须在 `platforms/ax637.md` 中标注。
3. 本表是 `platforms/m57.md` §参考文档、`skill-card.md` §Sources 与 `README.md` §平台矩阵的事实来源，调整路径时同步更新。
