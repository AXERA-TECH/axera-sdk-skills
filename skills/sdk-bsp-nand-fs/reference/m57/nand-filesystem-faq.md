# NAND / 文件系统 FAQ

> 本文根据 nand文件系统FAQ、linux下nand及文件系统FAQ汇总整理。Linux NAND/MTD/UBI/烧录原则可供 M57、AX637 和 AX637R 复用；QNX/ETFS 条目仅适用于 M57，AX637/AX637R 不涉及该运行时文件系统。具体版本、board、Flash 型号和命令参数以目标 SDK 为准。

## 适用边界

- 覆盖 SPI NAND、MTD、UBI/UBIFS、QSPI/OSPI 和 AXDL/FDL 相关问题；文末 QNX ETFS 条目仅作为 M57 专属参考。
- 文中 `/dev/mtdX`、`/dev/link/<name>`、分区名和启动参数均为取证或示例，不得把示例编号当作固定接口。
- 擦除、坏块标记、重分区和烧录可能破坏数据；执行写操作前保存配置、镜像和日志。

M57 的 QNX 路径或其他目标的专用 Flash 服务是否参与，必须由目标构建链和运行时设备枚举证明；共性 Linux 条目不能反推这些实现。


### Q1：NAND 接 4 线，是 SDR 还是 DDR？是否需要 DTR？

驱动四线模式是 SDR，使用单边沿采样，不开启 DTR。性能瓶颈通常还包括 Flash 内部处理时间，不能只根据线数判断最终吞吐。

### Q2：单 NAND 方案中 A 核和 R 核如何互斥访问？

A 核和 R 核通过主域 OSPI 控制器访问外挂 Flash，使用 `hwspinlock` 与软件锁保护读、写、擦除、初始化和 CS GPIO 控制。A 核和 R 核的 Flash 参数必须严格一致；主域死锁时由 Safety 侧检测并通过 reset main 域恢复。

MCAL 的 `Fls_raiseLockPriority(FALSE/TRUE)` 可提升 MCAL 访问优先级，但会受 FLS 调度周期影响而降低 A 核 Flash 性能，不应长期对所有场景开启。

### Q3：新 NAND 颗粒需要确认哪些物理特性？

至少确认：

- 支持的接口线数和模式；
- page size、erase size、总容量；
- JEDEC ID；
- OOB layout；
- ECC 能力和要求；
- quad enable、feature register、dummy cycle 等器件差异。

## NAND 适配与启动失败

### Q4：适配新 NAND 颗粒需要修改哪些层？

按启动阶段逐层适配，不能只修改 Linux：

1. **Romcode/SBL**：在 `build/scripts/flash_config/` 增加颗粒 YAML（可参考 `sample.yaml`），在目标 `config.mk` 指定该 YAML；必要时配置 `sbl_opt_param`。
2. **MCAL FLS**：仅 NAND 场景需要适配主域 NAND；NOR+NAND 场景按实际设计适配 NOR。参考 `SafetyIsland/mcal/mcal_drv/Fls/src/Spi_Nand.c`、`SafetyIsland/mcal/mcal_drv/Fls/` 和 MCAL FLS 用户手册；若颗粒不在 Flash list，通常需要 AE 支持并发布 SDK。
3. **SPL/U-Boot**：修改目标 DTS 的 OSPI `nand0` 节点，并在 `boot/uboot/u-boot-2022.10/drivers/mtd/nand/spi/` 对应厂商表增加 ID、geometry 和器件钩子逻辑。
4. **Linux kernel**：修改 `kernel/linux/linux-6.1.83/arch/arm64/boot/dts/axera/` 对应 DTS 的 `spi_nand0` 节点，并在 `kernel/linux/linux-6.1.83/drivers/mtd/nand/spi/` 增加或修正器件表和钩子。
5. **MCAL EB**：若新增颗粒同时加入 EB 的 xdm、FLS 模板和 `OSPI_FlashChip` 枚举，枚举顺序必须与 `spi_nand_ids` 顺序一致。

