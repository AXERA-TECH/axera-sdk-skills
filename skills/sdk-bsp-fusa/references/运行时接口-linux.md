# 运行时接口

**S4 必读。** Linux 侧的 sysfs/debugfs 完整接口。

<EXTREMELY-IMPORTANT>
**三类路径不能混用。** 这是 Linux 侧最容易出错的地方——在错误的路径下找属性会得到「节点不存在」的假结论，然后误判成「功能没编进去」。

| 用途 | 路径 |
|---|---|
| 常规属性（domain/module/error 三级） | `/sys/devices/platform/axdiag/` |
| 全局控制（注入总开关等） | `/sys/class/fusa/diag/diag/` |
| 注入参数 | `/sys/kernel/debug/diag_fault_inject/` |
| ECM 通道 | `/sys/class/fusa/ecm/` |
| FCU 通道 | `/sys/class/fusa/fcu/` |
</EXTREMELY-IMPORTANT>

## 节点是数字命名

Linux 与 QNX 在这里完全不同：

| | Linux | QNX |
|---|---|---|
| 路径根 | `/sys/devices/platform/axdiag/` | `/proc/ax_diag/` |
| 层级命名 | `domain0/module0/error17/` | `domain0/dfc/diag_server_heartbeat/` |

**Linux 用数字，QNX 用名字。** 所以拿到符号名后要先换算成 MID/EID 数字才能拼出路径：

```
AX_MAIN_BSP_DFC_DIAG_SERVER_HEARTBEAT  (mask 0x00000011)
  → domain 0, module 0, event 17
  → /sys/devices/platform/axdiag/domain0/module0/error17/
```

反过来，从目录名读回符号名：

```bash
cat /sys/devices/platform/axdiag/domain0/module0/name        # 模块名
cat /sys/devices/platform/axdiag/domain0/module0/error17/name # 错误名
```

不确定有哪些模块时先列出来，别硬猜：

```bash
ls /sys/devices/platform/axdiag/domain0/
for d in /sys/devices/platform/axdiag/domain0/module*/; do
  printf "%s = %s\n" "$(basename $d)" "$(cat $d/name 2>/dev/null)"
done
```

## ① error 级属性

路径：`/sys/devices/platform/axdiag/domain<D>/module<M>/error<E>/`

出处 `kernel/linux/linux-6.1.83/drivers/soc/axera/fusa/diag_sysfs.c`。

**只读**：

| 属性 | 含义 | 行号 |
|---|---|---|
| `name` | 错误符号名 | :338 |
| `eid` | 错误 ID | :216 |
| `number` | **累计上报次数** | :166 |
| `continu_cnt` | 连续计数 | :176 |
| `debounce_cnt` | 去抖计数 | :186 |
| `last_time` | 上次发生时间 | :196 |
| `pending` | 是否挂起 | :206 |
| `status` | 当前状态 | :366 |
| `injectable` | 是否可注入 | :348 |

**可写**：

| 属性 | 含义 | 行号 |
|---|---|---|
| `enable` | 该错误是否使能 | :49 |
| `prio` | 优先级 | :78 |
| `threshold` | 阈值 | :104 |
| `happen_debounce_times` | 发生去抖次数 | :130 |
| `resume_debounce_times` | 恢复去抖次数 | :156 |
| `happen_max_snd_ms` | 发生上报最大间隔 | :242 |
| `happen_min_snd_ms` | 发生上报最小间隔 | :268 |
| `resume_max_snd_ms` | 恢复上报最大间隔 | :294 |
| `resume_min_snd_ms` | 恢复上报最小间隔 | :320 |
| `handle_config` | 三条动作链的冗余双 bit 编码 | :393 |

排查时最有用的四个：`number`（累计上报，判断有没有真的报过）、`continu_cnt`、`debounce_cnt`、`pending`。

<EXTREMELY-IMPORTANT>
**`number` 才是「真的上报了」的证据。** 日志在刷但 `number` 为 0，说明还在去抖过程中，没有正式上报故障。这是区分「设计预期的过程日志」和「真故障」的关键判据，心跳类问题尤其依赖它（FAQ-8）。
</EXTREMELY-IMPORTANT>

**`name` 是只读的。** 用户态若尝试写 `errorN/name` 会被忽略（`DEVICE_ATTR_RO(name)`，:338），不报错但也不生效。

## ② module 级属性

路径：`/sys/devices/platform/axdiag/domain<D>/module<M>/`

