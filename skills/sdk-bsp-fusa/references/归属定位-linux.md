# 归属定位 · Linux 补充

**S2 用。先读 `归属定位-公共.md`，再读本文。**

公共部分已覆盖：三步定位法、mask 公式、domain 枚举、module 全表、ECM/FCU 两级关系、双层检查四步。本文只写 Linux 特有的部分。

## Linux 侧的路径与写法

| 项 | 值 |
|---|---|
| 错误码表 | `<SDK>/header/external/ax_diag_type_ex.h`（739 行） |
| mask 公式出处 | `header/external/ax_diag_type.h:126-128` |
| domain / MID 枚举出处 | `kernel/linux/linux-6.1.83/include/linux/diag_enum.h:12-77` |
| 符号名前缀 | **无 `AX_`**，如 `*_DFC_*`、`*_ECM_*`、`*_FCU_SAFETY_*` |
| 日志形态 | **两种**（见下） |

## 两种日志形态

| 形态 | 出处 | 样子 |
|---|---|---|
| **A · 直接给 mask** | 用户态、诊断信息、Jira 标题 | `error_mask: 0x80000011` |
| **B · 给三元组** | kernel netlink 打印（`diag_netlink.c:65`） | `err ID: 29 module ID: 45 domain ID: 0` |

形态 B 的出处是真 netlink 上报路径的 `pr_info`，**无速率限制**——这是 dmesg 刷屏的直接来源。

<EXTREMELY-IMPORTANT>
**wire 协议只有 8 bit mid。**

用户态 mask 给 module 留了 11 bit（`0x7FF`），但 kernel↔用户态的 netlink 报文里 `mid` 是 `uint8_t`（`include/uapi/linux/diag_netlink.h`）。

当前 MID 最大 88，还没撞上 255 的边界，但**看到 module 号 > 255 时要意识到这是解码错了**，不是真有那个模块。
</EXTREMELY-IMPORTANT>

## Linux 特有：三条动作链要分开判

<EXTREMELY-IMPORTANT>
**kernel 检测到故障 ≠ 用户态或 SafetyIsland 收到。**

三条动作链由 `handle_config` 独立控制，**report 成功不能证明 forward 也成功**。
</EXTREMELY-IMPORTANT>

```
diagnosis_error_send()
  └─ debounce 判定
       └─ 入队，诊断线程处理
            ├─ report 位  → Netlink → 用户态 app
            ├─ forward 位 → RPMsg + E2E P04 → SafetyIsland
            └─ reset 位   → panic/reset
```

客户说「没收到故障」时**先问清是哪一端**：

| 哪端没收到 | 查什么 |
|---|---|
| 用户态 app | report 位、`ax_diag_service` 是否在跑、Netlink handshake、error ACK |
| SafetyIsland | forward 位、RPMsg endpoint、handshake、E2E P04 日志 |
| 两端都没收到 | 事件是否达到 debounce 条件、`handle_config` 是否写入了正确节点 |

### handle_config 的冗余双 bit 编码

`handle_config` 用**冗余双 bit** 编码抗位翻转：

| 位段 | 含义 |
|---|---|
| `[1:0]` | app report |
| `[3:2]` | forward |
| `[5:4]` | reset |

每段**只允许 `00` 或 `11`**。出现 `01`/`10` 会被判为 bit-flip 并报 `DIAG_CORE_BIT_FLIP`。

所以客户看到 `handle_config error` 类报错时，先看写入的值是不是合法的冗余编码。

**当前默认值 `0x0f`** = report 开、forward 开、reset 关。

代码侧：`diag_check_handle_config()` 先校验冗余双 bit（`diag_core.c:1068` 打 `handle_config error`），再按位分派。reset 位触发 `panic()`（`diag_core.c:1133`）。

## ECM 排查清单（Linux，6 条）

ECM 是**就地检测层**。Linux 侧 ECM 有完整 sysfs 接口（QNX 只有 `ecm_fault` 命令行工具），这是排查上的优势。属性清单见 `运行时接口-linux.md`。

