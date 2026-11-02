# Linux 代码地图

**S5 用。** 定位代码、找判定依据。

所有路径相对客户 SDK 根目录（含 `.repo/` 的那一层）。**行号会随版本漂移，只作起点参考——落笔前必须打开文件核实。**

## 四域架构

Linux FuSa 是四方参与，比 QNX 多一层用户态服务的明确边界：

```
SafetyIsland R 核          Linux kernel diagcore        用户态 AxDiagCore         客户 app
 SafetyIsland/driver/    drivers/soc/axera/fusa/     msp/component/diag/
      │                          │                          │
      └──── RPMsg + E2E P04 ─────┤                          │
                                 └────── Netlink ───────────┴──────→
```

排查时按「哪一级先报」回溯：

| 谁先报 | 多半是 |
|---|---|
| R 核先报 | 用户态→R 核链路或 RPMsg |
| 用户态先报 | kernel↔用户态 Netlink |
| kernel 刷屏 | 用户态服务未起或被拖慢 |

## Kernel 侧 — `kernel/linux/linux-6.1.83/drivers/soc/axera/fusa/`

| 文件 | 职责 |
|---|---|
| `diag_core.c` | 框架核心、模块注册、domain 级属性、动作链分派 |
| `diag_core.h` | 内部阈值常量 |
| `diag_stl.c` | 周期自检、心跳检查、去抖判定、错误节点生命周期 |
| `diag_netlink.c` | 与用户态的 Netlink 通信、错误上报打印 |
| `diag_rpmsg.c` / `diag_rpmsg.h` | 与 SafetyIsland 的 RPMsg 通道 |
| `diag_sysfs.c` | module/error 级 sysfs 属性定义 |
| `diag_sys_common.c` | sysfs 公共逻辑、module 初始化 |
| `diag_fault_inject.c` | 故障注入 |
| `diag_safety_sys.c` | 安全域相关 |
| `diag_selftest.c` | 自检 |
| `diag_extend.c` | 客户扩展模块（MID 87） |
| `diag_helper.c` | 辅助函数 |
| `diag_api_test.c` | API 测试 |
| `fusa_sys.c` | 建 `/sys/class/fusa` + 动态注册 `axdiag` platform device |
| `ddr_stl/` | DDR STL 子目录 |
| `Kconfig` / `Makefile` | 编译开关 |

ECM/FCU 是**独立目录**（不在 fusa/ 下）：

- `drivers/soc/axera/ecm/` — `ecm.c`、`ecm_sysfs.c`、`ecm_stl.c`、`ecm_fault.c`
- `drivers/soc/axera/fcu/` — `fcu_virt.c`、`fcu_hal.c`、`fcu_sysfs.c`、`fcu_interrupt.c`

对照 QNX：那边全在 `kernel/osdrv/private_drv/{diag_core,ecm,fcu}/`。

### 关键判定点

**心跳去抖**（`diag_stl.c`）— 这是理解 FAQ-8 的核心：

```c
:148  if (wait_for_completion_timeout(&dc->heartbeat_complete,
          msecs_to_jiffies(SERVER_HEARTBEAT_TIMEOUT)) == 0UL
:149      || should_fail_diag_injection(&de_heartbeat_err)) {
:150      heartbeat_time++;
:151      dev_info(dev, "heartbeat time:%d\n", heartbeat_time);   // INFO，会刷屏，不是故障
:152      // The timeout for this heartbeat will only be 20ms in the next loop.
          // When the timeout count is 5, the actual timeout is 4 rounds.
:153      if (heartbeat_time > 5) {
:154          dev_err(dev, "heartbeat timeout.\n");               // ERR，才是真故障
              ...
```

单轮等待阈值 `SERVER_HEARTBEAT_TIMEOUT = 5`（ms），定义在 `diag_core.h:32`。

<EXTREMELY-IMPORTANT>
**`:152` 的注释与代码不符。** 注释说「timeout count is 5 时实际是 4 轮」，代码是 `heartbeat_time > 5`，即第 6 次才报。客户若按注释算延迟会差一轮（约 20ms）。**以代码为准。**

这不影响功能，但解释机制时别照抄注释。
</EXTREMELY-IMPORTANT>

`heartbeat_time` 是 `static int`（`:74`），跨调用累计；`:80` 处 `heartbeat_time == 0` 时才重新 arm completion 并发心跳。

**心跳的另一侧**（`diag_stl.c:139-146`）：SafetyIsland 心跳挂起时回 `0xdeadbeef` 应答；停止心跳时（`diag_stop_heartbeat_check`，:49-56）发 `0xdead0000`。这两个魔数在日志里出现是握手标记，不是内存损坏。

