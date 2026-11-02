# 4 分配Memory和存储空间

## 4.1 内存空间概述

在SDK中，系统配置的默认DDR空间范围为1 GiB。

SDK的内存空间分为两段空间：

- Linux使用的最大内存空间大小是384 MiB。
- 作为大段物理连续内存管理的CMM（Contiguous Memory Model）的空间，共640MiB。

> - 说明：
> 这里仅以1 GiB DDR空间分布供参考，实际情况可能存在差异，请以实际情况为准。

启动过程中，会把镜像和数据存放到DDR中。运行过程中，也会预留一部分内存空间给ATF、OPTEE等固件专用，因此Linux Memory空间里面还需要进一步细分。

## 4.2 内存空间大小调整

如果您想调整上述Linux内存和CMM内存空间的大小，请参考下面的详细介绍。

### 4.2.1 静态配置

以demo_nor_nand平台为例，修改build/platforms/axera/demo_nor_nand/config.mk文件SYSTEM_MEMORY_SZ和LINUX_MEMORY_SZ两个配置选项：

SYSTEM_MEMORY_SZ指定的是Linux memory和CMM memory大小的总和

LINUX_MEMORY_SZ指定的是Linux memory的大小

两者相减就是CMM memory的大小

注意：如果config.mk没有这两个配置选项，请自行添加。

### 4.2.2 动态调整

以demo_nor_nand平台为例，运行到uboot命令行下，调整SYSTEM_MEMORY_SZ和LINUX_MEMORY_SZ。

注意：请根据自己业务的具体情况配置的内存大小。

### 4.2.3 Inline ECC内存配置

Inline ECC 开启跟随fusa开关，普通版本默认关闭Inline ECC，fusa版本默认开启Inline ECC。

有两段空间开启了Inline ECC，第一段是linux内核空间，不可进行配置修改，第二段是CMM ECC空间，需要跟随DDR大小进行适配修改。

**SDK代码的ECC配置为1G DDR，按照4.2.1修改DDR大小后需要同步修改ECC配置**。修改方式为

SafetyIsland/driver/ddr/ddrmc_init.h的INLINE_ECC_BLOCK_1_START 为 DDR大小 - 128M的值。

警告：DDR大小-128M/8 ~ DDR大小 这段空间是ECC code存储区域，非DDR硬件和软件不允许使用。

### 4.2.4 验证内存配置

以demo_nor_nand平台为例，在linux执行相关的命令查看。

查看cmm内存配置是否符合预期。

查看linux kernel可用的内存大小。

## 4.3 FLASH存储空间的分配

M57 DEMO板的存储设备是NOR+NAND，以demo_nor_nand board中AB分区的NOR+NAND空间为例：

NOR和NAND上的分区是从0偏移地址紧密外后排布的：

并且分区排布的顺序在代码中固化，唯一需要确认的是每个分区的对应的size大小。

这个从build/platforms/axera/demo_nor_nand/partitions.json文件中获取。

## 4.4 调整分区大小

若只需要修改分区的大小，只需要修改配置文件中对应的size即可，无需额外修改文件，其余脚本会自动适配。

进入build/platforms/axera/demo_nor_nand/partitions.json配置文件，调整配置文件中的各分区对应的Size即可。

该文件中的配置经过脚本解析，组成mtdparts格式字符串。通过axdl工具将该信息写入metadata分区。uboot启动后会从该分区读取分区信息。

保存在Safety Nor/Nand上的mtdparts格式：

**nand\*1#**0x40000(sbl_a),0x40000(sbl_b),0x80000(spl_a),0x80000(spl_b),0x80000(atf_a),0x80000(atf_b),0x80000(optee_a),0x80000(optee_b),0x200000(uboot_a),0x200000(uboot_b),0x1400000(kernel_a)**bootable**,0x1400000(kernel_b)**bootable**

除了紫色是我们自定义字段，这些自定义字段不允许传递给后一级（RTOS、Linux），其他都是符合标准Linux kernel里面的定义。

partitions.json配置文件分区size单位是KB。需要注意size应保证是erase size的整数倍。如NOR上所有分区大小应4k（GD25F64）的整数倍，NAND上所有分区大小应256K（W35N04JW）的整数倍。

## 4.5 新建或删除分区

暂不支持创建和删除分区，以免影响设备启动。
