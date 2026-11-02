# linux下nand及文件系统FAQ汇总

## Q1: 单 NAND 方案，A 核和 R 核（safety）怎么互斥读写？安全吗？怎么保证mcal优先访问权？

A核和R核互斥访问使用主域OSPI控制器控制外挂flash。使用hwspinlock + 软件锁形式实现互斥，互斥阶段为R核mcal与Acore spl/uboot/kernel各阶段并行运行期间，具体保护对象，确保所有flash读写擦操作，初始化，以及cs-gpio控制。

互斥操作的前提条件是A核和R核对flash的配置参数需要严格一致，确保两域访问的配置一致性。

如果主域死锁，safety能够检测到主域异常，有reset main域方案保证可恢复。

目前有Mcal提供了接口Fls_raiseLockPriority(FALSE/TRUE);来提升mcal优先访问权。该功能开启后，受Mcal中fls调度周期影响，Acore会有不同程度flash性能下降。主要表现为，调度周期越长，Acore的flash访问性能越低。建议mcal按场景提升访问权限。不建议全域保持优先访问权限。

## Q2: 适配新的nand颗粒，代码需要做什么修改?

首先确认颗粒的一些物理特性，比如支持几线，page size，erase size，id信息。oob layout，ecc能力等。

### Romcode/sbl阶段：

- 新增build/scripts/flash_config的yaml文件，可参考sample.yaml设置
- 同时需要修改config.mk。指定该yaml文件。
- 虽然romcode和sbl公用一个解析flash参数的ymal文件，但sbl有一些独立优化参数sbl_opt_param, 具体配置说明可参考sample.yaml注释。这里主要是为了让sbl可以运行在主频和spi频率更高的场景下。提升sbl的读性能。
- 详情参考00 - AX SDK 使用说明.docx文档第七章SPI NAND Flash开发指南

### mcal阶段：(如有)

- 首先在工程在单nand场景下，mcal才会访问主域的nand，需要适配nand, 如果是nor nand方案，只需要适配nor。
- 参考文档：mcal/plugins/Fls/Doc/AXERA-M57 MCAL FLS UM.docx 4.11章节，有支持flash list清单，客户可直接在eb端通过 FlsChipSelect 选择对应颗粒（如 W25Q128、W25C138、GD25F64F、GD25LQ64、W35N01JW、W35N04JW、W25N02KW 等 NOR/NAND 颗粒），并配置 FlsTypeSelect、FlsOspiXferLines、QspiClkSrcRef、FlsCxGpioControl、FlsCxGpioOffset 等相关参数即可。

- 如果支持flash list清单没有该颗粒，需要爱芯AE支持, 释放新SDK。
- 爱芯AE支持可参考如下逻辑：
  - 以新增兆易创新的gd5f 4线nandflash颗粒为例。
  - 打开 SafetyIsland/mcal/mcal_drv/Fls/src/Spi_Nand.c，在 spi_nand_ids 数组中增加颗粒的描述信息，即在 spi_nand_ids[] 中新增一个 struct nand_info 条目，依次填写颗粒名称、ID/id_len、sector_size、options、protocol 以及 ctrl_ops、data_ops、init 等字段，颗粒的硬件信息可参考颗粒的芯片手册，例如：

```c
.protocol  = SPI_PROTOCOL_4S,          // 需要使用四线模式
.ctrl_ops  = &spinand_default_ctrl_ops, // 默认的一些控制操作，这些都是最基础的指令，一般不会变
.data_ops  = &spinand_data_ops_quad_sdr, // 四线模式下的读写指令，一般四线指令也比较统一，如果存在差异可以修改相应宏定义即可
.init      = w25n02kw_init,             // 切换四线的实现，因为切四线指令和前面已经支持 w25n02kw 颗粒也是一致的，这里直接用一样的实现方法；如果存在指令或者寄存器 quad enable bit 位差异，修改相应的指令和寄存器 bit 操作位即可
```

EB fls插件中需要将这款颗粒的信息添加进去，即在 EB 生成的配置中，于 `FlsChipSelect` 的枚举清单 `<var name="FlsChipSelect" type="ENUMERATION">` 下新增该颗粒项，并将其作为默认值。

### xdm文件修改

