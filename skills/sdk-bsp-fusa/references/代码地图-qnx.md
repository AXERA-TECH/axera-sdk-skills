# QNX 代码地图

**S5 用。** 定位代码、找判定依据。

所有路径相对客户 SDK 根目录（含 `.repo/` 的那一层）。**行号会随版本漂移，只作起点参考——落笔前必须打开文件核实。**

## 三域架构

FuSa 诊断是三级串联，心跳互发，`0xdeadbeef` 是握手/心跳标记：

```
Safety Island R 核 (mcal)  ←→  用户态 diag server (msp)  ←→  diag_core_drv (用户态 resmgr 进程)
     Diag_core.c              netlink_monitor.cpp            diag_stl.c
                         经 QNX message passing (name_attach + MsgSend)
```

<EXTREMELY-IMPORTANT>
**第三级不是内核驱动。** `diag_core` 虽在 `kernel/osdrv/private_drv/` 路径下，实际是装在 `/usr/bin/diag_core_drv` 的**用户态 resmgr 进程**（`common.mk:8` `NAME := diag_core_drv`、`:36` `INSTALLDIR=usr/bin`；`diag_core.c:2042` `main()`、`:2002` `resmgr_attach`）。

**第二、三级之间不是 TCP。** `diag_netlink` 这个名字只是沿用，实际用 `name_attach`/`name_open` + `MsgSend`/`MsgReceive`/pulse（`diag_netlink.c:386`、`:165`、`:229`、`:282`）。**没有端口、没有 socket、抓不到包。**

详见 `平台差异.md` 的「差异一」「差异二」。
</EXTREMELY-IMPORTANT>

排查时按「哪一级先报」回溯：R 核先报多为 server→R 核链路；server 先报多为 BSP↔server；BSP 刷屏多为 server 侧被拖慢或内存不足。

## BSP 侧 — `kernel/osdrv/private_drv/diag_core/`

| 文件 | 职责 |
|---|---|
| `driver/diag_stl.c` | 周期自检、心跳检查、去抖判定 |
| `driver/diag_netlink.c` | 与 server 的 QNX 消息传递（**非 TCP、非 netlink**）、错误上报打印 |
| `driver/diag_sysfs.c` | `/proc/ax_diag` 节点与属性定义 |
| `driver/diag_fault_inject.c` | 故障注入 |
| `driver/diag_core.c` | 框架核心、模块注册 |
| `driver/diag_rpmsg.c` | 与安全岛的 RPMSG 通道 |
| `include_priv/diag_core.h` | 内部阈值常量 |
| `include/diag_enum.h` | 模块/错误 ID 枚举 |
| `tools/diag_tools` | ksh 脚本，注入/查询工具 |

### 关键判定点

**心跳去抖**（`diag_stl.c`）— 这是理解 FAQ-01 的核心：

```c
heartbeat_time++;
diag_pr_info("heartbeat time:%d\n", heartbeat_time);   // INFO，会刷屏，不是故障
/* The timeout for this heartbeat will only be 20ms in the next loop.
 * When the timeout count is 5, the actual timeout is 4 rounds. */
if (heartbeat_time > 5) {
    diag_pr_err("heartbeat timeout.\n");                // ERR，才是真故障
    diagnosis_error_send(&de_heartbeat_err);
    heartbeat_time = 0;
}
```

单轮等待阈值 `SERVER_HEARTBEAT_TIMEOUT = 5`（ms），在 `include_priv/diag_core.h:59`。

**刷屏来源**（`diag_netlink.c`）— `diag_netlink_recv_error_handle` 对每条上报打一行 INFO，这就是 `err ID / module ID / domain ID` 那种刷屏行的出处。日志级别默认 7（info），调 `DIAG_LOG_LEVEL_VALUE` 可减少。

## 用户态 server 侧 — `msp/component/diag/`

