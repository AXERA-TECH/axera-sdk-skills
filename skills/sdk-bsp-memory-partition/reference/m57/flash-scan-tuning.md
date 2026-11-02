# M57 flash scan功能使用指南

**背景：** 随着 flash 频率提高，以及双边沿数据采样，且不同板子线传输延迟的差异，及温漂等影响，需要采样点设置更加准确，确保有足够的余量，能够抵消这些影响。这时需要使用 flash scan 工具分析出最优的采样点信息。

**环境：** flash scan 功能是基于 uboot 命令行开发的。直接更换带有 flash scan 功能的镜像执行 flash scan 采样点扫描即可（以 demo_nor_nand 工程为例）。

## 1. 开启 flash scan 功能

flash scan 功能在 uboot 下默认是不开启的，开启该功能需要打开 `CONFIG_SPI_RX_SAMPLE_DLY_SCAN`。

在 uboot 的 menuconfig（U-Boot 2022.10 Configuration）中，进入 `mtd` 子菜单即可看到 `flash scan` 选项，通过 `<Select>` 勾选它（对应宏 `CONFIG_SPI_RX_SAMPLE_DLY_SCAN`）。该开关最终体现在 `configs/m57h-demo-nor-nand_defconfig` 中新增一行 `CONFIG_SPI_RX_SAMPLE_DLY_SCAN=y`，可用 `git diff` 查看改动。

选中后，保存配置。可以看到 `CONFIG_SPI_RX_SAMPLE_DLY_SCAN` 被开启，再编译 uboot 镜像。

## 2. 板子更新 uboot 镜像

板子更新完 uboot 镜像后重启设备，进入 uboot 命令行敲 `mtd` 命令可以查看到 `mtd scan` 命令。

`mtd` 的帮助信息中列出了各子命令（`mtd list`、`mtd read`、`mtd erase`、`mtd dump`、`mtd scan` 等）及参数说明，其中 scan 的用法为：

```text
mtd scan <name> [<off> [<freq>] [<mode>]]
```

## 3. scan 命令介绍

- `name`：即为需要 scan 的 flash 设备，设备名可以通过 `mtd list` 获取，如下设备名为 `nand0`。
  - `mtd list` 会列出所有 MTD 设备，例如 `nand0`：`device: spi-nand@0`、`parent: ospi@0C040000`、`driver: spi_nand`、`type: NAND flash`、`block size: 0x40000 bytes`、`min I/O: 0x1000 bytes`、`OOB size: 128 bytes`、`OOB available: 80 bytes`，并列出各分区（`misc`、`ubootenv`/`ubootenv_bak`、`uboot_a/b`、`atf_a/b`、`optee_a/b`、`kernel_a/b`、`rootfs_a/b`、`userdata` 等）及其地址范围。
- `off`：为 flash scan 的偏移地址，该参数可以不设置，不设置默认 0 偏移地址测试；该地址尽量避开镜像区域，避免破坏镜像。如果不小心破坏导致设备起不来，可以重新刷镜像。一般建议用 userdata 区域地址。
- `freq`：为 flash scan 时的频率，该参数可以不设置，不设置默认 50M。注意 help 描述，这里的频率单位是 Hz，如果想测试 nand0 设备在 100M 频率下的采样情况，`freq` 设置为 100000000。
- `mode`：为 flash 的采样模式，该参数可以不设置，不设置默认采用内部时钟采样。目前 flash RX 采样分为内部时钟采样和外部 dqs 信号采样，如果要采样外部 dqs 采样，需要设置为 1；如果 flash 颗粒 qds 信号 clk 极性相反，则设置为 2。（如果是四线 nand，一般不涉及这些，该参数不设置）

> 什么时候用外部 qds 采样：外部 qds 采样一般是 flash 频率设置比较高且 ddr 模式时。目前 ip 设计是：在 flash io 模式为 ddr 模式、50M 及以下，使用内部采样即可；如果超过 50M，需要用外部 qds 采样。

### 命令举例

**使用内部采样：**

```sh
mtd scan nand0 0x19800000 50000000 0    # 0x19800000 为 userdata 区域内的地址空间
```

通过 log 可以发现 delay 从 0-5 都是可以采样成功的，那我们可以选择中间值 3 作为最终 flash 的最佳采样参数，将该参数更新到 uboot 和 kernel 的 dts 中即可。

**100M qds 采样：**

```sh
mtd scan nand0 0x19800000 100000000 1
```

通过 log 可以发现 delay 从 0-50 都是可以采样成功的，那我们可以选择中间值 25 作为最终 flash 的最佳采样参数，将该参数更新到 uboot 和 kernel 的 dts 中即可。

