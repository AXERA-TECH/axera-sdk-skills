# AX615 代码与取证地图

本文件沿用通用模板，用于把 AX615 的代码入口、运行时节点和证据关联集中记录。表中的历史版本和路径来自当前 Skill 已有资料；在分析具体设备时，仍需核对实际运行镜像、源码分支和构建产物，不能仅凭路径存在就断定修复已生效。

## 代码基线

| 项目 | 当前资料 | 核实方式 |
| --- | --- | --- |
| SoC/问题案例 | AX615 / 历史问题（编号已脱敏） | 设备信息、问题记录和现场日志 |
| 影响 SDK/BSP 版本 | `AX615_SDK_V2.0.0_P8` | 版本信息、发布记录、构建产物 |
| 已知修复版本 | `AX615_SDK_V3.3.0`、`AX615_SDK_V3.11.1` | 实际镜像版本与发布记录对照 |
| kernel 版本 | `linux-4.19.125`（案例资料中的目标路径） | `uname -a`、`/proc/version`、构建记录 |
| kernel commit | 未提供，不能判断 | Git commit、构建 manifest 或产物元数据 |
| Bootloader/固件版本 | 未提供，不能判断 | 启动日志、构建记录 |
| 目标板卡/硬件版本 | 未提供，不能判断 | 板卡丝印、BOM、测试记录 |
| 设备树精确节点与构建配置 | 未提供，不能判断 | 运行镜像、设备树 blob 与源码对照 |

## 模块定位

| 层级/模块 | 源码目录或文件 | 关键符号/节点 | 构建选项或配置 | 证据来源 |
| --- | --- | --- | --- | --- |
| kernel/driver：低功耗 GPIO | `linux-4.19.125/drivers/soc/axera/wakeup_source/gpio_lp.c` | `wakeup_gpio_lp_init()`、`wakeup_gpio_lp_handler()`、`axera_gpio_lp_remove()` | 低功耗 GPIO 与 IRQ 配置；精确设备树节点未提供 | `SKILL.md`、`diagnosis-flow.md` |
| kernel/driver：PM wakeup source | 同上及 Linux PM wakeup-source 实现 | `wakeup_source_register()`、`__pm_wakeup_event()`、`wakeup_source_unregister()` | `gpio_lp->ws` 应对应当前设备注册的 wakeup source | `diagnosis-flow.md` |
| 运行时：PM 唤醒计数 | `/sys/power/wakeup_count`、`/sys/power/state` | wakeup_count read/write 协议 | 具体用户空间休眠实现未提供 | `SKILL.md`、`diagnosis-flow.md` |
| 运行时：唤醒源与 IRQ 统计 | `/sys/kernel/debug/wakeup_sources`、`/proc/interrupts` | `wake_int`、gpio_lp IRQ 计数 | debugfs 挂载和字段因 BSP 可能不同 | `diagnosis-flow.md` |
| 运行时：timer32 | `/proc/ax_proc/power/wakeup_source/timer32/enable`、`time` | timer32 enable/time | 具体平台节点需现场确认 | `SKILL.md`、`diagnosis-flow.md` |
| 中间件/应用：休眠与取帧 | 应用休眠流程、VIN/AOV pipeline | `AX_SYS_Sleep`、`GetDevFrame` | 应用是否正确处理 wakeup_count 写回失败 | `SKILL.md`、`diagnosis-flow.md` |

## 现场取证清单

先确认节点存在性、权限和实际 BSP 差异；保留命令、时间戳和原始输出。以下命令以只读采集为主，不要求所有设备都支持：

```sh
uname -a
cat /proc/version
cat /proc/cmdline
cat /sys/power/state
cat /sys/power/wakeup_count
cat /sys/kernel/debug/wakeup_sources
cat /proc/interrupts
cat /proc/ax_proc/power/wakeup_source/timer32/enable
cat /proc/ax_proc/power/wakeup_source/timer32/time
dmesg -T
```

应用侧还应记录：

