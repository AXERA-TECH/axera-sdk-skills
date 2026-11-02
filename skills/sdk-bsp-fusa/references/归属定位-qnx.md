# 归属定位 · QNX 补充

**S2 用。先读 `归属定位-公共.md`，再读本文。**

公共部分已覆盖：三步定位法、mask 公式、domain 枚举、module 全表、ECM/FCU 两级关系、双层检查四步。本文只写 QNX 特有的部分。

## QNX 侧的路径与写法

| 项 | 值 |
|---|---|
| 错误码表 | `<SDK>/msp/fusa_out/include/ax_diag_type_ex.h`（约 739 行） |
| domain 枚举出处 | 同文件 `:638-643` |
| 符号名前缀 | **有 `AX_`**，如 `AX_MAIN_BSP_DFC_DIAG_SERVER_HEARTBEAT` |
| 日志形态 | **只有三元组一种** |

QNX 侧 mask 拆解的等价写法（与公共文件的公式等价，QNX 资料里常见这种写法）：

```
module = (mask & 0x7FFFFFF) >> 16
```

配套头文件：

- `msp/fusa_out/include/diag_enum.h` — 模块与错误 ID 枚举
- `msp/fusa_out/include/axera_diagnose.h` — 诊断状态编解码
- `msp/fusa_out/include/{ecm,fcu}_api.h`、`{ecm,fcu}_callback.h` — ECM/FCU 用户态接口

## 日志形态

QNX 只有一种形态——三元组，出处 `diag_netlink.c` 的 `diag_netlink_recv_error_handle`：

```
[20.223518] [diag-netlink:diag_netlink_recv_error_handle:96] err ID: 17 module ID: 45 domain ID: 0
```

按公共文件的公式合成即可：`(0 << 27) | (45 << 16) | 17` = `0x002D0011`。

<EXTREMELY-IMPORTANT>
日志里的 `diag-netlink` 前缀**具有误导性**。QNX 侧这个模块与 Linux netlink 无关，实际是 QNX message passing（`name_attach` + `MsgSend`/`MsgReceive`/pulse）。

不要因为看到 "netlink" 就去查网络配置、抓包、看 `/proc/net/netlink`——在 QNX 上这些全是死路。详见 `平台差异.md` 的「差异二」。
</EXTREMELY-IMPORTANT>

---

# ECM 与 FCU（QNX 侧机制）

FAQ 里 ECM/FCU 只以「故障码来源」和「已修缺陷」出现，没有机制说明。这一节补上。权威出处是 `<SDK>/docs/internal/domain/bsp/{ecm,fcu}.md`。

## ECM — Error Correction Module

设备节点 `/dev/ecm`，驱动 `m57_ecm_drv`（**用户态 resmgr 进程**，装在 `/usr/bin/`），单例（命名信号量 `/ecm_drv_singleton`）。

覆盖 10 个子系统：`ECM_TOP`、`ECM_CPU`、`ECM_DDR`、`ECM_FLASH`、`ECM_PERIPH`、`ECM_MM`、`ECM_NPU`、`ECM_ISP0/1/2`。驱动内置每个子系统的物理基址、寄存器长度、ECM 数量、FAULT_A/FAULT_B IRQ 配置。

代码位置：

- 驱动 `kernel/osdrv/private_drv/ecm/driver/m57_ecm_drv.c`
- 用户态 API `kernel/osdrv/private_drv/ecm/lib/`（`ecm_fault_enable`/`disable`/`inject`）
- 回调库 `kernel/osdrv/private_drv/ecm/lib/ecm_callback.c`
- STL 扩展 `kernel/osdrv/private_drv/ecm/lib_stl/`（仅 `USE_ECM_STL` 时编译）
- 调试工具 `ecm_fault`
- 安全岛侧 `SafetyIsland/driver/ecm/`、`SafetyIsland/mcal/mcal_drv/Ecm/`

