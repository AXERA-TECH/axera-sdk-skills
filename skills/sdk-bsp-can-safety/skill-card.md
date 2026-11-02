# Skill Card: sdk-bsp-can-safety

| Field | Value |
|---|---|
| name | sdk-bsp-can-safety |
| owner | Axera BSP  |
| version | 1.0.0 |
| platforms | M57 Linux/QNX 项目的 Safety 侧 AUTOSAR MCAL CAN/CAN FD |
| updateFrequency | 未指定 |

## 已知边界

- AX637/AX637R Safety 侧使用 RTT RTOS CAN，不属于本 skill。
- 主 CPU Linux SocketCAN、QNX 原生 CAN 和 SafetyIsland baremetal CAN 不属于本 skill。
- FAQ 仅是参考信息；目标 SDK 的源码、生成配置和用户手册是核对实现的依据。
- EB 配置说明中的限制和建议需结合目标 SDK、硬件版本及目标生成配置确认。

## Sources

- 用户提供的平台范围说明。
- `references/M57 CAN 常见问题解决思路.md`。
- `references/M57 MCAL CAN EB 配置说明.md`。
- `references/代码地图-mcal.md` 中列出的当前 SDK 文件。
- `SafetyIsland/mcal/plugins/Can/Doc/AXERA-M57 MCAL CAN UM.docx`。
