# 取证命令 · Linux

**S4 用。先读 `取证框架.md`（使用原则、症状分支、回填用法），本文只给 Linux 命令体。**

属性含义与三类路径见 `运行时接口-linux.md`。

## 路径确认（第一条必给）

<EXTREMELY-IMPORTANT>
**Linux 节点是数字命名**（`domain0/module45/error29`，不是模块名），且哪些模块存在取决于 Kconfig 与 DT。先让客户列出实际节点。
</EXTREMELY-IMPORTANT>

<EXTREMELY-IMPORTANT>
**这条命令兼作平台校验。** 若 S1 的平台判定是客户自报的（而非硬判据命中），这里就是验证点：

- `/sys/devices/platform/axdiag` 存在 → 确认是 Linux，继续
- 该路径不存在，改跑 `ls /proc/ax_diag/` 却有内容 → **客户自报错了，实际是 QNX**

发现不符时**立即停下改判**，切换到 `取证命令-qnx.md`，并把已给出的结论重新走一遍。不要继续用 Linux 命令。
</EXTREMELY-IMPORTANT>

```bash
# ① 框架是否在位（三条路径缺哪条说明哪块没编进去）
ls -d /sys/class/fusa /sys/devices/platform/axdiag /sys/kernel/debug/diag_fault_inject 2>&1

# ② 有哪些模块（数字目录 → 名字的对照）
for d in /sys/devices/platform/axdiag/domain0/module*/; do
  printf "%s = %s\n" "$(basename $d)" "$(cat $d/name 2>/dev/null)"
done
```

看什么：

| 缺失项 | 说明 |
|---|---|
| `/sys/class/fusa` | `CONFIG_AXERA_FUSA_SUPPORT` 未开，或 fusa 模块未加载 |
| `/sys/devices/platform/axdiag` | `CONFIG_AXERA_DIAG_CORE` 未开 |
| `/sys/kernel/debug/diag_fault_inject` | `CONFIG_DIAG_FAULT_INJECT` 未开，或 debugfs 未挂载 |

第二条的输出是后续一切的基线——拼路径前必须先有它。

**注意**：`axdiag` 是 `fusa_sys.c:49` 用 `platform_device_alloc("axdiag", -1)` **动态创建**的，走 name 匹配。所以 **DTS 里没有 `axera,diag-core` 节点是正常的**，不能据此判断 diagcore 未使能。实测 `m57.dtsi` 里确实没有该节点。

## A 必做项（所有症状通用）

```bash
# ③ 两级 cycle_enable（domain 级为 0 是最高频的根因）
cat /sys/devices/platform/axdiag/domain0/cycle_enable
cat /sys/devices/platform/axdiag/domain0/d_boot_error

# ④ 诊断服务是否在跑
ps aux | grep -c "[a]x_diag_service"

# ⑤ CPU 负载（大量结论以负载正常为前提）
top -bn1 | head -15

# ⑥ 关键日志（一次抓全，避免多轮往返）
dmesg | grep -iE 'diag-netlink|heartbeat|Diagnonsis|handle overdue|handle_config|Fail to stl init|fcu|ecm' | tail -40
```

看什么：

<EXTREMELY-IMPORTANT>
**`domain0/cycle_enable` 为 0 是 Linux 侧最高频的根因。**

两级开关的初值不同：module 级初值 **1**（`diag_sys_common.c:196`），domain 级初值 **0**（`diag_core.c:1332`）。domain 级要等 `ax_diag_service` 配置成功后才写 1（`msp/component/diag/src/core/diag_core.cpp:444`）。

所以 ③ 为 0 且 ④ 为 0 时，根因就是**服务没起来**，不是驱动坏了。
</EXTREMELY-IMPORTANT>

- `d_boot_error` 的 `d_` 前缀不能少（domain 级），module 级才是 `boot_error`（无前缀）。
- CPU 持续高负载时，`handle overdue`、heartbeat、`FCU_HANDLER_TIMEOUT` 类现象基本可归因到负载。