| 属性 | 读写 | 含义 | 行号 |
|---|---|---|---|
| `name` | RO | 模块名 | — |
| `count` | RO | 错误计数 | :427 |
| `mid` | RO | 模块 ID | :437 |
| `boot_error` | RO | 开机自检结果 | :515 |
| `cycle_enable` | RW | **模块级**周期自检开关，初值 **1** | :477 |
| `cycle_ms` | RW | 周期毫秒 | :502 |

`cycle_ms` 会被量化。内核 `HZ=250` 时 jiffy 粒度是 4ms，所以写进去的值和 `cat` 出来的不可能对任意毫秒精确对应——这是设计约束不是 bug，客户问起时直接解释。

## ③ domain 级属性

路径：`/sys/devices/platform/axdiag/domain<D>/`

出处 `diag_core.c`：

| 属性 | 读写 | 含义 | 行号 |
|---|---|---|---|
| `cycle_enable` | RW | **domain 级**周期自检开关，初值 **0** | :208 |
| `d_boot_error` | RO | domain 开机自检结果 | :340 |
| `detection_enable` | RW | 检测总开关 | :272 |
| `shutdown_start` | WO | 关机流程 | :245 |
| `suspend` | WO | 挂起 | :328 |
| `selftest` | WO | 触发自检 | :127 |
| `safety_debug` | WO | 安全调试 | :362 |

<EXTREMELY-IMPORTANT>
**`cycle_enable` 是两级的，两级都要开周期自检才跑。**

| 级别 | 初值 | 谁来开 |
|---|---|---|
| module 级（`diag_sysfs.c:477`） | **1** | 默认就开 |
| domain 级（`diag_core.c:208`，初始化在 :1332） | **0** | `ax_diag_service` 配置成功后写 1（`msp/component/diag/src/core/diag_core.cpp:444`） |

所以「节点都在但周期自检不跑」的**第一嫌疑是 `ax_diag_service` 没起来**，不是驱动坏了。这是 FAQ-2、FAQ-9 的核心。手动兜底：

```bash
cat /sys/devices/platform/axdiag/domain0/cycle_enable   # 0 = 没开
echo 1 > /sys/devices/platform/axdiag/domain0/cycle_enable
```

**注意 `d_boot_error` 的 `d_` 前缀**（domain 级），module 级是 `boot_error`（无前缀）。Buildroot 版 `diag_tools.sh` 就是在 domain 目录下读了 `boot_error`（缺前缀）所以读不到——这是个已实证的脚本 bug。
</EXTREMELY-IMPORTANT>

## ④ 全局控制

路径：`/sys/class/fusa/diag/diag/`

这是 `fusa_sys.c:66` 建的符号链接，指向 `axdiag` 设备。`inject_enable` 在这里（`diag_core.c:299`）：

```bash
cat /sys/class/fusa/diag/diag/inject_enable    # 注入总开关，必须为 1
echo 1 > /sys/class/fusa/diag/diag/inject_enable
```

<EXTREMELY-IMPORTANT>
**注入总开关是所有注入的前置门控。** `should_fail_diag_injection()` 第一件事就是检查 `dc->inject_enable`，为 false 直接返回不注入（`diag_fault_inject.c:70`）。

**已实证的坑**：SDK 里有两份 `diag_tools` 脚本，行为不同。

| 脚本 | `inject_enable` |
|---|---|
| `build/scripts/init_scripts/diag_tools` | 有，:125 `echo 1 > /sys/class/fusa/diag/diag/inject_enable` |
| `rootfs/buildroot-2024.02.2/package/diag_tools/diag_tools.sh` | **完全没有**（grep 零命中） |

客户镜像里装的若是 Buildroot 那版，`diag_tools -i` 会**回显正常但实际不注入**——因为总开关没开。这是「注入无效」类问题的头号原因。

取证：
```bash
grep -c inject_enable "$(command -v diag_tools)"    # 1=正确版, 0=残缺版
```
</EXTREMELY-IMPORTANT>

## ⑤ 注入参数（debugfs）

路径：`/sys/kernel/debug/diag_fault_inject/domain<D>/module<M>/error<E>/`

用的是 Linux 标准 fault-injection 框架（`select FAULT_INJECTION` + `FAULT_INJECTION_DEBUG_FS`），所以属性是框架标准的那套：`probability`、`interval`、`times`、`space`、`verbose` 等。

注入需要同时满足三个条件，缺一不可：