在 xdm 模板中按新颗粒补充字段映射，例如 `[MS "4"].chipIndex`、`fls_jobErrorNotification`、`maxReadNormalMode`/`maxReadFastMode`、`sampleSpeed`/`sampleEdge`/`sampleDelay`、`sectorListPtr`/`sectorListNum` 等，其中 `chipIndex` 需指向对应的颗粒枚举（如 `W25Q128_NORFLASH_CHIP`）。

### Fls 的模板文件修改

对应代码中 Fls_ConfigType_s 数据结构中 OSPI_FlashChip 需要新增枚举值（截图中的枚举依次包含 W25Q128、GD25F64F、GD25LQ64 等 NOR 颗粒，以及 W35N01JW、W35N04JW、W25N02KW、GD5F4G 等 NAND 颗粒）：

注意：这里的枚举排序需要和spi_nand_ids数组中的排序是一致的。

### spl/uboot阶段：

- 在uboot/u-boot-2022.10/arch/arm/dts下对应工程的dts文件，修改ospi节点下nand0节点信息。
- 在uboot/u-boot-2022.10/drivers/mtd/nand/spi/相应厂家颗粒信息文件中增加spinand_info table表，新增id等硬件信息，以及相应的钩子函数的逻辑实现。
- 详情参考00 - AX SDK 使用说明.docx文档第七章SPI NAND Flash开发指南

### kernel阶段：

- 在kernel/linux/linux-6.1.83/arch/arm64/boot/dts/axera/下对应工程的dts文件，修改ospi节点下spi_nand0节点信息。
- 在kernel/linux/linux-6.1.83/drivers/mtd/nand/spi/相应厂家颗粒信息文件中增加spinand_info table表，新增id等硬件信息，以及相应的钩子函数的逻辑实现。
- 详情参考00 - AX SDK 使用说明.docx文档第七章SPI NAND Flash开发指南

## Q3: 客户新板子 NAND romcode启动失败，怎么排查？

- 首先通过log确认是否是nand读失败或者读数据有问题。如果确认是nand问题，继续下面步骤
- 新板子，老颗粒，即客户的板子是新打板的，但是颗粒是已经在老的板子上支持过，
  - 首先排查新板子颗粒是否有虚焊等硬件问题
  - 把yaml的nand_busclk频率降低，如果降频后可以启动，说明yaml里rx_sample_delay参数设置可能不合理，需要调整。可以根据示波器查看波形，确认是否需要调整rx_sample_delay参数或者采用最简单方式去try rx_sample_delay参数。
- 新板子，新颗粒
  - 首先排查新板子颗粒是否有虚焊等硬件问题
  - 确认代码是否做了新颗粒的适配
  - 检查yaml文件参数设置是否正确。比如硬件信息，img_gzip_en使能等。命令序列设置是否正确。config.mk设置是否正确。
  - nand_busclk降频，try rx_sample_delay参数。

## Q4: 客户新板子 NAND 烧录失败，怎么排查？

- 首先排查新板子颗粒是否有虚焊等硬件问题。
- 确认烧录板子拨码状态是否正确。
- 确认uboot代码中是否支持新增颗粒的适配。

## Q5: 坏块标记会被擦除掉吗？

- 会。标记的坏块都是可以被擦除的，标记的区域本身是可以被erase指令擦除。
- fdl2在擦除时不会跳过坏块，烧录工具axdl如果勾了"全擦"，整个 flash 都擦，人工标记的坏块会被清掉；不点全擦也只是擦"用到的区域"，不是不擦。

## Q6: 驱动层会做磨损均衡吗？

- 驱动层只提供操作接口，以及简单跳坏块逻辑，不提供磨损均衡等操作，负载均衡只有文件系统才会做。

## Q7: erase 失败时怎么标记坏块？

- 标准 MTD 层不处理坏块，只把信息报出去，由调用 mtd 的一方进行坏块标记。

## Q8: 怎么看 mtd 设备和分区的对应关系？

- Linux：`cat /proc/mtd`、`ls -al /dev/link/*`
- 注意：mtd 设备号不固定，与注册顺序有关。但 `/dev/link/kernel_b` 一定是 kernel 分区，虽然对应 mtd 号不固定，测试脚本建议用 `/dev/link/xxx` 而不是写死 mtd 号

## Q9: mtd 读写性能怎么测？

