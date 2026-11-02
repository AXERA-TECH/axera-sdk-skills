# reference/ 文档路由

下表声明在检索参考文档时的实际来源，
**读取时按"实际路径"列取文件，不要假设文档一定在本目录下**。

## 文档路由表

| 文档用途 | 实际路径 | 说明 |
|---|---|---|
| rpmsg和rpzc的问题复盘总结FAQ | `reference/ax_ipc_FAQ.md` | 本地正文和图片可离线读取；保留来源标题与版本，允许根据问题进行补充和完善 |
| rpmsg和rpzc的知识库 | `reference/ax_ipc.md` | 允许根据代码框架进行补充和完善 |
| 主域Linux平台下的rpmsg和rpzc使用指南 | `reference/Linux-IPC&ZC核间通信操作指南.docx` | 原始操作指南 |
| 主域QNX平台下的rpmsg和rpzc使用指南 | `reference/QNX-IPC&ZC核间通信操作指南.docx` | 原始操作指南 |
| MCU域RTOS/MCAL下的rpmsg使用指南 | `reference/MCU-IPC核间通信操作指南.docx` | 原始操作指南 |
| MCU域RTOS/MCAL下的rpzc使用指南 | `reference/MCU-IPCZC核间通信操作指南.docx` | 原始操作指南 |
| 主域Linux平台下的rpmsg和rpzc使用指南补充 | `reference/Linux-IPC&ZC核间通信操作指南补充.md` | 针对主域Linux平台下的rpmsg和rpzc使用指南的补充修改到这里 |
| 主域QNX平台下的rpmsg和rpzc使用指南补充 | `reference/QNX-IPC&ZC核间通信操作指南补充.md` | 针对主域QNX平台下的rpmsg和rpzc使用指南的补充修改到这里 |
| MCU域RTOS/MCAL下的rpmsg和rpzc使用指南补充 | `reference/MCU-IPC&ZC核间通信操作指南补充.md` | 针对MCU域RTOS/MCAL下的rpmsg和rpzc使用指南的补充修改到这里 |

## 为什么这样分

- **原文档**：原文档只修改有错误的地方，便于owner追溯，防止AI改的面目全非。

- **补充文档**：补充文档全部有AI完成，便于owner和AI管理和操作。

## 其他

- AX637 不支持 QNX，QNX 相关修改无需同步到 AX637。