标识编码 `ECM_MAKE_ID(subsys, hwirq) = (subsys<<16)|hwirq`。注意与回调库的 `ECM_CALLBACK_MAKE_ID` **不能混用**。

### ECM 排查清单（QNX，8 条）

按顺序查：

1. **`fault_a_irq == 0` 的控制器不注册 FCU 回调** —— 回调和通知路径根本不生效。客户报「ECM 注入没反应」时这是首查项。查 `ecm_configs` 里该子系统的 IRQ 配置。

2. **`all_fault_enable` 不是对所有子系统都开** —— NPU 和 ISP 相关控制器启动时会跳过「全量 fault clear / mask open」式初始化，它们依赖按通道策略控制。把 NPU/ISP 当 CPU/DDR 处理会破坏启动期策略。

3. **STL 初始化延后 8 秒** —— 默认等 8 秒再执行，给其它驱动留启动窗口；线程创建失败才回退到主线程内联。**开机 8 秒内的 ECM STL 现象要考虑这个窗口。**

4. **`USE_ECM_STL` 条件编译** —— 未开启时 `DCMD_ECM_CYCLE_CTRL`、`axera_ecm_stl_init()`、`axera_ecm_boot_check()` 都不存在。不要当成必有能力。

5. **`hwirq` / `chan` / `fault_type` 三个概念别混** —— API 用 `hwirq`；`ecm_register_callback` 收的是 `chan` + `uncorrectable`；`ecm_register_callback_ex` 收的是编码后的 `id`。最常见的错是把通道号当硬件 IRQ 号。

6. **`uncorrectable` 语义与 hwirq 奇偶位相关** —— UT 和示例用 `hwirq / 2` 和 `hwirq & 1` 还原通道和 fault 类型。只传 `hwirq` 不按约定拆分会配错错误类型。

7. **回调异步执行** —— detached worker 里跑，执行前后有 mask/enable 操作。别假设它在原线程原时序。

8. **强依赖联动驱动** —— 回调路径不只依赖 `m57_ecm_drv`，还依赖 FCU、Safety Island、RPMSG 和 ECM 硬件中断链路。UT callback 用例失败时先确认链路是否真的通，别先怀疑业务逻辑。

## FCU — Fault Collection Unit

设备节点 `/dev/fcu`（`FCU_DEVICE_PATH` 固定），驱动 `fcu_drv`（**用户态 resmgr 进程**），单例（`/fcu_drv_singleton`）。

内置 `FCU_FAULT_NAMES_COUNT = 115` 的故障名表，提供 `hwirq ↔ name` 双向映射（`fcu_get_fault_name()` / `fcu_get_fault_index_by_name()`）。

故障处理**两层拆分**：

- `fcu_hal_handler()` — 从中断/RPMSG 入口收事件，更新统计，推入 CF / NCF 队列
- `fault_handler_thread()` — 从队列取出，调 `process_fault()` 通知已注册客户端

这个拆分是为了不在硬中断或 pulse 回调里做重活。

<EXTREMELY-IMPORTANT>
**当前 QNX SDK 的 `fcu_drv` 也通过 RPMSG 向 SafetyIsland 发送硬件控制和状态查询。** `driver/fcu.c:506-546` 的 `send_cmd()` 调用 `ax_rpmsg_send()`；部分硬件状态查询在 `:629-681` 使用约 1 秒的条件等待，本地统计查询可直接返回。

因此需核对 RPMSG、对端回复和请求顺序，不能因进程及节点存在就排除通信或并发问题。该等待机制与 Linux 不同，不能套用 Linux 的无限 completion 等待结论；约 1 秒也不是整个工具调用必定退出的保证。先串行查询，异常时取现有进程阻塞态和通信日志。QNX 用户态回调库仍按下面的清单排查。
</EXTREMELY-IMPORTANT>

代码位置：