- 最简单使用dd命令，可以编译mtd_speedtest或使用mtd-utils的测试命令。
- 读10M文件命令：`dd if=/dev/mtdx of=/dev/null bs=10M count=1 iflag=direct`
- 写10M文件命令：`dd if=/dev/null of=/dev/mtdx bs=10M count=1 oflag=direct`
- 注意，dd写是不含擦除动作，如果要写测试包含擦除的时间，请使用nandchar设备节点。
- 写/读的数据量不能超过分区大小：如 rtos_b 分区只有 2M，写 10M 文件报错，这不是驱动问题，换分区或按分区大小测。

## Q10：OSPI 和 QSPI 是什么关系？

- 按域区分：主域（main/A核）是 OSPI 控制器，safety 域（R核）是 QSPI 控制器。
- 主域无论 4 线 8 线nand都可以挂OSPI控制器下；safety 域因为QSPI控制器，不能挂8线nand。
- 单nand方案只用主域的 OSPI控制器。

## Q11: 使用mtd scan命令扫描要注意什么？

- mtd scan命令的调优参数可以给任何阶段使用，而不仅限于给uboot调优参数使用。
- 先确定扫描出来的rx_delay参数是给哪个阶段用，设置主频一定要和这阶段配置一致，比如想通过uboot下mtd scan扫描rx_delay参数给SBL用。那么除了目标频率设置要和SBL下一致外，主频设置也需要和SBL下一致。
- 修改主频设置需要修改uboot dts中的主频，目标频率可以直接在命令中设置。
- 如果在早期开发阶段，不确定uboot能否在当前频率下能够正常运行，可以在dts中调低频率，导致mtd功能正常，然后scan命令的频率再和目标频率对齐即可。
- mtd scan使用参考M57 flash scan功能使用指南

## Q12: only nand 工程要开 FLS_SINGLE_FLASH_MODE 吗？

- 需要，但是我们平台工程不需要重新去eb生成配置文件，因为当前提前放了一份nand配置文件，makefile脚本会自动处理平台，编译NAND的配置文件，主要逻辑是，代码下存放一份nand的fls配置文件，在编译demo_only_nand，替换到fls当前配置文件。编译结束恢复会之前配置。
- 客户工程仍按照标准流程去eb配置。生成配置文件。

## Q13: 改了 erasesize / 开 FLS_CUSTOM_BLOCK_ERASE_EN 后 Fls 初始化失败？

- 开64K擦除后测试报错，只改 size 不改 sector 配置时，Fls 初始化/测试报错
- 正确改法：sectorSize 和 numberOfSectors 按 64K 重新分配
- sectorPageSize 不用改

## Q14: M57TEST-BOOTCNT-001 Test Fail > FLS job failed 什么原因？

- boot_cnt demo 与 fls_demo 是直接访问fls驱动的，没有任何锁，是有相互影响，所以测试boot_cnt 任务需要默认关闭fls测试；

## Q15: Vspiflash_MainFunction 和 Fls_MainFunction 是什么关系？

- 其实没什么关系，放在一起是为了用户使用时无需感知。
- Vspiflash_MainFunction 是处理虚拟flash任务的主函数，需要周期调度，本身是一个后台程序，无需用户感知，减少客户定制负担，便将其放到Fls_MainFunction中。
- 客户也可以自行配置放到外层去调度，但是注意，虚拟falsh任务调度周期必须要大于fls的调度周期，因为虚拟flash会使用到fls接口，如果调度小于或者等于，虚拟flash后台任务无法正常调用fls功能。

## Q16: OTA / 虚拟 flash 读写速率慢？

- safety 侧访问的是虚拟 flash，走 IPC + mcal 调度 + 异步；且IPC单笔数据传输限制在4k。
- mcal 只是 demo 实现，用户可自行优化：缩短 fls 调度周期、fls 改同步方式（可能影响其他任务实时性）。

## Q17: 不同存储介质分别推荐用什么文件系统？

- SPI NOR → **jffs2**；SPI NAND → **ubifs**；eMMC → **ext4**；只读 / 掉电易失 rootfs → **squashfs**（或 initrd/cramfs/initramfs）；开发调试 → **NFS**。
- 只读 rootfs + 可写数据：rootfs 用 squashfs，另划读写分区挂到指定目录。

## Q18: 要求把 ubifs 改成只读文件系统怎么办？

- `ubifs` 本身**都是可读写的**；需要只读可选 **squashfs** 文件系统。
- 若只是临时用只读版本，可在某阶段挂载为只读：

```sh
mount -t ubifs -o ro ubi2 /opt      # 挂载即只读
mount -o remount,ro /opt            # 运行期重新挂载为只读
```