## B 按症状分支

### 1. 心跳类（`heartbeat` 关键词）

```bash
# module0 = DFC, error17 = DIAG_SERVER_HEARTBEAT
P=/sys/devices/platform/axdiag/domain0/module0/error17
for f in name number continu_cnt debounce_cnt pending status; do
  printf "%-14s = %s\n" "$f" "$(cat $P/$f 2>&1)"
done

# 区分两种日志
dmesg | grep -c "heartbeat time:"
dmesg | grep -c "heartbeat timeout"
```

看什么：**`number` 是判据。**

| `number` | `heartbeat time:` | 结论 |
|---|---|---|
| 0 | 有，在刷 | **去抖过程，没有真正上报故障** → 设计预期 |
| > 0 | 有 | 真的报了，继续查为什么心跳丢 |

`heartbeat timeout` 的计数才对应真实上报次数。这两个日志只差一个词，结论完全相反。

代码依据：单轮阈值 `SERVER_HEARTBEAT_TIMEOUT = 5`ms（`diag_core.h:32`），`diag_stl.c:151` 打 INFO，`:153` `if (heartbeat_time > 5)` 才 `:154` 报 ERR。

**注意**：`diag_stl.c:152` 的注释与代码不符——注释说「timeout count is 5 时实际是 4 轮」，代码是 `> 5` 即第 6 次才报。**以代码为准**，照抄注释会把上报延迟算差一轮。

### 2. 周期自检类（`cyclework`、`cycle` 关键词）

```bash
# 两级开关
cat /sys/devices/platform/axdiag/domain0/cycle_enable            # 初值 0
cat /sys/devices/platform/axdiag/domain0/module<M>/cycle_enable  # 初值 1
cat /sys/devices/platform/axdiag/domain0/module<M>/cycle_ms
cat /sys/devices/platform/axdiag/domain0/module<M>/boot_error
```

看什么：**两级都要为 1 周期自检才跑**。domain 级为 0 → 查 `ax_diag_service`。

`cycle_ms` 读回值与写入值不完全一致是**正常的**——`HZ=250` 时 jiffy 粒度 4ms，必然量化。别当 bug 查。

需要手动兜底开启时（客户同意后）：

```bash
echo 1 > /sys/devices/platform/axdiag/domain0/cycle_enable
```

### 3. 注入类（客户说「注入没生效」）—— 四条件顺序检查

> 四个条件按顺序查，前面不满足查后面没意义。

```bash
# ① 注入总开关（头号原因）
cat /sys/class/fusa/diag/diag/inject_enable

# ② diag_tools 是哪一版（0 = Buildroot 残缺版，漏开总开关）
grep -c inject_enable "$(command -v diag_tools 2>/dev/null)" 2>/dev/null

# ③ 该错误是否可注入
cat /sys/devices/platform/axdiag/domain0/module<M>/error<E>/injectable

# ④ 注入前后对比 number
cat /sys/devices/platform/axdiag/domain0/module<M>/error<E>/number
#   ...执行注入...
cat /sys/devices/platform/axdiag/domain0/module<M>/error<E>/number
```

看什么：

- ① 必须为 **1**。`should_fail_diag_injection()` 第一件事就是检查它（`diag_fault_inject.c:70`），为 false 直接返回不注入。
- ② 为 **0** 就是根因——Buildroot 版 `diag_tools.sh` 完全没有 `inject_enable`，所以 `diag_tools -i` **回显正常但实际不注入**。这是「注入无效」的头号原因。手动 `echo 1 > /sys/class/fusa/diag/diag/inject_enable` 后重试即可验证。
- ④ **看 `number` 是否变化**，不要看工具回显。
- 四条都对还不上报 → 查两级 `cycle_enable` 和 debounce 配置。