**刷屏来源**（`diag_netlink.c:65`）：

```c
pr_info("err ID: %d module ID: %d domain ID: %d\n", ...);
```

**无速率限制**，用户态服务未建链时会 loop 重发，所以 dmesg 刷屏是预期行为。处置方式是起 `ax_diag_service`，或调 `/proc/sys/kernel/printk` 降日志级别——不是去改代码。

**错误节点生命周期**（`diag_stl.c`）— 理解 `handle overdue` 和 RCU stall 类问题的关键：

同一个 `diag_core_error` 同时挂在 report rb-tree 和 `err_timeout_head` 两处。释放需要双方都完成：

| 事件 | 动作 | 行号 |
|---|---|---|
| report 完成 | `report_flag += 1` | :115 判 `== 0x1` |
| ACK 收到 | `report_flag += 2` | :36 `atomic_add(2, ...)` |
| **仅 `0x3` 可释放** | 两者都完成 | :107 判 `== 0x3` |

错误节点来自 **512 节点的 mempool**（`diag_core.h:34` `DIAG_DCE_MEMPOOL_MIN 512`），`GFP_ATOMIC` 分配。**错误风暴时 ACK 跟不上，节点占满 mempool** → 后续故障入队失败、timeout list 堆积 → RCU stall / Call trace。这条链是 FAQ-11、FAQ-12 的机制根源。

**`handle overdue` 阈值**（`diag_core.c:1111`）：

```c
pr_warn("module%d(%s) error%d(%s) handle overdue for %llums.\n", ...);
```

超时是 20ms。**它是症状不是根因**——出现说明诊断线程被拖慢了，要去找拖慢它的东西（FAQ-10）。

**动作链分派**（`diag_core.c`）：`diag_check_handle_config()` 先校验冗余双 bit（`:1068` 打 `handle_config error`），再按位分派 report / forward / reset。reset 位触发 `panic()`（`:1133`）。

**cycle_enable 两级初值**：

| 级别 | 初值 | 出处 |
|---|---|---|
| module | **1** | `diag_sys_common.c:196` `atomic_set(&module_sys->cycle_enable, 1)` |
| domain | **0** | `diag_core.c:1332` `atomic_set(&domain_sys->cycle_enable, 0)` |

domain 级要等用户态服务配置成功才开——见 `运行时接口-linux.md` 的详细说明。

**注入门控**（`diag_fault_inject.c:70`）：`should_fail_diag_injection()` 首先检查 `dc->inject_enable`，false 直接返回。这是「注入无效」的头号原因。

## 用户态 — `msp/component/diag/`

| 文件 | 职责 |
|---|---|
| `src/core/netlink_monitor.cpp` | 心跳定时器、与 kernel 的 Netlink、配置下发 |
| `src/core/diag_core.cpp` | 错误回调、上报处理、domain cycle_enable 开启 |
| `src/core/diag_event_manager.cpp` | 事件管理 |
| `src/core/bsp_diag.h` | BSP 诊断接口 |
| `config/diag_domain_*.json` | 各域运行时配置（6 个 domain） |

### 关键判定点

**domain cycle_enable 的开启点**（`diag_core.cpp:444`）：

```cpp
SetDomainCycleEnable(DIAG_DOMAIN_ID_MAIN_BSP, 1);
```

实现在 `:873`。**服务没起 → 这行不执行 → domain cycle_enable 保持 0 → 周期自检不跑。**

<EXTREMELY-IMPORTANT>
**已实证的属性名不一致**（`netlink_monitor.cpp:103`）：

```cpp
std::string resumeHappenMaxsndFile = filePath + "resume_happen_max_snd_ms";
```

kernel 侧实际属性名是 **`happen_max_snd_ms`**（`diag_sysfs.c:242`），**没有** `resume_happen_max_snd_ms` 这个属性。`fopen()` 失败后代码静默跳过，所以**配置看起来下发成功，实际没生效**。

这是「改 JSON 后 max interval 不生效」的直接原因（FAQ-5、FAQ-7、FAQ-27 都指向它）。

**结论一律落在回读板端 sysfs 实际值**，不要相信服务返回成功：
```bash
cat /sys/devices/platform/axdiag/domain0/module<M>/error<E>/happen_max_snd_ms
```

性质：这是当前 SDK 的静态代码事实。**告知客户时说清「缺陷性质需原厂确认」**，不要自行断定是已修还是未修。
</EXTREMELY-IMPORTANT>

**配置四层链路** — 改了上游不等于下游生效：

