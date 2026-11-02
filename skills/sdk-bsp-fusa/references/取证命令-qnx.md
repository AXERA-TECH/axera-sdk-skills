# 取证命令 · QNX

**S4 用。先读 `取证框架.md`（使用原则、症状分支、回填用法），本文只给 QNX 命令体。**

属性含义与 `diag_tools` 参数见 `运行时接口-qnx.md`。

## 路径确认（第一条必给）

`/proc/ax_diag` 的层级是 domain → module → error 三层。当前 SDK 使用 `domain0/module0/error17` 数字目录，历史资料可能有名字示例；先列现场目录并核对 `name`，不要直接拼路径：

<EXTREMELY-IMPORTANT>
**这条命令兼作平台校验。** 若 S1 的平台判定是客户自报的（而非硬判据命中），这里就是验证点：

- `/proc/ax_diag/` 有内容 → 确认是 QNX，继续
- 该路径不存在，改跑 `ls /sys/devices/platform/axdiag/` 却有内容 → **客户自报错了，实际是 Linux**

发现不符时**立即停下改判**，切换到 `取证命令-linux.md`，并把已给出的结论重新走一遍。不要继续用 QNX 命令。
</EXTREMELY-IMPORTANT>

```bash
# ① 确认 diag 节点存在及其结构
ls /proc/ax_diag/
ls /proc/ax_diag/domain0/
```

当前 SDK 既有 module 级 `cycle_enable`，也通过 BSP 额外属性组注册了 `/proc/ax_diag/domain0/cycle_enable`（`diag_core.c:1455-1478,1722-1729`）。BSP 周期自检需要两级都开启，以实际目录和回读为准。

## A 必做项（所有症状通用）

```bash
# ② 四个诊断进程是否都在（QNX 特有：任一挂掉都会静默失效）
pidin ar | grep -E "diag_core_drv|diag_extend|m57_ecm_drv|fcu_drv"

# ③ 版本确认
cat /proc/ax_diag/version 2>/dev/null

# ④ 诊断框架总览（哪些域/模块注册了、各自计数）
diag_tools -s

# ⑤ CPU 占用（大量结论以 CPU < 80% 为前提）
hogs -n -%1 | head -20
```

看什么：

<EXTREMELY-IMPORTANT>
**② 是 QNX 侧的首要项。** 四个进程是独立的用户态程序，任一崩溃退出后系统照常跑，但**诊断能力静默丢失——故障不再上报**。

客户报「以前有诊断日志，最近没有了」时，先看这一条，不要当成「没有故障所以没日志」。
</EXTREMELY-IMPORTANT>

- `diag_tools -s` 输出是后续一切的基线。
- CPU 占用超过 80% 时，心跳/周期自检类误报基本可以直接归因到负载。
- `hogs` 是 QNX 自带工具。若客户环境没有，改用 `pidin times` 或客户自己的负载监控手段。

## B 按症状分支

### 1. 心跳类（module 0，`heartbeat` 关键词）

```bash
# 该错误的计数与去抖状态
# 当前 SDK 数字目录示例；先确认节点存在并核对 name
P=/proc/ax_diag/domain0/module0/error17
for f in number continu_cnt debounce_cnt pending; do
  printf "%-14s = %s\n" "$f" "$(cat $P/$f 2>&1)"
done

# diag server 进程是否在跑
pidin ar | grep -i diag
```

看什么：`number` 是累计上报次数。若 `number` 为 0 但日志在刷 `heartbeat time:N`，说明只是去抖过程中的 INFO 计数，**没有真正上报故障**——可直接判为设计预期。

模块名和错误名的确切拼写以 `ls` 结果为准。

### 2. 周期自检类（`cyclecheck`、`CYCLECHECK` 关键词）

```bash
# 替换为已列出并核对 name 的实际 module 目录
P='/proc/ax_diag/domain0/module<M>'
cat /proc/ax_diag/domain0/cycle_enable
for f in cycle_enable cycle_ms cycle_last boot_error; do
  printf "%-14s = %s\n" "$f" "$(cat $P/$f 2>&1)"
done
```

看什么：`cycle_enable` 为 0 表示周期自检没开——若客户抱怨「注入了没上报」，这就是原因。`cycle_ms` 是周期，`cycle_last` 是上次执行情况，`boot_error` 是开机自检结果。

当前 SDK 的 BSP domain0 与 module 两级开关都要检查；不能因模块级为 1 就排除 domain0 未开启。其它域按其实际属性检查。

### 3. 注入验证类（客户说「注入没生效」）

```bash
# 注入前后对比该错误的 number 计数
cat /proc/ax_diag/inject_enable  # 当前 SDK 的总开关；diag_tools -i 会尝试打开
diag_tools -m <module> -f <event> -s
diag_tools -m <module> -f <event> -i
diag_tools -m <module> -f <event> -s
```

看什么：**看两次 `-s` 的 `number` 是否变化**，不要看 `Times`。`Times:1` 是「本次注入次数」不是累计值，所以不变是正常的；注入路径也不产生 call-trace。

若 `number` 没变，先确认该模块的 `cycle_enable`。

### 4. 配置不生效类（改了 Excel/JSON 没反应）