注入还需 `CONFIG_DIAG_FAULT_INJECT=y`（依赖 `DEBUG_KERNEL`）。

### 4. 配置不生效类（改了 Excel/JSON 没反应）

<EXTREMELY-IMPORTANT>
**唯一可信的验证点是板端 sysfs 实际值。** 服务返回成功、JSON 内容正确都不算。
</EXTREMELY-IMPORTANT>

```bash
# 回读实际生效值
P=/sys/devices/platform/axdiag/domain0/module<M>/error<E>
for f in enable prio threshold happen_debounce_times resume_debounce_times \
         happen_max_snd_ms happen_min_snd_ms resume_max_snd_ms resume_min_snd_ms; do
  printf "%-24s = %s\n" "$f" "$(cat $P/$f 2>&1)"
done
```

看什么：与客户期望的配置值逐项比对。

**已实证的坑**：用户态下发 `happen_max_snd_ms` 时用的属性名是 `resume_happen_max_snd_ms`（`netlink_monitor.cpp:103`），kernel 没有这个属性，`fopen()` 失败后静默跳过。所以这一项**很可能就是没生效**，且服务不报错。

命中时告知客户「这是当前 SDK 的静态代码事实，缺陷性质需原厂确认」，并给出规避：直接写 sysfs 即可生效。

SDK 侧配合查（不用板子）：

```bash
ls -la <SDK>/msp/component/diag/config/*.json
find <SDK> -name "Fault_diagnosis_event_list.xlsx" -not -path "*/.repo/*"
```

四层链路任一段断了都会表现为「不生效」：Excel → 生成物 → rootfs JSON → 板端 sysfs。**从下往上倒推最快。**

### 5. ECM 类（module 17~26 或 `ECM_*` 符号名）

```bash
# STL 是否初始化成功（失败不会让 probe 失败，静默）
dmesg | grep "Fail to stl init"
ls /sys/devices/platform/axdiag/domain0/ | grep -E 'module1[789]|module2[0-6]'

# ECM 设备级与通道级
cat /sys/class/fusa/ecm/*/ecm_num /sys/class/fusa/ecm/*/fault_a_num 2>&1
for d in /sys/class/fusa/ecm/*/fault*/; do
  printf "%s index=%s happed=%s inject=%s\n" "$(basename $d)" \
    "$(cat $d/index 2>&1)" "$(cat $d/happed_num 2>&1)" "$(cat $d/inject_num 2>&1)"
done

# 三方对账
grep -iE "ecm" /proc/interrupts
```

看什么：

- `Fail to stl init` **有输出 + ECM 模块目录缺失** = 已定性。现象是「ECM 通道有计数但 diag 里查不到 ECM 模块」，说明**上报链路断了**——安全相关，要认真对待。
- **三方对账**：`/proc/interrupts` 计数、通道 `happed_num`、diag 侧 `number`。不一致能定位到断在哪一段。
- **开机后某通道 `inject_num == 1`、`happed_num == 1` 是 boot check 自检痕迹，是预期**，别当残留故障查。

### 6. FCU 类（`FCU_SAFETY`、`FCU_HANDLER_TIMEOUT`）

<EXTREMELY-IMPORTANT>
**FCU 同步读取可能无限等待。** `fcu_virt.c:317` 使用不可中断的 `wait_for_completion_timeout(..., MAX_SCHEDULE_TIMEOUT)`，`timeout` 或强杀不能保证解除 D 状态。已有读取卡住或 RPMsg 状态不明时，停止新增同步读取，先收集下面的证据。
</EXTREMELY-IMPORTANT>

```bash
# 已有任务状态，找出阻塞读取的 PID
ps -eo pid,stat,wchan:32,args

# 用实际 PID 替换 <PID>，读取已有任务栈，不发起 FCU 请求
cat "/proc/<PID>/stack"

# 只列节点信息，先确认实际设备路径
ls -ld /sys/class/fusa/fcu/*

# 中断是否注册
grep -c FCU /proc/interrupts

# 建链相关日志
dmesg | grep -iE "rpmsg|handshake" | tail -20
```

