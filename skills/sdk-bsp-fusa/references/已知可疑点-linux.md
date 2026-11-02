# 已知可疑点

**S5 用，判「疑似新缺陷」前先比对这里。**

下面的条目都是在当前 SDK（`m57h_trunk`，`SDK_VERSION=V2.10.0`）上**逐条实证过**的代码事实，且 **FAQ 和 SDK 的 `diagcore.md`/`ecm.md`/`fcu.md` 三份文档都未记录**。

<EXTREMELY-IMPORTANT>
**怎么用这些条目**：

客户现象命中某条时，可以给出「代码事实 + 推理链 + 取证方法」，但**必须同时说明**：

> 这是当前 SDK 的静态代码事实，我按代码逻辑推断它会导致你看到的现象。但**缺陷性质（是否为已知问题、是否已在其它分支修复、是否有设计上的考虑）需要原厂确认**。

不要自行断定这些是 bug 并让客户改代码。它们的价值在于：① 快速解释现象；② 给交接文档提供高质量的代码推理链，省掉原厂一轮往返。

命中后仍应进 S6 产出交接文档——除非只是配置层面能规避。
</EXTREMELY-IMPORTANT>

## ① 用户态属性名写错，配置静默失效

**代码事实**：`msp/component/diag/src/core/netlink_monitor.cpp:103`

```cpp
std::string resumeHappenMaxsndFile = filePath + "resume_happen_max_snd_ms";
```

kernel 侧实际属性名是 `happen_max_snd_ms`（`diag_sysfs.c:242`），**不存在** `resume_happen_max_snd_ms`。

**推理链**：属性文件不存在 → `fopen()` 失败 → 代码静默跳过（不报错、不返回失败）→ 服务认为配置下发成功 → 该项实际保持 kernel 默认值。

**客户现象**：改了 JSON/Excel 里的 happen 最大上报间隔，服务启动无报错，但行为没变。

**取证**：

```bash
cat /sys/devices/platform/axdiag/domain0/module<M>/error<E>/happen_max_snd_ms
```

读回值 ≠ 期望值即命中。

**规避**：直接写 sysfs 即可生效（配置层面可解，不必等原厂）：

```bash
echo <期望值> > /sys/devices/platform/axdiag/domain0/module<M>/error<E>/happen_max_snd_ms
```

对应 FAQ-5、FAQ-7、FAQ-27。

## ② Buildroot 版 diag_tools 漏开注入总开关

**代码事实**：SDK 里有两份 `diag_tools` 脚本，行为不同。

| 脚本 | `inject_enable` |
|---|---|
| `build/scripts/init_scripts/diag_tools` | 有，:125 `echo 1 > /sys/class/fusa/diag/diag/inject_enable` |
| `rootfs/buildroot-2024.02.2/package/diag_tools/diag_tools.sh` | **完全没有**（`grep -c` 结果为 0） |

同一脚本还在 domain 目录下读 `boot_error`，而 kernel 在 domain 级导出的是 `d_boot_error`（`diag_core.c:340`）。

**推理链**：`should_fail_diag_injection()` 第一件事就是检查 `dc->inject_enable`，为 false 直接返回不注入（`diag_fault_inject.c:70`）。Buildroot 版脚本不开这个开关 → 注入请求全部被门控挡掉 → 但脚本本身执行成功，回显正常。

**客户现象**：`diag_tools -i` 回显正常，但 `number` 不增长、没有故障上报。这是「注入无效」的头号原因。

**取证**：

```bash
grep -c inject_enable "$(command -v diag_tools)"   # 0 = 残缺版
cat /sys/class/fusa/diag/diag/inject_enable        # 0 = 确认未开
```

**规避**（配置层面可解）：

```bash
echo 1 > /sys/class/fusa/diag/diag/inject_enable
# 然后重试注入，看 number 是否变化
```

## ③ ECM STL 初始化失败不中断 probe

**代码事实**：`drivers/soc/axera/ecm/ecm.c:375-378`

```c
ret = axera_ecm_stl_init(drvdata);
if (ret != 0) {
    dev_err(&pdev->dev, "Fail to stl init\n");
}          // ← 没有 return ret
```

**推理链**：STL 初始化失败后 probe 继续走完 → ECM 本体注册成功（中断能收、通道 sysfs 齐全、`happed_num` 正常增长），但 `diagnosis_register()` 没做成 → `axdiag/domain0/module<17..26>/` 缺失 → 故障不进诊断框架、不上报用户态和 SafetyIsland。

**客户现象**：「ECM 通道计数在涨，但 diag 里查不到 ECM 模块」「ECM 检测到错误但应用收不到」。

**取证**：

```bash
dmesg | grep "Fail to stl init"
ls /sys/devices/platform/axdiag/domain0/ | grep -E 'module1[789]|module2[0-6]'
```

前者有输出 + 后者缺失 = 命中。

**注意**：这条的现象容易被误判成「ECM 硬件没问题所以不用管」，实际是上报链路断了——安全相关，要认真对待。

## ④ ECM STL 基址 switch 无 default，可导致数组越界

**代码事实**：`drivers/soc/axera/ecm/ecm_stl.c:96-130`