| 文件 | 职责 |
|---|---|
| `src/core/netlink_monitor.cpp` | 心跳超时定时器、与 BSP 的通信 |
| `src/core/diag_core.cpp` | 错误回调、上报处理 |
| `src/core/diag_event_manager.cpp` | 事件管理 |
| `src/service/ax_diag_service.cpp` | 服务入口 |
| `src/toolkit/ax_diag_tool/` | 用户态诊断工具 |
| `src/modules/{npu,cve,ive,ivps}/` | 各子系统用户态自检 |
| `config/diag_domain_*.json` | 各域运行时配置 |
| `src/utils/version.h` | `DIAG_BUILD_VERSION` 定义 |

### 关键判定点

**server 心跳窗口**（`netlink_monitor.cpp:21`）：

```c
#define BSP_HEART_BEAT_TIMEOUT 20   // bsp heart beat time cycle is 20ms
```

实际窗口 = `BSP_HEART_BEAT_TIMEOUT * flowTimerLen`（`:588` 处 `timeout_->Start("diagcore_hbeat", ...)`）。`flowTimerLen` 默认 4，即 80ms。FAQ-12 说的「心跳窗口 = 20ms × flowTimerLen」就是这里，`flowTimerLen` 可调。

超时触发 `errorCallBack_`，在 `diag_core.cpp` 里打印 `BSP HeartBeat error` 并上报。

**运行时配置** — `config/diag_domain_*.json` 里每个模块有 `cycle_enable`、`cycle_ms` 等字段。客户问「周期自检默认开不开」时查这里，不要凭 FAQ 记忆回答，各模块默认值不同。

## 安全岛侧 — `SafetyIsland/`

| 路径 | 职责 |
|---|---|
| `mcal/mcal_drv/Diag/src/Diag_core.c` | R 核诊断核心、心跳监控 |
| `mcal/mcal_drv/Diag/src/Diag_Ipc.c` | 跨核 IPC |
| `mcal/mcal_config/generated/include/Diag_Cfg.h` | 生成的配置常量 |
| `driver/ecm/` | ECM 驱动（`ecm_hardware.c`、`Ecm_Stl.c`） |
| `driver/fcu/` | FCU 驱动（`Fcu.c`、`Fcu_Stl.c`、`Fcu_Hardware.c`、`Fcu_Cfg.c`） |
| `mcal/mcal_drv/{Ecm,Fcu}/` | MCAL 层 ECM/FCU |
| `mcal/mcal_drv/Bus/src/Bus_stl.c` | 总线 ECC 自检（ECM correctable/uncorrectable 服务例程） |
| `mcal/mcal_drv/CpuExtend/src/Cpu_stl.c` | CPU/OCM ECC 自检 |

### 关键判定点

**R 核心跳阈值**（`Diag_Cfg.h`）— 注意这个宏**出现两次**，是条件编译的两个分支：

```
:68   #define HEARTBEAT_TIMEOUT_MS 400U
:73   #define HEARTBEAT_TIMEOUT_MS 80U
```

引用前**必须看清当前构建走的哪个分支**（看两处的 `#if` 条件）。FAQ-04 说的「R 核 80ms 阈值 vs 实测 90ms」对应的是 80U 那个分支。直接引用错分支会得出相反结论。

这类「同名宏多处定义」的情况在 MCAL 生成代码里常见，凡引用 `Diag_Cfg.h` 的常量都要先确认分支。

## 配置生成链路

```
Excel (Fault_diagnosis_event_list.xlsx)
   ↓  make PLAT=<平台> fusa_config
generated_diag_config.py
   ↓
msp/component/diag/config/*.json  +  msp/fusa_out/include/*.h
```

相关位置：

- Excel：`build/platforms/customer/<板型>/Fault_diagnosis_event_list.xlsx`
- 生成脚本：`build/scripts/fusa/fusa_make.sh`、`fusa_common.mk`
- 编译总开关：`SUPPORT_AX_DIAG`
- 版本号：`build/version/m57_version.mk`
- manifest 历史：`.repo/manifests/M57_SDK_QNX_V*.xml`

**改了 Excel 必须重跑 `fusa_config`**，否则生成物不更新（FAQ-16）。

## 错误码表

`msp/fusa_out/include/ax_diag_type_ex.h`（约 739 行）——mask → 符号名的完整映射，以及 domain / module 枚举。S2 归属定位的权威来源。

配套：