看什么：

- 读取无响应只能说明请求未完成；未建链、发送失败或对端未回复都需核实。`ax_diag_service` 的 Netlink handshake 不能证明 FCU RPMsg 建链。先核对现有任务栈和通信日志，按已确认流程恢复通信，再串行读取实际设备下的 `fsm` 等同步属性；已有阻塞任务未恢复时不重试。
- `/proc/interrupts` 里找不到 `FCU` = 中断没注册，查板级 DTS 有没有 `&fusa { status = "okay"; }`。
- `FCU_HANDLER_TIMEOUT` 偶发是处理耗时抖动，**持续大量出现**才查链路。而且它常是更早原始故障的连锁结果，**先看时间线**。
- `mask` 只停止该来源的报告，**不会清除底层信号**。客户以为 mask 了就没事了，实际底层 fault 还在。

### 7. 压测/稳定性、Call trace、RCU stall —— head 不用 tail

```bash
# 首个异常（最重要——不是最后一条）
dmesg | grep -nE "Call trace|Oops|BUG:|WARN|RCU|KASAN" | head -10

# 内存
free -m
cat /proc/meminfo | grep -E "MemFree|MemAvailable"

# 错误风暴证据：上报量排序
for d in /sys/devices/platform/axdiag/domain0/module*/error*/; do
  n=$(cat $d/number 2>/dev/null); [ "${n:-0}" -gt 0 ] && echo "$d number=$n"
done | sort -t= -k2 -rn | head -10
```

看什么：

<EXTREMELY-IMPORTANT>
**用 `head -10` 而不是 `tail`。** 要找时间线上**最早**的异常，不是最后一条。

Linux FuSa 的 heartbeat、`handle overdue`、`FCU_HANDLER_TIMEOUT` 大多是首个原始故障的下游症状。按最后一条复位原因归因几乎必错。
</EXTREMELY-IMPORTANT>

最后一条命令找出上报量最大的错误码——**错误风暴**会占满 512 节点 mempool（`diag_core.h:34` `DIAG_DCE_MEMPOOL_MIN 512`），导致节点释放不及、timeout list 堆积、RCU stall。找到风暴源头才是根因。

错误节点生命周期：report 完成 `report_flag += 1`、ACK 收到 `report_flag += 2`，**仅 `0x3` 可释放**。ACK 收不到就会积压。

`handle overdue` 阈值是 20ms（`diag_core.c:1111`），**是症状不是根因**。

### 8. 编译/开关类（「关了开关还在」、「改了配置不生效」）

```bash
# 板端（内核开了 IKCONFIG 才有）
zcat /proc/config.gz 2>/dev/null | grep -E "AXERA_(FUSA|DIAG|ECM|FCU)|DIAG_FAULT_INJECT"

# 模块加载情况（没有 config.gz 时的替代）
lsmod | grep -iE "diag|ecm|fcu"
```

SDK 侧：

```bash
grep -E "AXERA_(FUSA|DIAG|ECM|FCU)|DIAG_FAULT_INJECT" \
  <SDK>/kernel/linux/linux-6.1.83/.config
```

<EXTREMELY-IMPORTANT>
**查 `.config`，不要查 defconfig。**

很多符号靠 `select` 间接带出——`CONFIG_AXERA_ECM` 通常不写在 defconfig 里，是被 `CONFIG_AXERA_ECM_FAULT=m` select 出来的。同理 `AXERA_FCU_SYSFS` select `AXERA_FCU` select `AXERA_FUSA_SUPPORT`。

**搜 defconfig 得出「没开」是错的结论。**
</EXTREMELY-IMPORTANT>

板端没有 `/proc/config.gz` 时，退而看模块是否加载和 sysfs 节点是否存在。
