# AX615 Linux SD 卡代码地图

本文只记录当前工作区中与**Linux 启动后 SD 卡问题**相关的代码入口、配置、日志锚点和证据边界。路径均以 `ax615_trunk` 为根目录表示；用户实际运行的 kernel、DTB、rootfs、模块和卡内容必须另行核对。

BL1/SPL、U-Boot 阶段不在本版 skill 的重点范围，后续有需求时再补充启动阶段代码地图。

## 1. Linux AXERA SDHCI host 驱动

文件：`kernel/linux/linux-4.19.125/drivers/mmc/host/sdhci-axera.c`

| 函数/符号 | 诊断用途 | 典型日志/证据边界 |
|---|---|---|
| `sdhci_axera_probe()` | platform probe、资源/能力解析、`mmc_of_parse()`、GPIO、PHY、`sdhci_add_host()` 和 host 建立 | `axera sdhci probe`；若后续没有 host 注册或 `mmc` 枚举日志，只能划定在 probe/host 建立之后的失败区间 |
| `mmc_of_parse()` 调用 | 解析标准 MMC DTS 属性 | `broken-cd`、`cd-gpios`、`cd-inverted`、`cd-debounce-delay-ms`、`non-removable`、`disable-wp` 等由 MMC core 解析 |
| `sdhci_axera_phy_init()` | Cadence HRS04 PHY 访问、DLL reset、DTS delay 写入 | 写 PHY 失败需结合返回值；PHY lock 结果由后续 `sdhci_axera_read_phy_reg()` 的 `phy lock successful` / `phy lock failed` 日志确认 |
| `sdhci_axera_read_phy_reg()` / `sdhci_axera_write_phy_reg()` | PHY 读写握手和 ACK 超时 | 需结合 probe/初始化返回值 |
| `get_sd_pwr_ref_gpio()` | 从 DTS 和芯片类型选择 `pwr_sw_gpio`、`pwr_en_gpioD/Q` | `Failed to get sd pwr_sw_gpio from dts`、`Failed to get sd pwr_en_gpio from dts` |
| `sdhci_axera_set_power()` | SD 电源 enable/disable；无 `pwr_en_gpioD/Q` 时配合 probe 设置的保持供电/不主动断电路径 | `no pwr_en gpio find in dts, may cannot control power off` 由 `sdhci_axera_probe()` 打印；`sdhci_axera_set_power()` 后续按 `SDHCI_QUIRK2_HOST_OFF_CARD_ON` 走保持供电 |
| `sdhci_axera_voltage_switch()` | 通过 `sd_pwr_sw_gpio` 切换 3.3 V/1.8 V | `no sd_pwr_sw_gpio, cannot switch to 1.8V` |
| `sdhci_axera_start_signal_voltage_switch()` | 3.3 V/1.8 V 稳定性检查 | `3.3V regulator output did not become stable`、`1.8V regulator output did not become stable` |
| `sdhci_axera_execute_tuning()` | SD/eMMC tuning 路径和结果；SD 软件 tuning 当前仅对 `MMC_TIMING_UHS_SDR104` 执行 | `no tuning point found`、`hw tuned ok, val:0x%x`、`Tuning failed, falling back to fixed sampling clock`、`Tuning is not completely, falling back to fixed sampling clock, fixed val:%d` |
| `sdhci_axera_mst_chip_type_handle()` | 按 AX615 型号限制 master 能力 | `AX615D SD mst only design 3.3V, not support UHS, switch 3.3V mode` |
| `axera_sdio_rescan()` | SDIO host 重新扫描 | `axera sdio_host is NULL`；与 SD storage `mmcblk` 分开分析 |
| `sdhci_axera_suspend()` / `sdhci_axera_resume()` | suspend/resume 后 retune 和 PHY 重初始化 | 休眠恢复问题需比较 suspend 前后日志 |
| `module_platform_driver()` | platform driver 注册 | 说明驱动代码支持 built-in 和 module 两种构建方式，实际方式由 config 决定 |

### 管脚上下拉边界

驱动中的 SD pin 上下拉动态配置函数处于 `#if 0`，注释说明硬件设计由 VDD 上拉，软件不动态调整更合适。因此：

- 卡识别不上时需要核对实际 pinmux、CMD/DAT 上拉和硬件设计；
- 不能假设 Linux 驱动已经设置了所需上下拉；
- 也不能仅凭该代码被关闭就断言板级上拉缺失，必须结合原理图、电平或硬件测量。

