# Skill Card: sdk-bsp-rpmsg

| Field | Value |
|---|---|
| name | sdk-bsp-rpmsg |
| owner | Axera BSP Team |
| kind | workflow (reference + configuration + diagnosis) |
| riskLevel | high — 跨端地址或 shared-memory 配置错误可能破坏内存或阻断核间通信 |
| platforms | M57 Linux/QNX 主域、AX637 / AX637R 非 QNX 场景与 SafetyIsland MCU/MCAL/RTOS |
| reviewCycle | IPC/RPMsg/RPZC 驱动、DTS、MCAL 配置或 UAPI 变化时 |

## Use case

配置、使用、验证并诊断 Axera SoC 的 IPC/RPMsg 和 RPZC。skill 通过 `routing.yaml` 识别 SDK 平台，并按 `reference/_index.md` 读取 `reference/ax_ipc.md`、Linux/MCAL/RTOS 指南和补充资料；问题复盘 FAQ 使用本地 `reference/ax_ipc_FAQ.md` 与随包图片，可离线读取。

## Platform matrix

| 平台 id | 说明 | 自动检测触发条件 |
|---|---|---|
| `m57` | M57 IPC/RPMsg/RPZC 公共实现 | `SafetyIsland/mcal/` 存在 |
| `ax637` | AX637/AX637R 非 QNX board 层；未声明差异时复用适用的 M57 Linux/MCU/RTOS 规则 | `SafetyIsland/rt-thread/bsp/m57/configs_ax637*` 存在 |

## Known risks

- M57 Linux/QNX 或 AX637 非 QNX 主域与 MCU 的 endpoint 地址、name、buffer name、方向或长度不匹配时无法通信。
- reserved-memory、IRAM/DDR 地址重叠或单端修改可能破坏其他应用数据。
- mailbox slot、destination core 和 mailbox/GPIO 中断方案必须两端一致。
- RPZC payload 尚未消费就回复 ACK，或 ACK 完成前复用同步 buffer，可能造成数据被覆盖。
- 远端 reset/remove 后旧 fd、mmap 和 endpoint 不保证有效，需要重新枚举和初始化。
- MCU 端 ring buffer 锁需按 BareMetal、RTOS、AUTOSAR 集成环境实现和验证。

- 以下 QNX 风险仅适用于 M57，AX637 不支持 QNX，QNX 相关修改无需同步到 AX637：
  - 默认 IPCZC 使用 IRAM，`IPC_ZC_BUFFER_BY_DDR=0`；切换 DDR 必须同步 reserved-memory、`Ipc_zc_cfg.h`、`AX_RESV_MEM_DDR_ADDR_IPCZC0` 和 MCU 端。
  - 默认 `IPC_GPIO_TRIGGER_IRQ_EN=1`，使用 GPIO + SPI slave CS/回主域 mailbox 通知；切换 mailbox 时必须同步两端。
  - EPT、buffer name/size、地址和 name service 属于跨端契约，远端 reset 后必须重新初始化。

## Sources

- `reference/_index.md` — 文档用途与实际路径的唯一入口
- `reference/ax_ipc.md` — Linux、MCAL、RTOS 的 IPC/RPMsg/RPZC 公共知识库
- [reference/ax_ipc_FAQ.md](reference/ax_ipc_FAQ.md) — 本地问题复盘 FAQ，保留来源标题、版本、适用范围和图片，可按问题持续完善
- `reference/Linux-IPC&ZC核间通信操作指南.docx` — Linux defconfig、DTS、RPMsg/RPZC 用户态流程
- `reference/Linux-IPC&ZC核间通信操作指南补充.md` — Linux 架构、UAPI 生命周期、reset/debug/test 补充
- `reference/QNX-IPC&ZC核间通信操作指南.docx` — 仅适用于 M57 的 QNX RPMSG-LITE、EPT/IPCZC、IRAM/DDR、mailbox/GPIO 和测试流程
- `kernel/osdrv/open_drv/ax_ipc/` — 仅适用于 M57 QNX 的 resource manager、`driver/cfg`、`driver/rpmsg`、`driver/rpzc`、`lib` 实现
- `msp/sample/ipc_rpmsg/` — 仅适用于 M57 QNX 的 `sample_ipc_rpmsg` 与 IPC/RPZC 示例
- `reference/MCU-IPC核间通信操作指南.docx` — MCAL IPC API、配置和集成
- `reference/MCU-IPCZC核间通信操作指南.docx` — MCAL IPC_ZC API、buffer/ACK 和集成
- `SafetyIsland/rt-thread/bsp/m57/drivers/ipc/` — RTOS IPC/RPZC 实现与静态配置
- `platforms/m57.md` — 对上述来源的执行摘要和跨端检查表
