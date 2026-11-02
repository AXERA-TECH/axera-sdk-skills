# AX615 wakeup_count 与 gpio_lp 诊断参考

## 1. Linux wakeup_count 的作用

`/sys/power/wakeup_count` 用于避免“用户空间准备休眠”和“内核正式进入 suspend”之间的
唤醒事件竞态。

Linux 4.19 的核心流程是：

1. 读取 `wakeup_count` 时，内核通过 `pm_get_wakeup_count(&val, true)` 等待当前正在处理的
   wakeup event 结束，并返回累计事件计数；
2. 用户空间完成自身的休眠准备；
3. 用户空间把原值写回；
4. 内核调用 `pm_save_wakeup_count(val)`，只有期间没有新事件时才接受该值；
5. 写回成功后，用户空间才请求 suspend；
6. 写回之后若出现新的 wakeup event，suspend 过渡应被中止。

因此，“写回失败”通常是一个保护机制，表示读取后发生了新的唤醒事件。调用者必须检查
写入结果，不能忽略错误后继续请求 suspend。

## 2. 该历史案例的竞态关系

本案例中，`gpio_lp` 驱动已经创建了名为 `wake_int` 的 `wakeup_source`，但问题版本的 IRQ
handler 在处理 GPIO 中断时只完成了以下动作：

- 增加驱动私有等待队列状态；
- 唤醒等待队列；
- 清除 GPIO 中断状态。

如果没有调用 `__pm_wakeup_event(gpio_lp->ws, 0)`，Linux PM 核心无法通过该 wakeup source
及时观察到 GPIO 唤醒事件。事件可能被驱动私有逻辑看到，却未纳入 `wakeup_count` 的
原子判定，从而形成以下窗口：

```text
用户空间读取 wakeup_count
        |
        |  GPIO 低功耗中断到达
        |  gpio_lp handler 处理，但未通知 PM wakeup source
        v
用户空间回写旧 wakeup_count，内核仍可能接受
        |
        v
系统继续 suspend，短时 GPIO 唤醒表现为丢失或处理不完整
```

在有效 GPIO 中断分支中增加：

```c
__pm_wakeup_event(gpio_lp->ws, 0);
```

使 PM 核心更新 wakeup event 计数和状态，从而让 `wakeup_count` 协议能够检测到该竞态。

## 3. 源码核查点

目标文件通常为：

```text
kernel/linux/linux-4.19.125/drivers/soc/axera/wakeup_source/gpio_lp.c
```

### 3.1 初始化

确认 `wakeup_gpio_lp_init()` 或等价初始化函数中注册 wakeup source：

```c
gpio_lp->ws = wakeup_source_register("wake_int");
if (!gpio_lp->ws) {
        /* error handling */
}
```

### 3.2 IRQ handler

确认只有在对应 GPIO 的 `int_status` 有效时才上报 wakeup event：

```c
if (int_status) {
        __pm_wakeup_event(gpio_lp->ws, 0);
        atomic_inc(&lpgpio_wait[index].wq_status);
        wake_up_interruptible(&lpgpio_wait[index].wq);
        /* clear interrupt */
}
```

调用位置应位于中断状态确认之后。不要在没有真实中断状态时无条件上报，否则可能制造虚假
wakeup event 并阻止系统休眠。

### 3.3 生命周期

检查所有成功创建 wakeup source 之后可能退出的路径：

- probe 失败回滚；
- driver remove；
- 可选的模块卸载或设备重新绑定。

对应路径应执行：

```c
if (gpio_lp->ws) {
        wakeup_source_unregister(gpio_lp->ws);
        gpio_lp->ws = NULL;
}
```

如果现有代码风格不在 remove 中把指针置空，至少确保该路径只会执行一次且不会继续访问指针。

## 4. 日志采集建议

### 4.1 基础信息

```sh
uname -a
cat /proc/version
cat /sys/power/state
cat /sys/power/wakeup_count
```

### 4.2 唤醒源信息

系统支持时采集：

```sh
cat /sys/kernel/debug/wakeup_sources
cat /proc/interrupts
```

观察 `wake_int` 或对应 gpio_lp IRQ 的计数在 GPIO pulse 前后是否变化。不同 SDK 的 debugfs
挂载点或字段可能不同；命令失败时记录错误，不要假设节点一定存在。

### 4.3 timer32 配置

历史资料附件中的测试程序使用：