### Q5：新板子启动失败，如何区分硬件、Flash 适配和参数问题？

先根据最早的启动日志判断是 NAND 读失败、数据校验失败还是后续镜像解析失败，然后按以下顺序排查：

1. 新板旧颗粒：先检查虚焊、供电、电平、走线和 CS；再降低 `nand_busclk`，若降频后恢复，重点调整 `rx_sample_delay`。
2. 新板新颗粒：确认硬件连接；确认 SBL、MCAL、U-Boot、Linux 四层都完成颗粒适配；确认 YAML 的硬件信息、`img_gzip_en`、命令序列和 `config.mk` 选择正确。
3. 对照 demo 板验证：demo 正常而客户板失败，优先比较硬件和时序；两者都失败，再回到软件适配和镜像链路。
4. scan 调参时先用低频确认基本读写，再把 scan 频率对齐到实际 SBL/目标阶段频率。

### Q6：新板 NAND 烧录失败，如何排查？

检查：

- 颗粒是否虚焊、供电和拨码状态是否正确；
- U-Boot/FDL 是否包含该颗粒适配；
- 烧录包中的分区和镜像是否属于当前 `PLAT`；
- 是否误用了全擦、错误的分区边界或不匹配的 geometry；
- 烧录失败后保留完整 FDL/AXDL 日志，禁止直接重复全擦覆盖现场。

## 坏块管理

### Q7：坏块标记会被擦除吗？

会。坏块标记所在区域可以被 erase 指令擦除。AXDL 勾选“全擦”时会擦整颗 Flash，人工标记的坏块可能被清除；不勾选全擦也可能擦除实际使用区域，因此不能把“不全擦”理解为“完全不碰坏块标记”。

擦除接口是否跳过坏块取决于调用方和参数。跳过可避免擦写坏块，但人工误标记会让可用空间减少；直接擦除可能在后续写入失败后重新标记。具体策略必须以 FDL/工具实现为准。

### Q8：erase 失败时谁负责标记坏块？

标准 MTD 层通常报告错误，不直接替调用方完成坏块标记。FDL 等上层应在 NAND erase 失败后使用带坏块标记的专用流程；不要在公共 erase 接口中无条件改变所有平台的语义。OOB 正常但 erase 失败的块可能无法提前从地址转换中判断，只能通过 erase 结果发现。

### Q9：启动阶段的坏块预留是多少？

Wiki FAQ 记录的默认 ROM code 预留范围为 `768K`：256K block 预留 3 个，128K block 预留 6 个；NOR 记录为 128K。该值属于启动链约束，调整 SBL/metadata 分区前必须按当前芯片、ROM code 和 SDK 版本重新确认，不应跨平台套用。

### Q10：驱动层是否做 wear leveling？

驱动层提供访问接口和基础坏块处理，不提供 wear leveling；负载均衡由文件系统层负责。不能用驱动层测试替代 UBIFS/ETFS 的长期寿命验证。

## Linux MTD / UBI

### Q11：如何确认 MTD 设备和分区的对应关系？

Linux 使用：

```sh
cat /proc/mtd
ls -al /dev/link/*
cat /sys/class/mtd/mtd*/name
```

QNX 使用：

```sh
cat /proc/ax_proc/mtd
```

MTD 编号随注册顺序、board DTS 和 probe 顺序变化。脚本和 OTA 必须按分区 label 或 `/dev/link/<name>` 定位，禁止写死 `/dev/mtdN`。

### Q12：`S90rescan-mtd` / `rescan_all_mtd.sh` 是否必须执行？

若当前 SDK 将坏块扫描延迟到启动脚本，应在任何 MTD 使用前执行，包括挂载 UBI 文件系统之前。脚本可以延后到业务服务起来后调用，但在扫描完成前不能读写 MTD 或 attach/mount 依赖该 MTD 的 UBI。