```
源 Excel (build/platforms/.../Fault_diagnosis_event_list.xlsx)
   ↓  make PLAT=<平台> fusa_config
生成物 (msp/component/diag/config/*.json + header/external/*.h)
   ↓  编译打包
rootfs 里的实际 JSON
   ↓  ax_diag_service 启动下发
板端 sysfs 实际值   ← 唯一可信的验证点
```

每一步都可能断。查的时候从下往上倒推最快。

## SafetyIsland 侧 — `SafetyIsland/`

- `driver/ecm/`、`driver/fcu/`、`driver/diag/`
- 与 QNX 侧**基本一致**（实测 `fcu/Fcu.c` 仅差 1 行 fault 表项）

所以 SafetyIsland 相关问题，QNX 的资料和结论大体可以借用——这是两平台唯一能直接互通的部分。

## 错误码表与 mask

| 项 | 位置 | 说明 |
|---|---|---|
| 错误码表 | `header/external/ax_diag_type_ex.h` | 739 行，620 个条目 |
| 同一份副本 | `msp/fusa_out/include/ax_diag_type_ex.h` | 内容相同 |
| mask 公式 | `header/external/ax_diag_type.h:126-128` | `(domain<<27) \| ((mid & 0x7FF)<<16) \| eid` |
| domain / MID 枚举 | `kernel/linux/linux-6.1.83/include/linux/diag_enum.h:12-77` | 见 `归属定位-公共.md` 全表 |

**错误码表和 MID 表与 QNX 逐字节/逐行相同。** 所以 mask 解码结果两平台通用，可以互相印证。

## 编译开关

全部是 Kconfig，在 `drivers/soc/axera/fusa/Kconfig`（对照 QNX 的 `SUPPORT_AX_DIAG` 之类 Makefile 宏）。

| 符号 | 类型 | 控制 |
|---|---|---|
| `CONFIG_AXERA_FUSA_SUPPORT` | bool，默认 y | FuSa 总开关，依赖 `NET` |
| `CONFIG_AXERA_DIAG_CORE` | tristate | 诊断框架核心，select `AXERA_E2E_KER` |
| `CONFIG_DIAG_CORE_SELFTEST` | bool | 自检 |
| `CONFIG_DIAG_FAULT_INJECT` | bool | 故障注入，依赖 `DEBUG_KERNEL`，select `FAULT_INJECTION` |
| `CONFIG_AXERA_DIAG_TEST` | tristate | 诊断测试 |
| `CONFIG_AXERA_DDR_STL` | bool | DDR STL |
| `CONFIG_AXERA_{MIPI_RX,GDC,VPP,VGP,FBCDC,ISP,IVE,CVE,NPU,MM_CDMA}_STL` | bool | 各子系统 STL |
| `CONFIG_AXERA_X2F_SCCB_PEC` | tristate，默认 n | SCCB PEC |

ECM/FCU 的开关在各自目录的 Kconfig：`CONFIG_AXERA_ECM`、`_ECM_SYSFS`、`_ECM_STL`、`_ECM_FAULT`；`CONFIG_AXERA_FCU`、`_FCU_SYSFS`。

fusa 配置片段：`kernel/linux/linux-6.1.83/arch/arm64/configs/fusa/common_fusa.config`（30 项，全部 `=y`）。

<EXTREMELY-IMPORTANT>
**判断某开关是否开启必须查 `.config`，不能查 defconfig。**

原因：很多符号靠 `select` 间接带出。例如 defconfig 里通常只显式写 `CONFIG_AXERA_ECM_FAULT=m`，`CONFIG_AXERA_ECM` 本体是被 `select` 出来的，defconfig 里搜不到。同理 `AXERA_FCU_SYSFS` select `AXERA_FCU` select `AXERA_FUSA_SUPPORT`。

**搜 defconfig 得出「没开」是错的结论。** 正确查法：

```bash
# 板端（若内核开了 IKCONFIG）
zcat /proc/config.gz | grep -E "AXERA_(FUSA|DIAG|ECM|FCU)|DIAG_FAULT_INJECT"
# SDK 侧构建产物
grep -E "AXERA_(FUSA|DIAG|ECM|FCU)|DIAG_FAULT_INJECT" <SDK>/kernel/linux/linux-6.1.83/.config
```

板端没有 `/proc/config.gz` 时，退而看模块是否加载（`lsmod | grep -E "diag|ecm|fcu"`）和 sysfs 节点是否存在——见 `运行时接口-linux.md` 第 ⑧ 节。
</EXTREMELY-IMPORTANT>

## 代码特征检测的正确做法

<EXTREMELY-IMPORTANT>
不要照抄 FAQ 里的关键词就 grep。已实测出假阴性。

正确顺序：

