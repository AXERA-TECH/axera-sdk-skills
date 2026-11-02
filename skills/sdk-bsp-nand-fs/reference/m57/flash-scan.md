# M57 Flash scan 指南

> 本文整理自 M57 flash scan 功能使用指南。命令、Kconfig 和频率必须以目标 SDK revision、board 和实际控制器配置为准。

## 适用边界

Flash scan 用于在目标控制器频率和采样延迟组合中寻找稳定的读数据窗口，主要服务于 OSPI/QSPI NAND/NOR 的读路径调参。scan 结果不能替代硬件连接、Flash ID、geometry、ECC 或坏块策略的确认，也不能直接证明整条启动链已经适配。

## 启用与入口

- U-Boot 源码在 `cmd/Kconfig` 定义 `CONFIG_SPI_RX_SAMPLE_DLY_SCAN`，并在 `cmd/mtd.c` 实现 `mtd scan`；目标镜像是否提供该命令仍须核对最终生成 `.config`，不能只凭源码存在下结论。
- 以目标 U-Boot 的 `mtd scan` 帮助为准。当前源码形式为：

```text
mtd scan <name> [off] [freq] [mode]
```

- `<name>` 必须使用目标板实际注册的 MTD/Flash 名称；`off`、`freq` 和 `mode` 的单位与可选值以当前 U-Boot 实现为准。
- 测试偏移应避开 boot、metadata、分区表和有效镜像区域，优先使用可重复读取且允许只读访问的区域。

## 推荐流程

1. 收集 board、`PLAT`、SDK revision、Flash ID、page/erase geometry、当前总线频率、采样模式和完整串口日志。
2. 先用较低频率确认 Flash 可稳定识别和读取，排除供电、CS、走线、ID 表和基本命令序列问题。
3. 将 scan 的频率设置为与实际使用阶段一致；不能用低频 scan 的成功结果直接覆盖 SBL/U-Boot/Linux 的高频配置。
4. 在多个采样延迟点执行重复读取，记录成功/失败窗口、频率、mode、偏移和数据校验结果。
5. 从连续稳定窗口中选择中间值，而不是选择窗口边界；将结果回填到目标 DTS、U-Boot 或平台配置的对应采样参数。
6. 重新验证冷启动、热启动、连续读取、跨页读取、擦除后读取和完整镜像链路，并保存原始日志。

## 采样模式注意事项

- 需要区分控制器内部采样延迟与外部 DQS/数据选通采样；两者不能仅凭参数名称互相替代。
- 四线 NAND 的线数不等于 DDR/DTR；常规四线 SDR 使用单边沿采样，是否支持 DTR 由控制器和颗粒能力共同决定。
- scan 窗口随板级走线、Flash 颗粒、供电、频率和温度变化；demo 板结果不能直接套用到客户板。
- 若降频后恢复，应优先检查 `rx_sample_delay`、时序和硬件信号质量，而不是先扩大分区或修改文件系统。

## 证据与验收

至少保留：

- scan 前后的控制器配置差异；
- 完整 scan 输出及重复次数；
- 实际阶段频率、mode、offset 和采样参数；
- Flash ID、geometry、ECC/坏块信息；
- 冷/热启动和连续读验证结果。

scan 成功窗口只说明指定条件下的读采样稳定性。若仍有启动失败，应按最早错误继续区分 NAND 读失败、校验失败、镜像解析失败和后续挂载失败。

## 来源与限制

- M57 flash scan 功能使用指南。
- 来源源码：`boot/uboot/u-boot-2022.10/cmd/Kconfig`、`boot/uboot/u-boot-2022.10/cmd/mtd.c`；具体频率、DTS 属性、命令参数和目标配置仍需结合目标 board 核对。