- 驱动 `kernel/osdrv/private_drv/fcu/driver/`
- 用户态 API `kernel/osdrv/private_drv/fcu/lib/fcu_api.c`
- 回调库 `kernel/osdrv/private_drv/fcu/lib/fcu_callback.c`
- 调试工具 `fcu_fault`
- 安全岛侧 `SafetyIsland/driver/fcu/`（`Fcu.c`、`Fcu_Stl.c`、`Fcu_Hardware.c`、`Fcu_Cfg.c`）
- **review 中的补丁 `fcu_codereview/`** —— 检索修复时别漏

### FCU 排查清单（QNX，8 条）

1. **RPMSG handshake 先行** —— 第一次发非 handshake 命令前会补发 `FCU_CMD_HANDSHAKE`。若新增 RPMSG 命令，别照搬「发一个命令就等返回」。链路没起来时所有命令都会异常。

2. **`FCU_CMD_*` 与 `DCMD_FCU_*` 是两套** —— 前者是驱动↔RPMSG 的命令语义，后者是用户态经 `/dev/fcu` 的控制码。**不要混用**。

3. **注册成功 ≠ 立即能收事件** —— `fcu_register_callback()` 顺序是：建 channel → 向驱动登记 → 创建回调线程 → 解除 mask。事件能否到达仍依赖驱动、RPMSG、硬件链路。

4. **注册/注销必须成对** —— `fcu_unregister_callback()` 不只释放 handle，还要清理 channel、线程、驱动侧注册。绕过它会留下悬挂注册、重复通知、未释放的 `coid`。

5. **回调 worker 的 mask/eoi/unmask 序列** —— worker 先 `fcu_irq_mask()`，回调结束 `fcu_irq_eoi()`，再尽量 `fcu_irq_unmask()`。这是为了减少重入和重复触发。漏 unmask 会导致后续事件收不到。

6. **handler 超时 50ms 是设计** —— 超过阈值上报 `0x800A0010`（`AX_MCAL_CDD_FCU_SAFETY_FCU_HANDLER_TIMEOUT`），HAPS 环境 100ms。偶发是耗时抖动；**持续大量出现**才需查处理链路为何变慢。

7. **`hwirq` 是主标识** —— 别和 `FCU_CMD`、`fault_type`、`name` 混淆。`fault_type` 当前只有 `FCU_FAULT_NCF` / `FCU_FAULT_CF` 两类，别自行扩展第三类。

8. **查询型 devctl 依赖 reply 缓冲和范围检查** —— 先做 `fcu_devctl_query` 风格的输入校验，别把非法 `hwirq` 送进驱动再分析错误。

## QNX 特有：四个独立进程

诊断相关功能由**四个独立的用户态进程**承担，不是一个内核模块：

| 进程 | 职责 | 节点 |
|---|---|---|
| `diag_core_drv` | 诊断框架核心 | `/proc/ax_diag/` |
| `diag_extend` | 扩展模块（MID 87） | `/dev/diag_extend` |
| `m57_ecm_drv` | ECM 驱动 | `/dev/ecm` |
| `fcu_drv` | FCU 驱动 | `/dev/fcu` |

<EXTREMELY-IMPORTANT>
**任一进程挂掉，其余仍在跑但功能残缺，且诊断能力静默丢失——故障不再上报。**

客户报「以前有诊断日志，最近没有了」「某类故障查不到了」时，**第一件事是确认四个进程都在**：

```bash
pidin ar | grep -E "diag_core_drv|diag_extend|m57_ecm_drv|fcu_drv"
```

不要当成「没有故障所以没日志」。这是 QNX 侧独有的失效模式，Linux 不存在（内核模块一起活一起死）。
</EXTREMELY-IMPORTANT>

归属定位到某类故障「完全收不到」时，按进程归属检查：ECM 类查 `m57_ecm_drv`，FCU 类查 `fcu_drv`，MID 87 扩展类查 `diag_extend`，其余查 `diag_core_drv`。
