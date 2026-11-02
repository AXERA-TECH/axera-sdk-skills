# AX615 Linux SD 卡症状矩阵

本表只提供当前 Linux 代码可核对的通用诊断方向，不替代目标板的日志、DTB、kernel config、模块和 A/B 对照。症状相同但芯片型号、板型、版本、card detect 方式或首个异常不同，结论等级必须降低。

| 症状/首个异常 | 可先确认的层级 | 需要的证据 | 当前不能推出 | 最小下一步 |
|---|---|---|---|---|
| 无 `/dev/mmcblk*`，也无 `axera sdhci probe` | driver/module 或 DTB 匹配前 | 实际 config、kernel 版本、DTB、模块包、完整 dmesg | 卡一定损坏或供电一定异常 | 先查 `CONFIG_MMC_SDHCI_AXERA` 是 `=y`/`=m`/未启用 |
| 驱动为 `=m` 但 `lsmod` 无 `sdhci_axera` | module 未加载候选 | `.ko` 是否存在、依赖、kernel version、`modprobe`/`insmod` 错误 | 源码中没有驱动 | 核对 `/lib/modules/$(uname -r)`，优先用 `modprobe sdhci-axera` 保存输出 |
| `modprobe: module ... not found` | module 查找失败 | 目标模块包、`uname -r`、module dependency database、实际 config | 卡、供电或控制器故障 | 区分 built-in 与 module，核对 `.ko` 是否随 rootfs 发布 |
| `CONFIG_MMC_SDHCI_AXERA=y` 但无 probe | built-in 驱动未匹配或日志缺失候选 | 实际 kernel、目标 DTB `compatible/status/reg`、日志级别 | 需要 `insmod` | 核对加载的 DTB 和 platform device，抓完整启动 dmesg |
| probe 日志中断在 `check 1~6` | AXERA host probe 某区间 | 完整 check 顺序、返回值、目标 DTB、资源和 IRQ | 具体硬件损坏 | 按停止位置核对相邻调用，不跨层下硬件结论 |
| `broken-cd` 下插卡无立即日志 | polling card detect | 目标 DTB、host 是否注册、轮询期间日志、卡在位状态 | polling 一定失效 | 等待完整 polling 周期并抓持续 dmesg，确认 host 已 probe |
| `cd-gpios` 下始终检测不到卡 | GPIO detect | GPIO 编号、pinmux、`cd-inverted`、debounce、插拔电平和中断 | 卡一定损坏 | 实测插拔前后 CD 电平，只改变极性配置做受控验证 |
| `cd-gpios` 下始终显示有卡 | GPIO 极性或电平候选 | `cd-inverted`、GPIO idle/active 电平、pinmux、硬件连线 | MMC core 枚举已成功 | 对照插拔电平和 detect 日志，确认极性后再看 CMD 响应 |
| `Failed to get sd pwr_en_gpio from dts` | DTS 电源 GPIO 获取 | 编译后 DTB、板型、芯片型号分支、`pwr_en_gpioD/Q` | 卡或控制器已损坏 | 反编译目标 DTB并核对电源 GPIO 与板级连线 |
| `no sd_pwr_sw_gpio, cannot switch to 1.8V` | 1.8 V voltage switch | 目标 DTS、芯片型号、UHS 属性和 capability | 外部 regulator 损坏 | 先确认设计是否支持 UHS；AX615D 核对 3.3 V-only 分支 |
| 上电后仍没有 CMD 响应 | power/pin/enumeration 候选 | SD 供电、电源 GPIO、上电延时、CLK/CMD/DAT、pinmux 和上拉 | 单独由卡或供电引起 | 先确认电压、CLK 和 CMD/DAT 上拉，再做已知正常卡对照 |
| 管脚悬空或上拉异常 | pin/pull 硬件候选 | 原理图、实测静态电平、pinmux；驱动动态上下拉代码状态 | 软件驱动一定会补偿 | 确认 VDD 硬件上拉和 pinmux，不盲目同时改多个寄存器 |
| `phy lock failed` | Cadence PHY DLL lock | PHY delay、时钟、供电、芯片型号、成功/失败模式 | delay 数值错误或 PCB 信号问题已确认 | 保持镜像和卡不变，做默认/已知配置对照并采集时钟证据 |
| `no tuning point found` | tuning 采样窗口 | 目标模式/频率、电压、卡、tuning 命令和完整 MMC 日志 | 卡物理损坏 | 对照低速或非 UHS 模式，观察是否能稳定枚举和读写 |
| tuning 回退后低速稳定 | 高速 timing/电压候选 | 回退日志、低速稳定性、错误复现率 | 具体 PHY delay 或走线问题 | 只改变频率/模式做 A/B，不直接盲改多个 delay |
| AX615D 无 UHS/1.8 V | 当前芯片能力限制候选 | 精确芯片型号、3.3 V-only 日志、驱动版本 | 所有 AX615 变体都相同 | 确认目标确为 AX615D 且实际驱动包含该限制 |
| 有 `mmcblk` 但 mount 失败 | partition/filesystem | 分区表、`blkid`、文件系统模块、mount 参数、dmesg | SDHCI 必然异常 | 只读确认分区和 FAT/VFAT/exFAT 支持，先不要格式化 |
| `mount` 显示 `(ro)` | 当前文件系统只读挂载 | mount 参数、`/sys/block/mmcblk*/ro`、FAT/exFAT 日志、写保护 | 卡坏、DTS 或文件系统中的具体一种 | 先区分显式 `-o ro`、块设备只读和文件系统降级 |
| `not properly unmounted` | 文件系统未正常卸载记录 | 是否直接拔卡/异常断电、首次 I/O error、挂载历史 | SDHCI 控制器故障 | 要求后续严格 `sync` + `umount`，用正常拔卡做 A/B |
| `Filesystem has been set read-only` | 文件系统进入只读保护 | 更早的 FAT/exFAT/I/O 日志、块设备 `ro`、拔卡历史 | 单凭该行确认卡损坏 | 找首个文件系统或 block I/O 异常，再决定离线检查 |
| `umount: device is busy` | 挂载点仍被占用 | `fuser -vm`/`lsof`、当前目录、后台服务 | 已安全卸载 | 停止占用进程，重新 `umount` 成功后再拔卡 |
| 未 `umount` 直接拔卡后损坏/readonly | userspace-hotplug 与 filesystem 高可信方向 | `card removed` 与 I/O error 时间顺序、拔卡操作、下次挂载日志 | 卡或 SDHCI 硬件必然损坏 | 以后固定执行 `sync`、`umount`、确认未挂载，再拔卡 |
| `card removed` 后出现 I/O error | 热拔卡后传输中断 | 时间顺序、detect 方式、当时是否仍挂载/写入 | 正常使用期信号问题 | 先确认是否人为拔卡；若非拔卡，再转 block I/O 分析 |
| 正常插卡期间 CRC/timeout/ADMA | block I/O 传输候选 | 首个错误、模式/频率、DMA、卡、供电、复现率 | 仅由卡或信号中的一种 | 做同板、同镜像、已知正常卡与低速模式对照 |
| 只有“偶发识别不到/挂载失败” | 信息不足 | config/module、DTB、detect、复现率、卡/板矩阵和完整日志 | 任何固定根因 | 收集成功/失败各一份完整日志，一次只改变一个变量 |

## 结论等级提示

- 日志明确落入某函数失败路径时，通常只能对“失败层级”给出 `已确认`。
- 驱动加载、DTB、card detect 或未 `umount` 拔卡的证据与 A/B 同时支持某方向，但仍缺目标二进制或硬件测量时，使用 `高可信待验证`。
- 只有用户现象描述而没有 config/module、首个异常和阶段信息时，使用 `信息不足`。