## 2. 驱动 built-in 与 module

### 配置与编译入口

- Kconfig：`kernel/linux/linux-4.19.125/drivers/mmc/host/Kconfig`
  - `CONFIG_MMC_SDHCI_AXERA` 是 `tristate`，支持 `=y`、`=m` 或未启用。
- Makefile：`kernel/linux/linux-4.19.125/drivers/mmc/host/Makefile`
  - `obj-$(CONFIG_MMC_SDHCI_AXERA) += sdhci-axera.o`
- 代表性 defconfig：
  - `kernel/linux/linux-4.19.125/arch/arm/configs/axera_AX615_emmc_defconfig`
  - `kernel/linux/linux-4.19.125/arch/arm/configs/axera_AX615_nor_emmc2sd_defconfig`

不同 defconfig 可能分别使用 built-in 或 module；必须核对用户设备实际 `.config` 或 `/proc/config.gz`，不能以某一个示例 defconfig 推导所有产品配置。

### `=y` built-in

- 驱动编入 kernel image，启动时由 platform bus 自动匹配和 probe；
- 通常没有独立 `sdhci-axera.ko`，不需要 `insmod`/`modprobe`；
- 识别不上时优先检查 `dmesg`、目标 DTB 的 `compatible/status/reg/interrupts`、probe 返回值、card detect 和供电。

### `=m` module

- 应生成 `sdhci-axera.ko`，并随 rootfs/模块包安装；
- 还需 MMC/SDHCI 依赖模块，例如 `mmc_core.ko`、`mmc_block.ko`、`sdhci.ko`、`sdhci-pltfm.ko`；具体名称和路径以目标构建产物为准；
- 可通过 `modprobe sdhci-axera` 让模块工具解析依赖；若系统无 module dependency database，再按目标产物依赖顺序使用 `insmod`；
- `modprobe: module ... not found` 可能表示模块未打包、kernel version 不匹配或驱动其实是 built-in，不可直接判断源码没有驱动。

### 只读取证

```text
zcat /proc/config.gz | grep -E 'CONFIG_MMC|CONFIG_MMC_SDHCI|CONFIG_MMC_SDHCI_AXERA'
lsmod | grep -iE 'mmc|sdhci'
find /lib/modules/$(uname -r) -type f -name '*mmc*.ko*' -o -name '*sdhci*.ko*'
dmesg -T | grep -iE 'sdhci|mmc|module|unknown symbol|version magic'
```

如果 `/proc/config.gz` 不存在，应读取目标构建的 `.config`；如果 rootfs 没有 `find` 或 `modprobe`，保留工具缺失事实并直接核对模块包。

## 3. DTS、card detect、供电和地址

### 代表性 DTS

- `kernel/linux/linux-4.19.125/arch/arm/boot/dts/axera/AX615.dtsi`
  - aliases 中的 `mmc0`/`mmc1` 仅表示默认设备别名，不代表所有板型的实际控制器用途。
- `kernel/linux/linux-4.19.125/arch/arm/boot/dts/axera/AX615_nor_emmc2sd.dts`
  - 代表性 emmc2sd 变体：SD 使用 `sdhci@1B40000`，配置 `no-sdio`、`no-mmc`、`broken-cd` 和 Cadence PHY delay；电源 GPIO 是否存在必须以实际目标 DTB 为准。
- 其他 `AX615_*emmc2sd.dts` 和 `AX615_emmc.dts`
  - 按实际板型核对 controller 地址、用途、GPIO 和 UHS 属性。

### card detect 两种方式

1. `broken-cd`
   - MMC core 设置 polling 能力，周期性检查卡状态；
   - 插拔检测存在延迟，不能用“插卡后没有立即日志”直接判断 card detect 失效；
   - 排查 polling 是否启动、host 是否已注册，以及轮询周期内是否出现枚举日志。

2. `cd-gpios`
   - 使用 GPIO detect，结合 `cd-inverted` 和 `cd-debounce-delay-ms`；
   - 排查 GPIO 编号、pinmux、极性、消抖、插拔电平变化和中断；
   - 极性错误可能导致“始终有卡”或“始终无卡”。

`broken-cd` 与 `cd-gpios` 应按目标 DTS 的实际设计选择；不能同时拿两套假设解释同一现场。`non-removable` 一般用于固定设备，不应随意用于可插拔 SD 卡来掩盖 detect 问题。

### 供电与 voltage switch

需核对：