- GPIO pulse 的单调时钟时间戳、脉宽和间隔；
- `wakeup_count` 读取值、写回结果（字节数或 `errno`）及随后是否请求 suspend；
- `AX_SYS_Sleep` 返回值、`GetDevFrame` 返回值和业务状态；
- 与同一 suspend 周期对应的 `PM: suspend entry (deep)`、`PM: suspend exit`、`Freezing of tasks aborted` 等完整上下文。

如果节点不存在、debugfs 未挂载或命令失败，应记录具体错误和 BSP 配置，不要把“无节点”直接判为 GPIO 唤醒故障。寄存器写入、驱动卸载、刷写、断电和修改启动参数不属于通用取证清单，必须单独制定受控验证方案。

## 代码与日志关联

| 现象/日志关键字 | 对应代码路径和符号 | 触发条件 | 验证命令或实验 | 反证条件 |
| --- | --- | --- | --- | --- |
| 短时 GPIO 唤醒丢失；GPIO 私有等待队列有事件但 PM 判定不稳定 | `gpio_lp.c` 的 `wakeup_gpio_lp_handler()`；有效 `int_status` 分支 | IRQ 到达但没有同步 PM wakeup source | 对照 `/proc/interrupts`、`wakeup_sources`、完整 suspend 时间线；重复不同 pulse 间隔 | IRQ 状态未置位、GPIO 配置错误或不同 wakeup source 触发时，不能归因于该 handler |
| `wakeup_count` 写回失败 | Linux PM wakeup-count 路径；应用 read/write 协议 | 读取后到写回前发生新的 wakeup event | 记录原始计数、写回返回值、GPIO/timer/其他事件的相对时序 | 没有并发事件且写回仍失败时，应检查权限、节点和用户空间写法 |
| `PM: suspend entry (deep)` 后立即 `PM: suspend exit` | PM suspend 流程及所有启用的 wakeup source | GPIO、timer32 或其他事件触发中止/唤醒，或 suspend callback 失败 | 关联 `wakeup_sources`、IRQ、timer32 和后续 PM 日志 | 仅凭两行日志不能区分 GPIO、timer32、冻结失败和 callback 失败 |
| `Freezing of tasks aborted` | suspend 冻结阶段；不直接等同于 gpio_lp | 用户任务、内核线程或 worker 未冻结，或并发事件中止冻结 | 保留 abort 前后完整日志，检查未冻结任务和触发返回路径 | 若冻结成功后才发生 GPIO 唤醒异常，才继续检查 wakeup-source 路径 |
| `AX_SYS_Sleep ret=0x800b0715` | 平台 `AX_SYS_Sleep` 错误码定义及 kernel PM 日志 | API 返回失败，具体原因需由同周期证据解释 | 在对应 SDK 定义中解析错误码并关联 PM 日志 | 单独看到十六进制返回值不能推出 wakeup_count 根因 |
| `GetDevFrame ret=0x80110180` | VIN/ISP/帧队列与应用取帧路径 | 取帧超时或 pipeline 状态异常 | 同时核对 GPIO IRQ、PM resume、VIN/ISP 和帧队列证据 | 单独的取帧错误不能证明 suspend 或 GPIO wakeup_count 失败 |
| 修复后仍有资源问题 | `wakeup_source_register()`、probe 回滚、`axera_gpio_lp_remove()` | 重复 probe/remove 或异常退出路径 | 受控多轮 probe/remove（产品支持时），检查 wakeup source 是否重复或泄漏 | 不支持卸载/重新绑定时，不应据此设计无授权操作 |

## 证据等级与引用边界

- 可重复的修复前后或单变量 A/B 结果优先于单条日志和历史经验。
- 代码中存在 `__pm_wakeup_event()` 不等于当前运行镜像已包含该修复，必须核对 commit、构建记录或产物。
- 历史资料中的 pulse 延时、唤醒时延和修复版本是历史参照；不能直接当作当前板卡保证值。
- 如果代码、镜像、日志或硬件基线无法对齐，结论最多标为“高可信候选”或“待验证”。