### 更新 uboot/kernel 下 dts 参数

**50M 内部采样（uboot）：**

```dts
&ospi {
    status = "okay";
    /* for W35N01 */
    nand0: spi-nand@0 {
        compatible = "spi-nand";
        reg = <0>;
        spi-tx-bus-width = <8>;
        spi-rx-bus-width = <8>;
        //spi-rx-sample-nedge; /* Negative edge sampling */
        spi-rx-sample-delays = <3>;        /* 修改采样参数 */
        spi-rxdqs-sample-delays = <31>;
        spi-max-frequency = <50000000>;    /* 修改 50M 频率 */
        // spi-dqs;                        /* 使用内部采样 */
        // spi-dqs-revert;
        // spi-cpha;
        // spi-cpol;
        spi-cmd-flip;
        spi-data-flip;
        u-boot,dm-pre-reloc;
        u-boot,dm-spl;
        status = "okay";
    };
};
```

**100M qds 采样（uboot）：**

```dts
&ospi {
    status = "okay";
    /* for W35N01 */
    nand0: spi-nand@0 {
        compatible = "spi-nand";
        reg = <0>;
        spi-tx-bus-width = <8>;
        spi-rx-bus-width = <8>;
        //spi-rx-sample-nedge; /* Negative edge sampling */
        spi-rx-sample-delays = <3>;
        spi-rxdqs-sample-delays = <25>;    /* 修改采样参数 */
        spi-max-frequency = <100000000>;   /* 修改 100M 频率 */
        spi-dqs;                           /* 使用 dqs 采样 */
        spi-dqs-revert;                    /* w35n04 qds 极性相反 */
        // spi-cpha;
        // spi-cpol;
        spi-cmd-flip;
        spi-data-flip;
        u-boot,dm-pre-reloc;
        u-boot,dm-spl;
        status = "okay";
    };
};
```

**50M 内部采样（kernel）：**

```dts
&ospi {
    status = "okay";
    spi_nand@0 {
        #address-cells = <1>;
        #size-cells = <1>;
        compatible = "spi-nand";
        reg = <0>;
        rx-sample-delays = <3>;            /* 修改采样参数 */
        rxdqs-sample-delays = <31>;
        spi-max-frequency = <50000000>;    /* 修改 50M 频率 */
        spi-tx-bus-width = <8>;
        spi-rx-bus-width = <8>;
        // spi-dqs;                        /* 使用内部采样 */
        // spi-dqs-revert;
        spi-cmd-flip;
        spi-data-flip;
        status = "okay";
    };
};
```

**100M qds 采样（kernel）：**

```dts
&ospi {
    status = "okay";
    spi_nand@0 {
        #address-cells = <1>;
        #size-cells = <1>;
        compatible = "spi-nand";
        reg = <0>;
        rx-sample-delays = <3>;
        rxdqs-sample-delays = <25>;        /* 修改采样参数 */
        spi-max-frequency = <100000000>;   /* 修改 100M 频率 */
        spi-tx-bus-width = <8>;
        spi-rx-bus-width = <8>;
        spi-dqs;                           /* 使用 dqs 采样 */
        spi-dqs-revert;                    /* w35n04 qds 极性相反 */
        spi-cmd-flip;
        spi-data-flip;
        status = "okay";
    };
};
```

如果扫描出的参数给 romcode 使用，需要注意 uboot 中 flash 的频点要保持和 romcode 一致。目前 romcode 的频点是固定在 400M。（现在 uboot 快启，在 uboot 下重定向前不走 clk 驱动框架，用的第 102 行频率设置频点；重定向后，会走 clk 驱动框架，会用第 93 行设置频点，所以都要设置一下。）

对应的 dts 片段中还包含时钟配置：`&flash_cru` 下通过 `assigned-clocks = <&flash_clk_mux CLK_FLASH_OSPI>`、`assigned-clock-parents = <&flash_pll_400m>` 指定 flash 时钟源为 400M，并且 `&ospi` 节点中相应地把 `spi-max-frequency` 设为 `<400000000>`，即上面所说给 romcode 使用的 400M 频点。

**u-boot.img（nor+nand 工程）**

一般频率较低，或者单板差异不大时，使用目前源码推荐的参数即可。

> 注意：uboot 下 dts 里面的频率可以设置低一点，确保 uboot 下默认的 `spi-rx-sample-delays=3`，flash 驱动能起来。如果是想扫描单线模式下指定频率的 `spi-rx-sample-delays`，对应 `spi-tx-bus-width`/`spi-rx-bus-width` 设置为 1。
