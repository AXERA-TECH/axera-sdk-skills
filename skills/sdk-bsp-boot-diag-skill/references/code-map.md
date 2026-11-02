# AX615 启动代码地图

以下路径相对于用户提供的 SDK 工作区根目录；行号应在实际版本中重新确认。不要假定 SDK 位于固定绝对路径。

内核基线：`kernel/linux/linux-4.19.125`。启动诊断只将工作区当前文件、实际构建 commit 和用户镜像作为证据，不以文件名相似的其他版本替代。

| 阶段 | 文件 | 可确认行为 | 关键日志/证据 |
|---|---|---|---|
| BL1 串口输出 | `boot/bl1/common/include/printf.h` | `DEBUG` 控制 `info`、`debug`、`printf` | 宏值、实际镜像是否重编 |
| BL1 启动入口 | `boot/bl1/spl/spl_main.c` | 初始化、DDR、镜像加载、跳转下一阶段 | `init_sequence_f[...]`, `ddr init fail` |
| 启动介质识别 | `boot/bl1/spl/spl_main.c` | 由 chip mode 设置 `boot_info` | `The system boot from SD/eMMC/NOR/NAND` |
| 芯片/DDR 类型 | `boot/bl1/board/board.c` | 从 efuse 读取并写入 `iram_misc_info` | 实际打印或寄存器读取结果 |
| 下载启动 | `boot/bl1/fdl/fdl_main.c` | 初始化 chip/pinmux/UART/DDR 后进入 FDL | `enter download mode` |
| 镜像读取 | `boot/bl1/spl/spl_main.c` | loader init、逐镜像 read、post-load | `flash:* init failed`, `* image load failed` |
| DTB/bootargs | `boot/bl1/spl/spl_main.c` | `copy_dtb_img`、`update_fdt_bootargs` | `copy_dtb_img failed`, post-load 返回值 |
| 启动回退 | `boot/bl1/spl/spl_main.c` | `BOOT_KERNEL_FAIL` 计数，三次后进入 U-Boot/恢复路径 | `kernel boot failed!` |
| watchdog/reset | `boot/bl1/board/board.c` | `wdt_enable`, `wdt_kick` 与 reboot 枚举 | reset reason、复位前最后日志 |

## 推荐只读命令

```bash
rg -n "DEBUG|ddr init fail|flash:.*init failed|image load failed|post-load failed|kernel boot failed|copy_dtb_img|BOOT_KERNEL_FAIL" \
  boot/bl1/common boot/bl1/board boot/bl1/spl boot/bl1/fdl
git -C boot/bl1 rev-parse HEAD
git -C boot/uboot rev-parse HEAD
git -C kernel/linux rev-parse HEAD
rg -n "spinand_check_ecc_status|eccinfo\.get_status|STATUS_ECC_MASK" \
  kernel/linux/linux-4.19.125/drivers/mtd/nand/spi
```

这些命令只能定位候选代码和版本，不能替代对实际镜像、配置宏和日志的核对。