### Q13：MTD 分区是否需要手动修改 mtdpart？

以 Wiki 记录的较新版本为准，mtdpart 分区通常由 U-Boot 传参或构建生成链路提供，不应直接手改生成文件。实际排查要同时核对 platform JSON、生成 metadata、U-Boot bootargs、运行时 `/proc/mtd` 和 SDK revision。

### Q14：如何测试 MTD 读写性能？

优先使用 SDK 的 `mtd_debug` 或对应 `mtd-utils` 工具，并记录命令、分区、数据量和 `time`：

```sh
mtd_debug read /dev/mtdX 0x0 0x200000 /tmp/read
mtd_debug write /dev/mtdX 0x0 0x200000 /tmp/read
```

数据量太小会被启动和调度开销主导，单次结果不能作为基线；读写长度不得超过目标分区大小。若读写都慢，先查公共路径；只有单向慢时，再对比读/写路径、擦除、DMA、文件系统和控制器配置。比较 Linux 与 QNX 时必须注明设备层，因为 QNX 还叠加 ETFS。

### Q15：不同存储介质推荐什么文件系统？

Wiki FAQ 的常见基线是：

| 介质/用途 | 常见选择 |
|---|---|
| SPI NOR | `jffs2` |
| SPI NAND | `ubifs` |
| eMMC | `ext4` |
| 只读 rootfs | `squashfs`（或 initrd/cramfs/initramfs） |
| 开发调试 | `NFS` |

最终选择还要结合是否掉电、是否可写、镜像制作链和产品启动要求。

### Q16：如何把 UBIFS 作为只读文件系统？

UBIFS 本身是可读写文件系统。临时只读可以使用：

```sh
mount -t ubifs -o ro ubi2 /opt
mount -o remount,ro /opt
```

若产品需要固化的只读 rootfs，优先评估 `squashfs`，可写数据单独放到可写分区；不要仅通过挂载选项掩盖镜像类型和 OTA 设计问题。

## QNX ETFS

### Q17：QNX ETFS 与 Linux NAND 文件系统有什么区别？

ETFS 使用 data 区与 spare/OOB 区保存文件系统信息，Linux 主流 MTD 方案通常不采用同样的 ETFS transaction 组织。ETFS 设备不能简单当作具有连续物理地址的裸设备。

ETFS 写入的最小粒度通常是 `page + etfs_trans`；包含 ETFS transaction 的镜像不能随意按 512 字节拆包写入。烧录前必须确认镜像类型、record 大小和目标是 ETFS1 还是 ETFS2。

### Q18：`/dev/etfs2` 大小和 `userdata.img` 怎么确定？

`etfs2` 起始地址由分区表决定，扩大分区需要向前调整起始地址且不能覆盖前面的镜像分区。运行时 ETFS 会使用后续可用区域，打包镜像大小不必机械地填满整个分区。

注意命令单位可能不同：U-Boot 分区数值通常按字节，`etfsctl` 或相关工具可能按 KB 输出，调整前必须统一单位并按 erase/page 对齐。

### Q19：QNX `mtdpart` 启动有什么依赖？

mtd 进程依赖 ETFS 后端先起来。常见启动顺序是先等待 `/dev/etfs1`，再启动 `mtdpart`，依赖 mtd 的服务继续增加 wait；实际启动脚本以目标 QNX buildfile 为准。

### Q20：QNX NAND 性能比 Linux 低是否正常？

QNX 的 mtd 层建立在 ETFS 之上，性能上限受 ETFS、IPC、MCAL 调度和异步路径影响；不能直接将 QNX `mtd_debug` 结果与 Linux raw MTD `dd` 结果比较。应使用相同数据量、相同擦除策略和明确的设备层进行对照。

## 来源与追溯

- nand文件系统FAQ。
- linux下nand及文件系统FAQ汇总。
- M57 flash scan功能使用指南。
- QNX ax_mtd知识库v1.0。
