# M57 NAND/Flash 适配指南

> 本文整理自 nand 文件系统 FAQ、linux 下 nand 及文件系统 FAQ 汇总。新增颗粒必须按目标 SDK 和板级设计重新核验。下文的 MCAL/EB 步骤是条件项；AX637/AX637R 当前 Linux 主域 + Safety/RTOS demo 路径不能仅凭仓库存在 generic MCAL 代码就认定使用这些运行时层。

## 先确认的颗粒与硬件信息

至少确认：

- JEDEC ID、厂商和型号；
- page size、erase/block size、总容量和 OOB layout；
- 支持的接口线数、SDR/DDR/DTR 能力和 dummy cycle；
- ECC 能力、要求和坏块标记位置；
- quad-enable、feature register、读写/擦除命令序列；
- 控制器频率、采样延迟、CS、供电和板级连接。

不能只依据容量或 JEDEC ID 判断兼容性。新板旧颗粒先排查虚焊、供电、电平、走线、CS 和时序；降频后恢复时重点检查采样延迟和信号质量。

## 启动链分层适配

按启动阶段逐层检查，不要只修改 Linux：

1. **Romcode/SBL**：在 `build/scripts/flash_config/` 增加或核对颗粒 YAML，检查目标 `config.mk` 是否选择正确；必要时核对 `sbl_opt_param`。
2. **MCAL FLS**：NAND 场景检查 `SafetyIsland/mcal/mcal_drv/Fls/`，包括 `Spi_Nand.c`、颗粒表、geometry、ECC 和命令序列。若颗粒不在 Flash list，需按 SDK 支持流程引入，不能自行假定枚举值。
3. **SPL/U-Boot**：检查目标 DTS 的 OSPI `nand0` 节点，以及 `boot/uboot/u-boot-2022.10/drivers/mtd/nand/spi/` 中的厂商表、ID、geometry 和器件钩子。
4. **Linux kernel**：检查 `kernel/linux/linux-6.1.83/arch/arm64/boot/dts/axera/` 的 `spi_nand0` 节点，以及 `kernel/linux/linux-6.1.83/drivers/mtd/nand/spi/` 的器件表和钩子。
5. **MCAL EB**：若产品链路使用 EB，核对 xdm、FLS 模板和 `OSPI_FlashChip` 枚举；枚举顺序必须与 `spi_nand_ids` 顺序保持一致。

- 当前 checkout 的 M57 `common.c`/`mtdparts.c` 会根据启动介质和 metadata 读取、筛选或生成 `mtdparts`，因此分区核对不能只看 Linux DTS；还必须检查 `main_bootmode`、`main_mtd`、`safe_mtd`、mtdparts metadata 和运行时布局。


按最早出现的错误分类：

- 读 ID/读页失败：先查硬件连接、频率、采样、命令序列和颗粒表；
- 数据校验失败：核对 ECC、OOB、镜像版本、压缩选项和读时序；
- 镜像解析或后续挂载失败：核对分区边界、镜像类型、元数据和文件系统，而不要继续盲目调 scan；
- AXDL/FDL 烧录失败：确认 FDL/工具是否含颗粒适配、烧录包是否属于当前 `PLAT`、分区和 geometry 是否一致，并保留完整日志。

新板新颗粒应同时对照 demo 板：demo 正常而客户板失败时优先比较硬件和时序；两者都失败时再回到软件适配和镜像链路。

## 验证边界

适配完成后应分别验证：Flash ID、原始页读写、擦除、ECC/坏块处理、SBL/SPL/U-Boot 启动、目标 Linux 设备枚举、文件系统挂载、烧录回读和冷启动。若目标确实包含 QNX 或 MCAL FLS，再增加对应设备层验证；单次 scan 或单次吞吐不能证明适配完成。

## 来源

- nand 文件系统 FAQ。
- linux 下 nand 及文件系统 FAQ 汇总。