```c
switch(axera->paddr) {
    case 0x8014000:  axera->stl_module_id = DIAG_MID_ECM_CPU;   break;
    ... 共 10 个 case ...
    case 0x1010c000: axera->stl_module_id = DIAG_MID_ECM2_ISP;  break;
}          // ← 没有 default 分支
ecm_diag_info.name = name_buf[axera->stl_module_id - (u8)DIAG_MID_ECM_TOP];  // :129
ecm_diag_info.handle[...].name = fun_check_name_buf[axera->stl_module_id - (u8)DIAG_MID_ECM_TOP];  // :130
```

**推理链**：`switch` 未命中 → `stl_module_id` 保持 `devm_kzalloc` 清零后的 **0** → `0 - DIAG_MID_ECM_TOP` = `0 - 17` = **-17** → `name_buf[-17]` 越界读，`:130` 同理。

**触发条件**：DT 里的 ECM 基址不在这 10 个硬编码值里——新增 ECM 实例、FPGA/HAPS 环境不同的地址映射、或客户改了 DT。

**客户现象**：ECM probe 阶段 oops / KASAN 报错，或 `domain0/module*/name` 出现乱码。

**取证**：

```bash
dmesg | grep -iE "oops|KASAN|BUG:" | head
for d in /sys/devices/platform/axdiag/domain0/module*/; do cat $d/name; done   # 看有无乱码
```

同时核对客户板级 DT 里 ECM 节点的 `reg` 是否在上面 10 个值之内。

**这条在标准板型上不会触发**（10 个 case 覆盖了标准配置），只在改过 DT 或非标环境才可能命中。

## ⑤ FCU 请求无限等待，SafetyIsland 不回包会挂死

**代码事实**：`drivers/soc/axera/fcu/fcu_virt.c:317`

```c
if (wait_for_completion_timeout(&fault->complete, MAX_SCHEDULE_TIMEOUT) == 0UL) {
```

`MAX_SCHEDULE_TIMEOUT` 是 Linux 里表示「无限等待」的值，用它做 `wait_for_completion_timeout` 的超时参数等于没有超时。

**推理链**：Linux FCU 是 `axera,fcu_virt`（纯转发，无 `reg`），所有请求经 RPMsg 送给 SafetyIsland 执行 → SafetyIsland 未建链/未回包 → 调用者永久阻塞。

**客户现象**：`cat /sys/class/fusa/fcu/*/fsm` 或任何 FCU 属性读取卡住不返回，终端像死了；进程处于 D 状态无法 kill。

**取证**（已有卡住的读取时，不再发起同步请求）：

```bash
ps -eo pid,stat,wchan:32,args
grep -c FCU /proc/interrupts
dmesg | grep -iE "rpmsg|handshake" | tail -20
```

`wait_for_completion_timeout` 的等待不可中断，`timeout` 或强杀不能保证解除 D 状态。无响应只说明请求未完成，不能直接认定未建链。先取现有任务栈和通信证据，确认恢复后再串行读取；参见 `取证命令-linux.md` 的 FCU 分支。

SDK 的 `fcu.md` 提到了「不回包时当前会无限等待」，所以这条**部分有文档记录**——但没说清后果是取证命令会挂死。

## ⑥ fusa/Makefile 里 selftest 目标变量名疑似写错

**代码事实**：`drivers/soc/axera/fusa/Makefile:10`

```make
diag-core-objs = diag_core.o diag_netlink.o diag_stl.o
diag-core-objs += diag_sysfs.o diag_extend.o diag_sys_common.o
...
diag-core-$(CONFIG_DIAG_CORE_SELFTEST) += diag_selftest.o
```

前面几行都用 `diag-core-objs`，最后一行是 `diag-core-`（少了 `objs`）。kbuild 识别的是 `<module>-objs` 或 `<module>-y`，`diag-core-y` 也有效，但 `diag-core-$(CONFIG_...)` 展开成 `diag-core-y` 时才碰巧有效——**`CONFIG_DIAG_CORE_SELFTEST` 是 bool，开启时展开为 `diag-core-y`，这实际上是有效的 kbuild 写法**。

**所以这条大概率不是缺陷**，只是与前面几行风格不一致。列在这里是为了避免误判：如果客户报「selftest 功能不工作」，**不要**从这行入手，`diag-core-y` 与 `diag-core-objs` 会被 kbuild 合并。

真要确认编入情况：

```bash
nm diag-core.ko 2>/dev/null | grep -i selftest
# 或板端
ls /sys/devices/platform/axdiag/domain0/selftest
```

## 两条属于「设计预期」，别当缺陷查

这两条容易被客户当成故障，实际是设计行为，要主动解释清楚：

**① dmesg 刷屏是预期的。** `diag_netlink.c:65` 的 `pr_info` 无速率限制，用户态服务未建链时会 loop 重发。处置方式是起 `ax_diag_service`，或调 `/proc/sys/kernel/printk` 降日志级别——**不是改代码**。

**② 开机后某 ECM 通道 `inject_num == 1`、`happed_num == 1` 是预期。** `axera_ecm_boot_check()` 启动时会对某通道真实注入一次做自检。这是开机自检的痕迹，不是残留故障。

## 另有一条注释与代码不符

`diag_stl.c:152` 的注释说「When the timeout count is 5, the actual timeout is 4 rounds」，代码是 `if (heartbeat_time > 5)`——即第 6 次才报。

**不是功能缺陷**，但解释心跳机制时**以代码为准**，别照抄注释，否则算出的上报延迟会差一轮（约 20ms）。
