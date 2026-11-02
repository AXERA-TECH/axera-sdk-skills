# AX637/AX637R NAND / 文件系统 FAQ

> 本文根据 nand文件系统FAQ和 linux下nand及文件系统FAQ汇总整理，只保留 AX637/AX637R 可复用的 Linux NAND/MTD/UBI、分区与烧录原则。具体版本、board、Flash 型号和命令参数以目标 SDK 为准。

## 适用边界

- 覆盖 SPI NAND、MTD、UBI/UBIFS、QSPI/OSPI 和 AXDL/FDL 相关问题。
- 不包含 QNX、virtual flash、MCAL FLS 或 MCAL EB；这些属于 M57 reference。
- `/dev/mtdX`、`/dev/link/<name>`、分区名和启动参数均为取证或示例，不得把示例编号当作固定接口。
- 擦除、坏块标记、重分区和烧录可能破坏数据；执行写操作前保存配置、镜像和日志。

## NAND 方案与硬件

### Q1：NAND 接 4 线，是 SDR 还是 DDR？是否需要 DTR？

四线模式本身不等于 DDR/DTR。是否启用 DTR 取决于目标控制器、Flash 颗粒和 DTS/驱动配置；性能还受 Flash 内部处理时间影响，不能只根据线数判断吞吐。

### Q2：新 NAND 颗粒需要确认哪些物理特性？

至少确认接口线数和模式、page/erase/OOB geometry、容量、JEDEC ID、ECC 能力和要求、坏块标记、quad enable、feature register、dummy cycle 及读写/擦除命令差异。

## NAND 适配与启动失败

### Q3：适配新 NAND 颗粒需要修改哪些层？

按目标 AX637/AX637R 构建链逐层核对：

1. **Romcode/SBL**：核对 `build/scripts/flash_config/` 的颗粒 YAML、目标 `config.mk` 和必要的 `sbl_opt_param`。
2. **SPL/U-Boot**：核对目标 DTS 的 OSPI NAND 节点，以及 `boot/uboot/u-boot-2022.10/drivers/mtd/nand/spi/` 中的厂商表、ID、geometry 和器件钩子。
3. **Linux kernel**：核对目标 arm64 DTS 的 SPI NAND 节点，以及 `kernel/linux/linux-6.1.83/drivers/mtd/nand/spi/` 的器件表和钩子。
4. **Safety/RTOS 启动链**：仅在目标构建确实引用时核对相关启动和 Flash 配置；不要由 generic 目录存在推断当前平台使用该运行时路径。

### Q4：新板启动失败，如何区分硬件、Flash 适配和参数问题？

先定位最早错误，再按顺序检查：

1. 新板旧颗粒：检查虚焊、供电、电平、走线和 CS；降频后恢复时重点检查采样延迟和信号质量。
2. 新板新颗粒：确认 SBL、U-Boot、Linux 和实际 Safety/RTOS 启动链均完成所需适配，并核对 YAML、压缩选项、命令序列和 `config.mk`。
3. demo 正常而客户板失败时优先比较硬件和时序；两者都失败时再检查软件适配和镜像链路。
4. scan 调参先以低频确认基本读写，再把频率对齐到实际启动阶段；AX637/AX637R 的 scan 命令是否启用须核对目标 defconfig。

### Q5：新板 NAND 烧录失败，如何排查？

检查颗粒焊接、供电和拨码，确认 U-Boot/FDL 是否包含该颗粒适配，烧录包是否属于当前 `PLAT`，分区边界、镜像和 geometry 是否匹配。失败后保留完整 FDL/AXDL 日志，禁止直接重复全擦覆盖现场。

## 坏块管理

### Q6：坏块标记会被擦除吗？

坏块标记所在区域可以被 erase。AXDL 全擦会擦整颗 Flash，人工标记可能被清除；不全擦也可能擦除实际使用区域。擦除接口是否跳过坏块取决于调用方和参数，必须以当前 FDL/工具实现为准。

### Q7：erase 失败时谁负责标记坏块？

标准 MTD 层通常报告错误，不替调用方完成坏块标记。FDL 等上层应在 erase 失败后进入明确的坏块标记流程；不要在公共 erase 接口中无条件改变所有平台语义。

### Q8：驱动层是否做 wear leveling？

驱动层提供访问接口和基础坏块处理，不负责 wear leveling；负载均衡由 UBI/UBIFS 等文件系统层承担。驱动层测试不能替代长期文件系统寿命验证。

## Linux MTD / UBI

### Q9：如何确认 MTD 设备和分区的对应关系？

```sh
cat /proc/mtd
ls -al /dev/link/*
cat /sys/class/mtd/mtd*/name
```

MTD 编号随注册、DTS 和 probe 顺序变化。脚本和 OTA 必须按分区 label 或 `/dev/link/<name>` 定位，禁止写死 `/dev/mtdN`。

### Q10：`S90rescan-mtd` / `rescan_all_mtd.sh` 是否必须执行？

若当前 SDK 将坏块扫描延迟到启动脚本，应在任何 MTD 使用以及 UBI attach/mount 之前完成扫描。是否启用该路径必须根据目标 rootfs、启动脚本和运行时日志确认。

### Q11：MTD 分区是否需要手动修改？

通常由 U-Boot 传参或构建生成链路提供，不应直接修改生成产物。排查时同时核对 platform JSON、生成 metadata、U-Boot mtdparts/bootargs、运行时 `/proc/mtd` 和 SDK revision。

### Q12：如何测试 MTD 读写性能？

优先使用 SDK 对应的 `mtd-utils`/调试工具，记录命令、设备层、分区、数据量、擦除策略和 `time`。读写长度不得超过目标分区，单次小数据结果不能作为基线；只有单向慢时再分别检查读/写、擦除、DMA、文件系统和控制器路径。

### Q13：不同存储介质推荐什么文件系统？

| 介质/用途 | 常见选择 |
|---|---|
| SPI NOR | `jffs2` |
| SPI NAND | `ubifs` |
| eMMC | `ext4` |
| 只读 rootfs | `squashfs` 或产品指定只读镜像 |
| 开发调试 | `NFS` |

最终选择还要结合掉电恢复、可写性、镜像制作链和产品启动要求。

### Q14：如何把 UBIFS 作为只读文件系统？

临时只读可以使用只读挂载或 remount。产品需要固化的只读 rootfs 时，优先评估 `squashfs`，可写数据放独立分区；不要仅靠挂载参数掩盖镜像类型和 OTA 设计问题。

## 来源与追溯

- nand文件系统FAQ。
- linux下nand及文件系统FAQ汇总。
