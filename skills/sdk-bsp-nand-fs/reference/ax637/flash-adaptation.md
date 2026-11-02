# AX637/AX637R NAND/Flash 适配指南

> 本文整理自 nand 文件系统 FAQ、linux 下 nand 及文件系统 FAQ 汇总。新增颗粒必须按目标 SDK 和板级设计重新核验。本平台文档只保留当前 AX637/AX637R 适用的 SBL、U-Boot 与 Linux 路径，不包含 QNX、virtual flash 或 MCAL/EB FLS 流程。

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

1. **Romcode/SBL**：在 `build/scripts/flash_config/` 核对颗粒 YAML、目标 `config.mk` 和必要的 `sbl_opt_param`。
2. **SPL/U-Boot**：检查目标 DTS 的 OSPI `nand0` 节点，以及 `boot/uboot/u-boot-2022.10/drivers/mtd/nand/spi/` 中的厂商表、ID、geometry 和器件钩子。
3. **Linux kernel**：检查目标 Linux DTS 的 `spi_nand0` 节点，以及 `kernel/linux/linux-6.1.83/drivers/mtd/nand/spi/` 的器件表和钩子。
4. **Safety/RTOS 启动链**：仅在目标 AX637/AX637R 构建实际引用时，核对相关启动和 Flash 适配配置；不要把 generic MCAL/EB 代码当作当前平台 active route。

## 启动与烧录故障定位

按最早出现的错误分类：

- 读 ID/读页失败：先查硬件连接、频率、采样、命令序列和颗粒表；
- 数据校验失败：核对 ECC、OOB、镜像版本、压缩选项和读时序；
- 镜像解析或后续挂载失败：核对分区边界、镜像类型、元数据和文件系统，而不要继续盲目调 scan；
- AXDL/FDL 烧录失败：确认 FDL/工具是否含颗粒适配、烧录包是否属于当前 `PLAT`、分区和 geometry 是否一致，并保留完整日志。

新板新颗粒应同时对照 demo 板：demo 正常而客户板失败时优先比较硬件和时序；两者都失败时再回到软件适配和镜像链路。

## 验证边界

适配完成后应分别验证：Flash ID、原始页读写、擦除、ECC/坏块处理、SBL/SPL/U-Boot 启动、Linux 设备枚举、文件系统挂载、烧录回读和冷启动。单次 scan 或单次吞吐不能证明适配完成。

## 来源

- nand 文件系统 FAQ。
- linux 下 nand 及文件系统 FAQ 汇总。