1. `CONFIG_DIAG_FAULT_INJECT=y`（且依赖 `DEBUG_KERNEL`）
2. `/sys/class/fusa/diag/diag/inject_enable` == 1
3. 该 error 的 `injectable` == 1

三条都满足了还不上报，再查 `cycle_enable` 两级和 debounce 配置。

## ⑥ ECM 通道

路径：`/sys/class/fusa/ecm/`

设备级（`ecm_sysfs.c:21-24`）：`fault_a_num`、`fault_b_num`、`ecm_num`

每通道 `fault<N>/`（`ecm_sysfs.c:62-72`）：

| 属性 | 含义 |
|---|---|
| `index` | 通道索引，用它和 `hwirq` 对账 |
| `mask` | 屏蔽状态 |
| `fault_ab` | A/B 路 |
| `happed_num` | **实际发生次数** |
| `inject_num` | 注入次数 |
| `last_time` | 上次发生时间 |
| `init` | 初始化状态 |
| `clear` | 清除（写） |
| `inject` | 注入（写） |

`hwirq = channel * 2 + ce_ue`（correctable=0/uncorrectable=1）。用 `fault<N>/index` 核对，别直接拿 channel 号当目录号。

开机后 `fault2/inject_num == 1` 且 `happed_num == 1` 是 boot check 自检的痕迹，**是预期**，不是残留故障。

## ⑦ FCU 通道

路径：`/sys/class/fusa/fcu/`

<EXTREMELY-IMPORTANT>
**FCU 的同步属性读取可能无限等待。** `fcu_virt.c:317` 使用 `wait_for_completion_timeout(..., MAX_SCHEDULE_TIMEOUT)`，等待不可中断，`timeout` 或强杀不能保证解除 D 状态。

已有读取卡住或 RPMsg 状态不明时，停止新增同步读取，先按 `取证命令-linux.md` 收集现有任务栈、RPMsg/握手日志和节点信息。无响应只说明请求未完成，未建链、发送失败或对端未回复都需进一步核实。

通信恢复确认后再串行读取；不要并发发起 FCU 请求。`fsm` 只是当前状态的旁证，不能单独证明整个链路正常。
</EXTREMELY-IMPORTANT>

设备级（`fcu_sysfs.c:157+`）：

`fcu_irq_max`、`trans_lock`(WO)、`permnt_lock`(WO)、`config_mode`、`config_timeout`、`alarm_timeout`、`fosu_enable`、`alarm_reset`(WO)、`eout_enable`、`eout_protocol`、`eout_reversal`、`eout_all_low`、`eout_fast`、`eout_rate`、`raw_status_l`、`raw_status_h`、`status_l`、`status_h`、`fsm`、`debug_eout`、`debug_reset`、`debug_nmi`、`debug_intr`、`debug_tick`

每通道 `fault<N>/`（`fcu_sysfs.c:112-130`）：

`name`、`index`、`happed_num`、`inject_num`、`init`、`last_time`、`mask`、`clear`(WO)、`enable`、`inject`(WO)、`eout`、`rst`、`alarm`、`raw_status`、`status`

`fsm` 反映 FCU 状态机当前状态；它是否能读回也受 RPMsg 请求与回复影响。

`mask` 只停止该来源的报告，**不会清除底层信号**（FAQ-23）。客户以为 mask 了就没事了，实际底层 fault 还在。

## ⑧ 框架是否在位

三条路径一起看，缺哪条说明哪块没编进去：

```bash
ls -d /sys/class/fusa /sys/devices/platform/axdiag /sys/kernel/debug/diag_fault_inject 2>&1
```

| 缺失项 | 说明 |
|---|---|
| `/sys/class/fusa` | `CONFIG_AXERA_FUSA_SUPPORT` 未开，或 fusa 模块未加载 |
| `/sys/devices/platform/axdiag` | `CONFIG_AXERA_DIAG_CORE` 未开 |
| `/sys/kernel/debug/diag_fault_inject` | `CONFIG_DIAG_FAULT_INJECT` 未开，或 debugfs 未挂载 |

`axdiag` 是 `fusa_sys.c:49` 用 `platform_device_alloc("axdiag", -1)` **动态创建**的，走 name 匹配。所以 **DTS 里没有 `axera,diag-core` 节点是正常的**，不能据此判断 diagcore 未使能（FAQ-1）。实测 `m57.dtsi` 里确实没有该节点。