1. 先读 `docs/internal/domain/bsp/{diagcore,ecm,fcu}.md` 和实际代码，确认**当前实现用什么原语**
2. 再决定搜什么关键词
3. 用 `rg -c`（计数）或 `rg -l`（列文件），比看匹配文本可靠
4. 搜不到时，**不能判定「未含修复」**——可能是重构搬家、原语不同、宏包裹

Linux / QNX 原语对照（若你手上的资料来自 QNX 分支）：

| Linux | QNX |
|---|---|
| `local_irq_save` / `spin_lock_irqsave` | `InterruptLock` / `InterruptDisable` |
| `spin_lock` / `mutex_lock` | `pthread_mutex_lock` |
| `wait_for_completion_timeout` | `MsgReceivePulse` + `TimerTimeout` |
| `msecs_to_jiffies` | `nsec` 直接计算 |
| `pr_info` / `dev_err` | `slogf` / `printf` |
</EXTREMELY-IMPORTANT>

## SDK 内权威文档

比 FAQ 更详细的机制说明，FAQ 未覆盖时优先读这些，**不要猜**：

| 文档 | 内容 |
|---|---|
| `docs/internal/domain/bsp/diagcore.md` | diag 框架（QNX 侧叫 `fusa_diagcore.md`） |
| `docs/internal/domain/bsp/ecm.md` | ECM 机制、设计决策、坑 |
| `docs/internal/domain/bsp/fcu.md` | FCU 机制、设计决策、坑 |

统一 8 段式模板：`requirements` / `overview` / `design-decisions` / `api-contracts` / `pitfalls` / `test-strategy` / `review-findings`。

**`pitfalls` 段落最有用**——已知坑清单，往往直接命中客户的问题。这三份文档经逐条比对与当前代码高度一致，可以直接引用其结论。

注意：`diagcore.md` 的 `requirements` 和 `api-contracts` 段是空的；三份文档的 `review-findings` 段当前均为空。`docs/internal/domain/fusa/readme.md` 只有占位模板文本，不用读。

**Linux 侧没有 review 中的补丁目录。** QNX 侧有 `code_review/`、`doc_modify/`、`fcu_codereview/`，Linux 工作区实测三个都不存在（也不在 manifest 里）。所以不用去那里找未合入的修复。

## 常见排查入口速查

| 现象关键词 | 先看哪里 |
|---|---|
| `heartbeat time:N` | `diag_stl.c:150-151` 去抖 INFO，不是故障 |
| `heartbeat timeout.` | `diag_stl.c:153-154`，`> 5` 才报 |
| `err ID/module ID/domain ID` 刷屏 | `diag_netlink.c:65`，无限流，服务未起会 loop |
| `handle overdue for Nms` | `diag_core.c:1111`，20ms 阈值，是症状不是根因 |
| `handle_config error` | `diag_core.c:1068`，冗余双 bit 校验失败 |
| Call trace / RCU stall | `diag_stl.c` 的 `report_flag` 0x3 释放条件 + 512 mempool |
| 注入无效 | ① `inject_enable` ② `diag_tools` 是哪一版 ③ `injectable` ④ 两级 `cycle_enable` |
| 改 JSON 不生效 | `netlink_monitor.cpp:103` 属性名 + 回读板端 sysfs |
| 周期自检不跑 | domain `cycle_enable`（初值 0）+ `ax_diag_service` 是否在跑 |
| `FCU_HANDLER_TIMEOUT` | 先看时间线找首个原始故障，再查 FCU |
| ECM 有计数但 diag 无模块 | `dmesg \| grep "Fail to stl init"` |
| 开关不生效 | 查 `.config` 不是 defconfig |
| `cycle_ms` 读回不符 | HZ=250，jiffy 粒度 4ms，量化是必然 |

## 已实证的当前代码不一致

这两条我在当前 SDK 上直接验证过，客户现象命中时可以给结论，但要说清**「这是当前 SDK 的静态代码事实，缺陷性质需原厂确认」**：

**① 用户态属性名写错** — `netlink_monitor.cpp:103` 用 `resume_happen_max_snd_ms`，kernel 实际是 `happen_max_snd_ms`（`diag_sysfs.c:242`）。`fopen()` 失败静默跳过，配置看似成功实际未生效。

**② Buildroot 版 diag_tools 漏开注入总开关** — `rootfs/buildroot-2024.02.2/package/diag_tools/diag_tools.sh` 里 grep `inject_enable` 零命中，而 `build/scripts/init_scripts/diag_tools:125` 有。装了残缺版的镜像上 `diag_tools -i` 回显正常但不注入。同一脚本还在 domain 目录读 `boot_error`（应为 `d_boot_error`）。

判为「疑似新缺陷」前先比对这两条，可能已经在列。其它可疑点见 `已知可疑点-linux.md`。