- `msp/fusa_out/include/diag_enum.h` — 模块与错误 ID 枚举
- `msp/fusa_out/include/axera_diagnose.h` — 诊断状态编解码
- `msp/fusa_out/include/{ecm,fcu}_api.h`、`{ecm,fcu}_callback.h` — ECM/FCU 用户态接口

## SDK 内权威文档

比 FAQ 更详细的机制说明，FAQ 未覆盖时优先读这些，**不要猜**：

| 文档 | 内容 |
|---|---|
| `docs/internal/domain/bsp/fusa_diagcore.md` | diag_core 框架 |
| `docs/internal/domain/bsp/ecm.md` | ECM 机制、设计决策、坑 |
| `docs/internal/domain/bsp/fcu.md` | FCU 机制、设计决策、坑 |
| `docs/internal/domain/bsp/axdma.md` | AXDMA |
| `docs/internal/domain/bsp/dmaper.md` | DMAPER |
| `docs/internal/domain/bsp/clock_monitor.md` | 时钟监控 |
| `docs/internal/domain/safetyisland/` | 安全岛相关 |

每份文档的 `pitfalls` 段落尤其有用——那是已知坑的清单，往往直接命中客户的问题。

## 补丁与 review 目录

检索修复是否存在时，**这些目录不能漏**——补丁可能在 review 中而非主线：

- `fcu_codereview/` — FCU 相关 diff（如 `239461d.diff`）
- `code_review/`
- `doc_modify/` — 文档修改分析，含调用链分析文档

实测案例：FAQ-31 说 V1.1.0 修了 FCU `set_mask` 竞态，但主线 `private_drv/fcu` 下搜不到关中断原语，补丁躺在 `fcu_codereview/239461d.diff`（标题 `fcu: FCU set mask add irq_save`）。

## 代码特征检测的正确做法

<EXTREMELY-IMPORTANT>
不要照抄 FAQ 里的关键词就 grep。已实测出假阴性。

正确顺序：

1. 先读 `docs/internal/domain/bsp/*.md` 和实际代码，确认**当前实现用什么原语**
2. 再决定搜什么关键词
3. 用 `rg -c`（计数）或 `rg -l`（列文件），比看匹配文本可靠
4. 搜不到时，**不能判定「未含修复」**——可能是重构搬家、原语不同、或补丁在 review

QNX / Linux 原语对照（FAQ 里的描述可能来自 Linux 分支）：

| Linux | QNX |
|---|---|
| `local_irq_save` / `irq_save` | `InterruptLock` / `InterruptDisable` |
| `spin_lock` | `pthread_mutex_lock` / `InterruptLock` |
| `wait_for_completion_timeout` | `MsgReceivePulse` + `TimerTimeout` |
| `msecs_to_jiffies` | `nsec` 直接计算 |
</EXTREMELY-IMPORTANT>

## 常见排查入口速查

| 现象关键词 | 先看哪里 |
|---|---|
| `heartbeat time` / `heartbeat timeout` | `diag_stl.c` 去抖逻辑 + `netlink_monitor.cpp:21` 窗口 |
| `BSP HeartBeat error` | `diag_core.cpp` 的 `errorCallBack_` |
| `diag-netlink ... err/module/domain` 刷屏 | `diag_netlink.c` 的 `diag_netlink_recv_error_handle` |
| `fcu handler timeout` / `0x800A0010` | `docs/internal/domain/bsp/fcu.md` + `SafetyIsland/driver/fcu/Fcu_Stl.c` |
| ECM readback / ECC 误报 | `docs/internal/domain/bsp/ecm.md` + `private_drv/ecm/driver/m57_ecm_drv.c` |
| 周期自检误报 | 对应模块的 `*_stl.c` + `config/diag_domain_*.json` 的 `cycle_*` |
| 注入无效 | `diag_fault_inject.c` + 模块 `cycle_enable` 状态 |
| 开关不生效 | `SUPPORT_AX_DIAG` + Excel + `fusa_config` 是否重跑 |
| 卡死/阻塞 | 相关 `*_main.c` 的 `MsgReceivePulse` 是否带超时 |