1. **STL 初始化失败不会让 probe 失败。** `ecm.c` 里 STL 初始化失败只打 `dev_err(... "Fail to stl init")` 就继续走。结果是 ECM 本体正常（中断能收、通道计数在涨），但 `axdiag/domain0/module<17..26>/` 缺失。客户现象是「ECM 通道有计数，但 diag 里查不到 ECM 模块」。取证：`dmesg | grep "Fail to stl init"`。

2. **`hwirq` 的换算关系**：DT 第一个 cell 是 channel，`hwirq = channel * 2 + ce_ue`（correctable=0 / uncorrectable=1）。查故障要用 `fault<N>/index` 对账，别直接拿 channel 号当 `fault` 目录号。

3. **三方对账**：`/proc/interrupts` 的 IRQ 计数、各通道 `happed_num`、diag 侧 `number`。三者不一致说明链路某段断了，能定位到具体哪一段。

4. **开机后 `fault2/inject_num == 1` 是预期**，不是残留故障。ECM boot check 启动时会对某个通道真实注入一次做自检。别把它当故障查。

5. **Kconfig 靠 `select` 带出，defconfig 里搜不到不代表没开。** `CONFIG_AXERA_ECM` 通常不显式写在 defconfig，而是被 `CONFIG_AXERA_ECM_FAULT=m` 之类 `select` 出来的。**判断必须查 `.config`，不是 defconfig。**

6. **NPU 等可上下电的子系统**，硬件状态切换期间必须暂停 monitor，资源恢复完成后再开启，否则会误报。

## FCU 排查清单（Linux，6 条）

FCU 是**跨域汇聚层**——收集各处的 fault 并决定对外行为（EOUT 引脚、复位、告警）。

<EXTREMELY-IMPORTANT>
**Linux 侧 FCU 是纯转发实现。** DT compatible 是 `axera,fcu_virt`，**没有 `reg` 属性**——它不直接操作硬件寄存器，所有请求经 RPMsg 转发给 SafetyIsland 执行。这和 QNX 侧直接操作硬件是架构性差异。

后果：**FCU 同步读取可能不可中断地无限等待，`timeout` 或放后台不能保证结束请求。** 已有读取卡住或通信状态不明时，停止新增同步读取，先取现有任务栈、RPMsg/握手日志；无响应不能单独证明未建链。通信恢复确认后再串行访问。
</EXTREMELY-IMPORTANT>

1. **`FCU_HANDLER_TIMEOUT` 表示处理过程超时，不等同于 FCU 寄存器损坏。** 这是最容易被误读的一个码。偶发是耗时抖动；**持续大量出现**才需查处理链路为何变慢。而且它经常是更早的原始故障拖慢系统后的连锁结果，**要先看时间线**。

2. **并发访问会串台。** 同时读 `fault0/*` 和 FCU 级属性会互相抢 completion，返回值可能对不上号。调试时**串行访问**，一条一条来。

3. **DTS 前置条件**：板级 DTS 里要有 `&fusa { status = "okay"; }`，且 `/sys/devices/platform` 下能看到 fcu 节点。这两条不满足时所有 FCU 排查都是白做。

4. **`/proc/interrupts` 里 chip 名应为 `FCU`。** 看不到说明中断没注册。边界情况：`fusa` disabled、`fcu_num` 缺失、`hwirq` 超出 `fcu_num` 范围。

5. **注入是 sysfs 写 `fault<N>/inject`**，不是命令行工具。写完看 `happed_num` 和 diag 侧 `number` 是否变化。

6. **Kconfig 同样靠 `select`**：`AXERA_FCU_SYSFS` select `AXERA_FCU`，`AXERA_FCU` select `AXERA_FUSA_SUPPORT`。defconfig 搜不到 `CONFIG_AXERA_FCU=y` 不代表未启用，查 `.config`。

## 双层检查在 Linux 侧的落点

按公共文件的四步走，Linux 侧的重点是：

1. 看 MID 17~26 区间有无相关 ECM 项
2. 若有，走上面 ECM 清单——尤其**第 1 条（STL 初始化失败静默）**和**第 5 条（查 `.config`）**
3. 确认上报是否经 FCU 转发到 SafetyIsland——若是，走 FCU 清单
4. 排除两层后才认定问题在子系统自身

Linux 侧还要多问一句：**三条动作链里断在哪一条**（见上文）。这是 Linux 独有的一层，QNX 没有对应物。
