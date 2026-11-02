# 运行时接口 · QNX

**S4 必读。** 属性含义、`diag_tools` 参数、设备节点。

出处 `kernel/osdrv/private_drv/diag_core/driver/diag_sysfs.c` 与 `tools/diag_tools`。

## 路径总览

| 用途 | 路径 |
|---|---|
| 诊断属性（domain/module/error 三级） | `/proc/ax_diag/` |
| ECM 设备节点 | `/dev/ecm` |
| FCU 设备节点 | `/dev/fcu` |
| diag_extend 节点 | `/dev/diag_extend` |

<EXTREMELY-IMPORTANT>
**先列实际目录，不要仅凭平台猜模块/错误路径。** 当前 QNX SDK 的 `diag_sys_common.c:933-945,1041-1053` 使用数字目录；部分历史资料使用名字示例，不能据此拼当前路径。

- 当前 QNX SDK：`/proc/ax_diag/domain0/module0/error17/`
- Linux：`/sys/devices/platform/axdiag/domain0/module0/error17/`

按 ID 与节点的 `name` 对账，具体目录以板端 `ls` 为准；旧资料中的 `dfc/diag_server_heartbeat/` 仅在现场确有该目录时使用。
</EXTREMELY-IMPORTANT>

QNX 没有 Linux 的 `/sys/class/fusa/` 路径。当前 SDK 在 `/proc/ax_diag/inject_enable` 导出注入总开关（`diag_core.c:1590-1605,1735`），`diag_tools -i` 会先尝试打开它（脚本 `:346`）；注入不生效时仍需核对实际回读与脚本版本。

## 属性速查

### domain 级

路径 `/proc/ax_diag/domain<D>/`

**只读**：`name`、`domain_id`、`count`

<EXTREMELY-IMPORTANT>
**普通 domain 属性组只有上述三项，但 BSP domain0 还注册了额外属性。** 当前 SDK 的 `diag_core.c:1455-1478,1722-1729` 导出 domain0 的 `cycle_enable`、`d_boot_error`、`detection_enable`、`shutdown_start`，其中 `cycle_enable` 初值为 0。

当前 `diag_stl.c:85-87` 同时检查 BSP domain 和 module 两级开关；排查前回读实际值，不能只开 module 就认为周期自检已运行。其它 domain 是否有同样属性要看实际注册与节点。
</EXTREMELY-IMPORTANT>

### module 级

路径 `/proc/ax_diag/domain<D>/module<M>/`（当前 SDK；现场目录以 `ls` 为准）。

| 属性 | 读写 | 含义 |
|---|---|---|
| `name` | RO | 模块名 |
| `count` | RO | 错误计数 |
| `mid` | RO | 模块 ID |
| `cycle_last` | RO | 上次周期自检执行情况 |
| `boot_error` | RO | 开机自检结果（**无 `d_` 前缀**） |
| `cycle_enable` | RW | 周期自检开关 |
| `cycle_ms` | RW | 周期毫秒 |

### error 级

路径 `/proc/ax_diag/domain<D>/module<M>/error<E>/`（当前 SDK；现场目录以 `ls` 为准）。

**只读**：`name`、`last_time`、`number`、`continu_cnt`、`debounce_cnt`、`pending`、`eid`

**可写**：`enable`、`prio`、`threshold`、`happen_debounce_times`、`resume_debounce_times`、`happen_max_snd_ms`、`happen_min_snd_ms`、`resume_max_snd_ms`、`resume_min_snd_ms`

### 排查时最有用的四个

| 属性 | 含义 |
|---|---|
| `number` | **累计上报次数** |
| `continu_cnt` | 连续计数 |
| `debounce_cnt` | 去抖计数 |
| `pending` | 是否挂起 |

<EXTREMELY-IMPORTANT>
**`number` 才是「真的上报了」的证据。**

日志在刷但 `number` 为 0，说明还在去抖过程中，没有正式上报故障。这是区分「设计预期的过程日志」和「真故障」的关键判据，心跳类问题尤其依赖它。
</EXTREMELY-IMPORTANT>

## diag_tools 参数速查

出处 `kernel/osdrv/private_drv/diag_core/tools/diag_tools`（ksh 脚本）的 `show_help()`。

| 参数 | 长选项 | 说明 |
|---|---|---|
| `-d` | `--domain` | 域 ID，默认 0 |
| `-m` | `--module` | 模块 ID |
| `-f` | `--fault` | 故障/错误 ID |
| `-i` | `--injection` | 执行注入 |
| `-t` | `--times` | 注入次数（`-i` 的子参数） |
| `-p` | `--probability` | 注入概率（`-i` 的子参数） |
| `-s` | `--show` | 查询信息 |
| `-C` | `--Config` | 配置 |
| `-v` | `--verbose` | 详细日志 |
| `-h` | `--help` | 帮助 |