- `pwr_en_gpioD` / `pwr_en_gpioQ`：`get_sd_pwr_ref_gpio()` 按芯片类型选择的 SD 电源使能 GPIO；
- `pwr_sw_gpio`：3.3 V/1.8 V UHS 电压切换；
- `post-power-on-delay-ms`：上电后等待时间；
- 缺少 `pwr_en_gpioD/Q` 时，`sdhci_axera_probe()` 会清除 `MMC_CAP_AGGRESSIVE_PM`、设置 `MMC_PM_KEEP_POWER` 和 `SDHCI_QUIRK2_HOST_OFF_CARD_ON`，并打印 `no pwr_en gpio find in dts, may cannot control power off`；这表示当前代码走的是无电源 GPIO 的保持供电路径。

### 其他 DTS 字段

`compatible`、`status`、`reg`、`interrupts`、`no-sdio`、`no-mmc`、`bus-width`、`max-frequency`、`cap-sd-highspeed`、`sd-uhs-*`、`disable-wp` 和 `cdns,phy-*`。

DTS 源码只是候选配置；必须确认编译后的目标 DTB被实际加载，且板级覆盖没有改变这些字段。

## 4. 文件系统、readonly 与安全拔卡

### 相关配置

重点核对：

- `CONFIG_FAT_FS`
- `CONFIG_VFAT_FS`
- `CONFIG_EXFAT_FS`

与 SDHCI 驱动相同，这些配置可能是 `=y`、`=m` 或未启用。若为 `=m`，还要确认 FAT/VFAT/exFAT module 已打包和加载。

### readonly 分层

```text
mount | grep mmcblk
cat /sys/block/mmcblk*/ro
dmesg -T | grep -iE 'FAT-fs|exFAT|read-only|not properly unmounted|I/O error'
```

- `mount` 中 `(ro)`：挂载结果为只读，可能是显式 `-o ro`、文件系统错误或设备只读；
- `/sys/block/mmcblk*/ro` 为 `1`：块设备层只读，还需核对写保护、驱动和卡状态；
- `Volume was not properly unmounted`、`Filesystem has been set read-only` 等日志：优先检查未正常卸载、文件系统元数据损坏和更早的 I/O 错误；
- 仅凭 readonly 不能确认是卡坏、`disable-wp` 缺失、文件系统损坏或 SDHCI 异常。

### 安全拔卡规范

只要 SD 分区已挂载或存在写入，就必须先执行：

```text
sync
umount /mnt/<sdcard>
mount | grep mmcblk
```

确认对应分区不再出现在 mount 输出后才能拔卡。若 `umount` 返回 `device is busy`，先使用：

```text
fuser -vm /mnt/<sdcard>
lsof /mnt/<sdcard>
```

找到并停止占用进程，再重新 `umount`。不能忽略 busy 直接拔卡。

未 `umount` 拔卡或异常断电可能导致：

- 脏页、目录项或 FAT/exFAT 元数据未写回；
- 下次挂载失败、自动 readonly 或文件丢失；
- `card removed` 后出现 block I/O error；
- polling 模式因检测延迟，在物理拔卡后仍短暂发起 I/O。

文件系统损坏不能反推 SDHCI 控制器必然故障。应先区分正常使用期 I/O error 与 `card removed` 之后的预期失败。

## 5. Linux 现场只读取证

```text
dmesg -T | grep -iE 'mmc|sdhci|sdio|tuning|phy|voltage|power|timeout|crc|adma|dma|error|fail|read-only|FAT-fs|exFAT'
cat /proc/partitions
ls -l /sys/class/mmc_host
ls -l /sys/block/mmc*
mount
blkid
lsmod | grep -iE 'mmc|sdhci'
zcat /proc/config.gz | grep -E 'CONFIG_MMC|CONFIG_FAT|CONFIG_EXFAT'
```

针对实际 host/card 路径：

```text
cat /sys/class/mmc_host/mmc*/mmc*/type
cat /sys/class/mmc_host/mmc*/mmc*/name
cat /sys/class/mmc_host/mmc*/mmc*/cid
cat /sys/class/mmc_host/mmc*/mmc*/csd
cat /sys/class/mmc_host/mmc*/mmc*/scr
cat /sys/block/mmcblk*/ro
```

以上 glob 在路径不存在时可能返回错误；保留错误文本，不要把“路径不存在”改写为“卡损坏”。涉及 `dd`、`mkfs`、`fsck -y`、分区修改或格式化前，必须确认设备节点、备份数据和操作授权；诊断第一步不做破坏性写操作。
