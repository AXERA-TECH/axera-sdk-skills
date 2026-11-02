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

### 4.2.1 Linux内存大小调整

以ax637_demo_only_nand平台为例，修改

kernel/linux/linux-6.1.83/arch/arm64/boot/dts/axera/ax637-demo-only-nand.dts里面memory节点。

默认情况下，系统内存大小是384 MiB（0x18000000），前者为内存空间的起始地址，后者是内存空间的大小，将后者修改为您期望的值即可。

### 4.2.2 CMM内存地址和大小调整

以ax637_demo_only_nand平台为例，在build/scripts/init_scripts/load_modules.sh里面修改，重新编译打包rootfs.img，通过AXDL烧写到板端。

修改配置后，可在板端查看/usr/bin/load_modules.sh文件，确认文件是否包含如下这行修改：

insmod /opt/ko/ax_cmm.ko cmmpool=anonymous,0,0x118000000,640M

如果需要在板端直接修改CMM配置，也可以通过vi来修改该文件来实现（只读文件系统除外）。

## 4.3 FLASH存储空间的分配

以AX637R DEMO板 ax637r_demo_only_nand board中AB分区的ONLY_NAND空间为例：

flash上的分区是从0偏移地址紧密外后排布的：

分区排布的顺序看partitions.json文件的分区先后关系，唯一需要确认的是每个分区的对应的size大小。

这个从build/platforms/axera/ax637r_demo_only_nand/partitions.json文件中获取。

## 4.4 调整分区大小

本节以ax637_demo_only_nand为例说明分区大小的调整方法及一些约束点。

进入build/platforms/axera/ax637_demo_only_nand/partitions_without_ab.json配置文件，调整配置文件中的各分区对应的Size。

该文件中的配置经过脚本解析，组成mtdparts格式字符串。通过axdl工具将该信息写入metadata分区。uboot启动后会从该分区读取分区信息。

保存在Nand上的mtdparts格式(格式示例如下)：

768K(sbl),768K(metadata),768K(metadata_bak),1024K(spl),4096K(rtos),768K(ubootenv),768K(ubootenv_bak),4096K(uboot),768K(atf),2048K(optee),30720K(kernel) bootable,153600K(rootfs),102400K(userdata)

除了紫色是我们自定义字段，这些自定义字段不允许传递给后一级（RTOS、Linux），其他都是符合标准Linux kernel里面的定义。

partitions.json配置文件分区size单位是KB。需要注意size应保证是block size的整数倍。如SDK，NAND上所有分区大小应256K（W25N04LW）的整数倍。

分区大小调整约束：

1、对于nand场景，由于nand颗粒本身坏块特性（出厂坏块或使用坏块），SDK展示的分区配置文件默认已为各分区预留足够block用作跳坏块(满足生命周期内10ppm不良率要求)，若客户为了极致裁剪分区大小不在乎使用坏块，那么也必须预留block（因为还要考虑出厂坏块的颗粒特性）。

2、对于nand场景，不像emmc场景 hsm是没有专门的分区的，hsm镜像是附在sbl镜像后面作为256K sbl镜像输出的(前128K是sbl后128K是hsm)，这是受限于Romcode对sbl及hsm的引导导致，因此对于sbl分区中实际sbl镜像占的大小要用256K进行考虑。

3、对于AB场景下，SBL分区大小无论emmc情况还是nand情况必须用SDK默认展示的（nand 768k, emmc 128K），原因是RomCode找B分区的偏移就是按这个大小来的。

Nand场景下若客户实在不考虑使用坏块，对于前面几个关键启动分区，可考虑的大小优化：

1、sbl分区大小优化（如前说明 只支持非AB下）

若block256：分区可改512K（保证至少留1block）

若block128：分区可改384K（注意：不能改256K，如前说明 要考虑hsm的附加）

2、metadata/metadata_bak分区大小优化

若block256：分区可都改256K（若metadata分区出厂坏块，有metadata_bak在，还能用bak）

若block128：分区可都改128K

不建议删掉metadata_bak，因为删了后metadata分区还要多预留1block，总体size没优化。

注： 其中sbl/metadata/medata_bak的大小SDK默认不开放也不建议修改，若真要为了Size优化不考虑使用坏块要来改，除了修改partition文件，还要修改如下2块地方

uboot配置: menuconfig 搜2配置

LUA_SBL_SIZE_IN_NANDFLASH   LUA_METADATA_SIZE_IN_NANDFLASH

sbl配置：sbl_demo.h 2配置

3、misc/misc_bak分区大小优化（只在AB场景下需要misc分区，SDK默认放AB管理信息)

这两个分区的大小优化策略同上面的 metadata/metadata_bak

## 4.5 新建或删除分区

- 分区表中sbl* ~ rtos* 分区为MCU侧使用及引导镜像，默认不支持直接在中间增删分区。

- 注1：only_nand下分区表信息在metadata分区，uboot axdl烧录阶段写入

- 注2：only_emmc下分区表信息在offset=0开始1M gpt空间，因此sbl分区从1M地址起

- 分区表中misc*/ubootenv* ~ 开始及往后的分区为Acore侧使用及引导的镜像，这些分区的偏移关系就是分区前后的相对关系，Acore这些分区支持在里面增删自己的自定义分区。比如若要新增test1纯数据分区，除了partitions.json配置文件里新增分区，还需对boot/uboot/u-boot-2022.10/board/axera/common/m57/common.c下的白名单数组main_part_id[]增加test1，若客户有多个PLAT工程可将一共会多出现的分区名一次性填到该数组即可。

/* Supported partition identifier for Main A55 */

const char *main_part_id[] = {

"misc",

"ubootenv",

"atf",

"optee",

"uboot",

"boot",

"kernel",

"rootfs",

"misc_bak",

"ubootenv_bak",

"atf_a",

"atf_b",

"optee_a",

"optee_b",

"uboot_a",

"uboot_b",

"boot_a",

"boot_b",

"kernel_a",

"kernel_b",

"rootfs_a",

"rootfs_b",

"userdata",

"test1",

"test2",

"test3",

"test4",

};

- 比如若要新增test1镜像分区，除了前面说的了partitions.json配置文件及白名单数组main_part_id[修改，还需对axp打包脚本进行修改（目的是将客户自己的镜像打到axp里去，若客户不用我们的axp打包逻辑自然也不用管这步骤），若客户有多个PLAT工程可将一共会多出现的新增镜像的路径一次性填到里面即可。

diff --git a/scripts/axp_make.sh b/scripts/axp_make.sh

index bcfdb895..5a750e9d 100755

--- a/scripts/axp_make.sh

+++ b/scripts/axp_make.sh

@@ -390,6 +390,12 @@ initialize_project_specific_paths() {

RTOS_A_PATH=$SAFE_IMG_PATH/CameraDemo_enc_signed.img

RTOS_B_PATH=$SAFE_IMG_PATH/CameraDemo_enc_signed.img

fi

+        if [ "$PROJECT" = "客户工程PLAT名1" ] || [ "$PROJECT" = "客户工程PLAT名2 " ]; then

+            TEST1_PATH=$HOME_PATH/build/platforms/axera/$PROJECT/test1.img

+            TEST2_PATH=$HOME_PATH/build/platforms/axera/$PROJECT/test2.img

+            TEST3_PATH=$HOME_PATH/build/platforms/axera/$PROJECT/test3.img

+            TEST4_PATH=$HOME_PATH/build/platforms/axera/$PROJECT/test4.img

+        fi