`-C` 的子参数：`-enable`、`-happen_min`、`-happen_max`、`-resume_min`、`-resume_max`、`-prio`、`-threshold`、`-happen_debounce_times`、`-resume_debounce_times`、`-handle_config`。

环境变量 `DIAG_DEBUG=1` 开调试输出。

**`-i`、`-C`、`-s` 三者必须且只能存在一个。**

当前脚本的框架级 `-s` 和模块级 `-m M -s` 提前退出；错误级 `-m M -f E -s` 会走到末尾，尝试写 `domain0/cycle_enable=1`（`:613-653`）。严格只读取证时直接 `cat` 已确认的属性，不把所有 `-s` 调用都当成无副作用；板端脚本版本仍需核对。

官方示例：

```bash
diag_tools -s                      # 框架总览
diag_tools -m 0 -s                 # module 0 信息
diag_tools -m 0 -f 16 -s           # module 0 的 error 16 信息
diag_tools -m 0 -f 16 -i           # 注入
diag_tools -m 0 -f 16 -i -t 5      # 注入 5 次
```

注意 `Times:1` 是「本次注入次数」不是累计值，**验证注入是否生效要看 `number` 变化**，不是看 `Times`。

## ECM / FCU 接口

QNX 侧 ECM/FCU **没有 sysfs 属性**，只有设备节点 + 命令行工具：

| | ECM | FCU |
|---|---|---|
| 设备节点 | `/dev/ecm` | `/dev/fcu` |
| 驱动进程 | `m57_ecm_drv` | `fcu_drv` |
| 单例锁 | `/ecm_drv_singleton` | `/fcu_drv_singleton` |
| 查询/注入工具 | `ecm_fault` | `fcu_fault` |
| 用户态库 | `libax_ecmirq` | `libax_fcuirq` |
| 用户态 API | `ecm/lib/`（`ecm_fault_enable`/`disable`/`inject`） | `fcu/lib/fcu_api.c` |

工具的确切参数让客户跑 `-h` 或 `use <工具名>` 取。

<EXTREMELY-IMPORTANT>
**这是 Linux 相对 QNX 的排查优势**：Linux 有完整的 ECM/FCU sysfs，能直接读到每个通道的 `happed_num`、`mask`、`status`、`fsm`。QNX 只能通过工具查，粒度和便利性都差一些。

所以 Linux 侧的「三方对账」「读 `fsm` 判建链」这类手段在 QNX 上没有直接对应物。
</EXTREMELY-IMPORTANT>

## 进程与节点的对应关系

<EXTREMELY-IMPORTANT>
QNX 的诊断能力由**四个独立用户态进程**提供，节点存在与否直接取决于对应进程是否在跑：

| 进程 | 提供的节点 | 挂掉的后果 |
|---|---|---|
| `diag_core_drv` | `/proc/ax_diag/` | 整个诊断框架失效 |
| `diag_extend` | `/dev/diag_extend` | MID 87 扩展模块失效 |
| `m57_ecm_drv` | `/dev/ecm` | ECM 检测与上报失效 |
| `fcu_drv` | `/dev/fcu` | FCU 汇聚失效 |

**节点不存在时，先查进程在不在**，再怀疑编译开关：

```bash
pidin ar | grep -E "diag_core_drv|diag_extend|m57_ecm_drv|fcu_drv"
```

这与 Linux 不同——Linux 的节点缺失基本只有「没编进去」一种原因（内核模块不会单独崩溃）。
</EXTREMELY-IMPORTANT>

## 日志

<EXTREMELY-IMPORTANT>
**QNX 的 diag 日志走 `printf` 到进程 stdout，不是 slog2。**

`include/diag_log.h:124-128` 的 `diag_printf()` 内部是 `printf()`/`vprintf()`，`DIAG_LOG_PRINT` 宏只是包一层等级过滤。虽然 `slogger2` 在系统里跑，但 diag 框架**没有接 `slogf`**。

**不要让客户用 `slog2info` 找诊断日志。** 看串口输出，或客户自己的 stdout 重定向落点。
</EXTREMELY-IMPORTANT>

日志级别默认 7（info），调 `DIAG_LOG_LEVEL_VALUE` 可减少刷屏。

`diag-netlink` 前缀的刷屏行来自 `diag_netlink.c` 的 `diag_netlink_recv_error_handle`——对每条上报打一行 INFO，**无速率限制**。这个名字与 Linux netlink 无关，详见 `平台差异.md`。