```sh
cat /proc/ax_proc/power/wakeup_source/timer32/enable
cat /proc/ax_proc/power/wakeup_source/timer32/time
```

测试程序会启用 timer32，并设置例如 1000 ms 的超时。timer32 同时也是唤醒源，分析 GPIO
唤醒时必须区分究竟是 GPIO 先唤醒，还是 timer32 到期后才恢复系统。

### 4.4 PM 日志

```sh
dmesg -w
```

需要关联以下事件顺序：

```text
应用读取 wakeup_count
应用写回 wakeup_count
应用请求 AX_SYS_Sleep/写入 power state
PM: suspend entry (deep)
GPIO pulse
GPIO IRQ handler
PM: suspend exit
应用收到 GPIO 事件或取帧结果
```

如果日志没有统一时间基准，在应用日志中使用单调时钟时间戳，不要仅依赖普通 printf 顺序。

## 5. 复现实验设计

### 实验 A：不使用应用层 wakeup_count

目的：确认问题版本中短时 GPIO 唤醒的丢失比例。

变量：

- GPIO pulse 延时：1 ms、8 ms、15 ms、50 ms、500 ms；
- 每档重复多次；
- timer32 设置为足够长的兜底时间，避免把 timer32 唤醒误认为 GPIO 唤醒。

记录：

- GPIO IRQ 计数；
- wakeup source event count；
- suspend entry/exit 时间；
- 应用事件接收结果。

### 实验 B：使用正确的 wakeup_count 协议

目的：确认 GPIO 事件出现在 read/write 窗口时，写回会失败或后续 suspend 被中止，而不是
静默丢事件。

必须记录：

- read 的文本值；
- write 的字节数或 errno；
- write 失败后是否停止请求 suspend；
- 事件到达相对于 read/write 的时序。

### 实验 C：应用驱动补丁后重复 A/B

目的：验证可靠性修复，同时量化延迟回归。

历史资料中的观察值为：

- 去掉应用层 wakecount，第 15 ms 唤醒，不丢中断，唤醒时间约 46 ms；
- 保留应用层 wakecount，第 7 ms 唤醒，不丢中断，唤醒时间约 50 ms。

这些值只作为历史参照。当前平台应重新测量平均值、最大值和异常值，并明确 GPIO pulse 到
应用可见事件之间的计时边界。

## 6. 日志判读

### `PM: suspend entry (deep)` 后很快 `PM: suspend exit`

可能原因包括：

- GPIO 事件被正确识别，主动中止或唤醒 suspend；
- timer32 或其他唤醒源触发；
- 驱动 suspend callback 失败；
- freeze 阶段失败。

需要结合后续日志，不可仅凭这两行得出结论。

### `Freezing of tasks aborted ...`

说明 suspend 没有通过任务冻结阶段。日志列出的许多 `not frozen` 任务可能只是中止后打印的
系统状态，不能逐个认定为根因。先找触发 abort 的返回路径和并发 wakeup event，再判断是否
有真正无法冻结的任务。

### `AX_SYS_Sleep ret=0x800b0715`

这是平台 API 返回值，不能仅凭十六进制值推断具体根因。应在对应 SDK 的错误码定义中解析，
并与同一周期的 kernel PM 日志关联。若 kernel 日志明确显示 freeze aborted，则先处理该阶段。

### `GetDevFrame ret=0x80110180`

该结果与 VIN/ISP/帧等待相关，不能单独证明 suspend 或 GPIO wakeup_count 失败。只有同时缺少
GPIO IRQ、PM wakeup event 和正常 resume 证据时，才把它作为本案例的辅助现象。

## 7. 修复评审清单

- [ ] 引入了声明 `__pm_wakeup_event()` 所需的 PM wakeup 头文件；
- [ ] 仅在确认有效 GPIO LP 中断后调用 `__pm_wakeup_event()`；
- [ ] 使用的是当前设备注册的 `gpio_lp->ws`；
- [ ] IRQ 中没有进行可能休眠的操作；
- [ ] probe 错误回滚会注销 wakeup source；
- [ ] remove 路径会注销 wakeup source；
- [ ] 不会重复注销或释放后继续访问；
- [ ] 使用和不使用应用层 wakeup_count 的路径均完成回归；
- [ ] 测量并报告唤醒延迟；
- [ ] 区分 GPIO 与 timer32 等其他唤醒源。