<EXTREMELY-IMPORTANT>
**唯一可信的验证点是板端节点实际值。** 服务返回成功、JSON 内容正确都不算。
</EXTREMELY-IMPORTANT>

```bash
# 回读实际生效值
# 替换为已确认存在的实际事件目录
P='/proc/ax_diag/domain<D>/module<M>/error<E>'
for f in enable prio threshold happen_debounce_times resume_debounce_times \
         happen_max_snd_ms happen_min_snd_ms resume_max_snd_ms resume_min_snd_ms; do
  printf "%-24s = %s\n" "$f" "$(cat $P/$f 2>&1)"
done
```

看什么：与客户期望的配置值逐项比对。

四层链路任一段断了都会表现为「不生效」：Excel → 生成物 → rootfs JSON → 板端节点。**从下往上倒推最快。**

### 5. ECM 类（module 17~26，或 `ECM_*` 符号名）

```bash
# ECM 驱动进程与节点
pidin ar | grep -i ecm
ls -l /dev/ecm

# 该 ECM 子系统的故障状态
ecm_fault <查询参数>
```

`ecm_fault` 的确切参数让客户跑 `ecm_fault -h` 或 `use ecm_fault` 取。

看什么：

- 先确认 `/dev/ecm` 存在且 `m57_ecm_drv` 进程在跑。**进程不在 = ECM 诊断完全失效**。
- 若客户报「ECM 注入没反应」，重点查该子系统的 `fault_a_irq` 是否为 0——为 0 则不注册 FCU 回调，通知路径根本不通（见 `归属定位-qnx.md` 的 ECM 清单第 1 项）。
- **开机 8 秒内的现象要考虑 ECM STL 初始化延后窗口**（ECM 清单第 3 项）。

### 6. FCU 类（`FCU_SAFETY`、`fcu handler timeout`、`0x800A0010`）

```bash
# FCU 驱动进程与节点
pidin ar | grep -i fcu
ls -l /dev/fcu

# FCU 故障查询
fcu_fault <查询参数>
```

`fcu_fault` 参数同样让客户跑 `-h` 取。

看什么：`0x800A0010` 是 handler 超过 50ms 的超时上报，**偶发是设计预期**（HAPS 环境阈值 100ms）。要区分偶发和持续——**持续大量出现**才需查 handler 为何变慢。让客户统计单位时间内该码出现次数。

当前 QNX SDK 的 FCU 硬件控制/状态查询也经 RPMSG 转发；部分查询有约 1 秒的条件等待，本地统计可直接返回，不能把该等待当成整个工具调用的退出保证。先串行查询；已有调用卡住或超时时停止重复请求，取现有 `pidin` 阻塞态、驱动标准输出和 RPMSG/对端日志，核对发送及回复。不能因 `/dev/fcu` 存在就排除通信问题，也不要照搬 Linux 的不可中断无限等待结论。

### 7. 压测/稳定性类

```bash
# 内存与 /tmp 占用（r_core_log 撑爆是已知问题）
df -h /tmp
ls -lhS /tmp | head -10

# 内存总量
pidin info | head -5

# 卡死时看线程阻塞态（QNX 特有）
pidin -p diag_core_drv
pidin -p fcu_drv
```

看什么：

- r_core_log 过大吃光内存是已知问题，**应限制在 ≤ 1M**。`/tmp` 满会导致 `malloc` 失败连带心跳超时。
- **`pidin` 的线程阻塞态是 QNX 排查卡死的核心手段**：`REPLY-blocked` 表示 `MsgSend` 出去没等到 `MsgReply`（对端卡住或没起来）；`RECEIVE-blocked` 是正常等消息；`MUTEX` 表示在抢锁。

<EXTREMELY-IMPORTANT>
QNX 的 `MsgSend` 是**同步阻塞**的。对端不 `MsgReply` 就会一直卡在 SEND/REPLY-blocked，**反向拖住 diag 的发送线程**。看到 `REPLY-blocked` 要顺着找对端进程在干什么。
</EXTREMELY-IMPORTANT>

### 8. 配置/编译类（「关了开关还在」、「改了配置不生效」）

这类主要在 SDK 侧查，不用板子：

```bash
# 编译总开关
rg -n "SUPPORT_AX_DIAG" <SDK>/build/ | head -10

# 生成的配置
ls -la <SDK>/msp/component/diag/config/
find <SDK> -name "Fault_diagnosis_event_list.xlsx" -not -path "*/.repo/*"
```

看什么：改了 Excel 必须重跑 `make PLAT=<平台> fusa_config` 重新生成，否则不生效。编译期开关和运行时上报是两层，**关编译宏不等于运行时节点消失**。

## 日志在哪找

<EXTREMELY-IMPORTANT>
**QNX 的 diag 日志不走 slog2。** `include/diag_log.h:124-128` 的 `diag_printf()` 内部是 `printf()`/`vprintf()`，日志去了进程的标准输出（daemonize 后取决于重定向）。

**不要让客户用 `slog2info` 找诊断日志**——找不到会让客户误以为框架没跑。正确做法是看串口输出，或客户自己的日志重定向落点。

日志级别默认 7（info），调 `DIAG_LOG_LEVEL_VALUE` 可减少刷屏。
</EXTREMELY-IMPORTANT>
