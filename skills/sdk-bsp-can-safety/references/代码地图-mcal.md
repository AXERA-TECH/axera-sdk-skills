# M57 MCAL CAN 代码与文档索引

以下路径已在当前 M57 工作区核对存在。

| 内容 | 路径 |
|---|---|
| CAN API | `SafetyIsland/mcal/mcal_drv/Can/inc/Can.h` |
| CAN Driver 实现 | `SafetyIsland/mcal/mcal_drv/Can/src/Can.c` |
| FlexCAN 接口与实现 | `SafetyIsland/mcal/mcal_drv/Can/inc/Can_Flexcan.h`、`SafetyIsland/mcal/mcal_drv/Can/src/Can_Flexcan.c` |
| IRQ 实现 | `SafetyIsland/mcal/mcal_drv/Can/src/Can_Irq.c` |
| CanIf callback | `SafetyIsland/mcal/mcal_drv/CanIf/inc/CanIf_Cbk.h`、`SafetyIsland/mcal/mcal_drv/CanIf/src/CanIf_Cbk.c` |
| TJA1145 收发器 | `SafetyIsland/mcal/mcal_drv/CanTrcv_TJA1145/` |
| EB 插件定义与生成器 | `SafetyIsland/mcal/plugins/Can/config/Can.xdm`、`SafetyIsland/mcal/plugins/Can/generate/` |
| 当前生成配置 | `SafetyIsland/mcal/mcal_config/generated/include/Can_Cfg.h`、`SafetyIsland/mcal/mcal_config/generated/src/Can_Cfg.c`、`SafetyIsland/mcal/mcal_config/generated/src/Can_PBcfg.c` |
| 示例 | `SafetyIsland/mcal/mcal_example/examples/Demo/Can_Demo.c` |
| 用户手册 | `SafetyIsland/mcal/plugins/Can/Doc/AXERA-M57 MCAL CAN UM.docx` |
| EB 配置补充说明 | `references/M57 MCAL CAN EB 配置说明.md` |

当前源码可直接核对的接口包括：

- `Can_Init()`、`Can_DeInit()`、`Can_SetControllerMode()`、`Can_Write()`
- `Can_GetControllerErrorState()`、`Can_GetControllerTxErrorCounter()`、`Can_GetControllerRxErrorCounter()`
- `Can_MainFunction_Read()`、`Can_MainFunction_Write()`、`Can_MainFunction_BusOff()`、`Can_MainFunction_Mode()`
- `CanIf_TxConfirmation()`、`CanIf_RxIndication()`、`CanIf_ControllerBusOff()`

目标项目行为应以其实际使用的生成配置和源码版本为准。

## FAQ 核对矩阵

FAQ 给出排查建议，下面的路径用于核对当前 SDK 实现。样例生成配置只能证明字段和生成结果存在，不能代表客户目标工程取值。

### 1. CAN Bus-Off

| 核对项 | 配置/API | 实现位置 | 最低证据 |
|---|---|---|---|
| 处理模式 | `CanBusoffProcessing`；`CAN_BUSOFFPOLL_SUPPORTED`、`CAN_BUSOFFINT_SUPPORTED` | `plugins/Can/config/Can.xdm`、生成的 `Can_Cfg.h` | 目标 controller 的 EB 配置和目标生成文件 |
| 自动恢复 | `CanAutoBusOffRecovery` | `Can.xdm`、生成器 `generate/src/Can_Cfg.c`、目标 `Can_Cfg.c` | 目标 controller 的配置值和生成结果 |
| polling 路径 | `Can_MainFunction_BusOff()` | `mcal_drv/Can/src/Can.c` | 周期调用证据与 `CanIf_ControllerBusOff()` 是否触发 |
| interrupt 路径 | `CanIf_ControllerBusOff()` | `mcal_drv/Can/src/Can_Irq.c`、`mcal_drv/CanIf/src/CanIf_Cbk.c` | controller ID、首次回调时间和调用上下文 |
| 错误状态 | `Can_GetControllerErrorState()`、`Can_GetControllerTxErrorCounter()`、`Can_GetControllerRxErrorCounter()` | `mcal_drv/Can/inc/Can.h`、`src/Can.c` | Bus-Off 前后状态及 TX/RX error counter |

### 2. CAN 中断处理时间过长

| 核对项 | 配置/API | 实现位置 | 最低证据 |
|---|---|---|---|
| IRQ 入口 | controller 对应的 IRQ handler | `mcal_drv/Can/src/Can_Irq.c` | controller、IRQ 名称及进入频率 |
| 上层回调 | `CanIf_TxConfirmation()`、`CanIf_RxIndication()`、`CanIf_ControllerBusOff()` | `mcal_drv/CanIf/src/CanIf_Cbk.c` | 回调内实际执行内容及耗时测量 |
| 处理方式 | TX/RX/Bus-Off 的 polling 或 interrupt 配置 | `Can.xdm`、目标 `Can_Cfg.h` 和 `Can_PBcfg.c` | 目标 controller 的实际生成值 |
| 影响范围 | TX/RX/overflow 计数与时间戳 | 现场取证 | 同一时间轴上的 IRQ、回调和丢帧/overflow 现象 |

### 3. CAN TX 失败

| 核对项 | 配置/API | 实现位置 | 最低证据 |
|---|---|---|---|
| 请求是否接收 | `Can_Write()` 返回 `E_OK`、`E_NOT_OK` 或 `CAN_BUSY` | `mcal_drv/Can/src/Can.c` | HTH、返回值、调用频率；`CAN_BUSY` 只说明发送硬件对象繁忙或同 HTH 不可重入等实现条件 |
| 发送完成 | `CanIf_TxConfirmation()` | `mcal_drv/CanIf/src/CanIf_Cbk.c` | 对应 PDU 的 confirmation 计数或时间戳 |
| HTH/邮箱配置 | TX hardware object 和 multiplex 配置 | 目标 `Can_PBcfg.c` | HTH 到 controller/MB 的生成映射 |
| CAN FD 模式 | `CanControllerFdISO`；`CAN_CONTROLLER_FD_ISO_CANFD` | `Can.xdm`、目标 `Can_Cfg.h` | 通信两端的 ISO/non-ISO 实际配置 |
| 总线状态 | error state、TX/RX error counter | `Can.h`、`Can.c` | API 结果以及总线分析仪的 ACK/协议错误证据 |

### 4. RX Enhanced FIFO 丢帧

| 核对项 | 配置/API | 实现位置 | 最低证据 |
|---|---|---|---|
| FIFO 类型 | `CanRxFiFo` / `CanEnhanceFiFo`；`CAN_ENHANCE_FIFO_ENABLE` | `Can.xdm`、目标 `Can_Cfg.h` | 目标 controller/HRH 的生成配置 |
| overflow 通知 | `CanFiFoOverflowNotif`；`Can_pEnhanceFiFoOvfNotif` | `Can.xdm`、`Can.h`、目标 `Can_PBcfg.c` | callback 是否配置、是否触发及累计次数 |
| DMA 与 watermark | `CanEnhanceFiFoDmaEnable` 和生成的 Enhanced FIFO 参数 | `Can.xdm`、目标 `Can_Cfg.h`/`Can_Cfg.c` | 目标 controller 的实际生成值 |
| 接收上报 | `CanIf_RxIndication()` | `mcal_drv/CanIf/src/CanIf_Cbk.c` | 硬件/FIFO、CanIf、应用三层接收计数 |
| 时序关联 | IRQ/回调时间戳、总线报文时间线 | 现场取证 | overflow 首次发生前后的总线负载和接收计数 |

## EB 配置核对矩阵

本节用于路由 [M57 MCAL CAN EB 配置说明](M57%20MCAL%20CAN%20EB%20配置说明.md)中的 5 类信息。文档中的配置规则和工程建议应保留来源标签；目标项目取值以实际 EB 工程和生成文件为准。

| 文档章节 | 文档说明 | 当前 SDK 核对入口 | 目标工程需要提供 |
|---|---|---|---|
| 1. CAN MB 数量说明 | 每个通道的 RAM block、payload size 与 MB 数量关系；8-byte payload 时最多 96 MB | 用户手册“硬件特性”；`Reg_eSys_FlexCan.h` 的 `MBDSR0/1/2` 和 payload 定义；`generate/src/Can_PBcfg.c` 的 `CanRamBlock` 生成逻辑 | controller 的各 RAM block payload 配置、hardware object 数量及目标 `Can_PBcfg.c` |
| 2. CAN RX MB / Enhance FIFO | RX MB 与 Enhanced FIFO 的使用约束、FIFO depth 及推荐模式 | `Can.xdm` 的 `CanRxFiFo`；生成的 `CAN_*_ENHANCE_FIFO_EN`；目标 `Can_PBcfg.c` 的 MB/FIFO 映射 | controller 的 RX 模式、HRH 配置、目标生成值和实际接收负载 |
| 3. CAN FD 采样点说明 | normal CBT 与 extended CBT 的选择及 Tq 范围差异 | `Can.xdm` 的 `CanControllerPropSeg`、`CanControllerSeg1`、`CanControllerSeg2`、`CanControllerSyncJumpWidth`；用户手册 bit timing 章节 | nominal/data phase bit timing、时钟和目标采样点 |
| 4. CAN RX 过滤说明 | Standard、Extended、Mixed 过滤；Mixed 顺序和 Standard filter 偶数规则 | `Can.xdm` 的 `CanIdType`、`CanHwFilter`、`CanHwFilterCode`、`CanHwFilterMask`；目标 `Can_PBcfg.c` filter table | 按 EB 顺序导出的完整 filter 列表、ID type、code 和 mask |
| 5. CAN RX DMA 说明 | DMA 仅用于 Enhanced FIFO；文档基于硬件限制给出高 busload 下不建议开启的工程建议 | `Can.xdm` 的 `CanEnhanceFiFoDmaEnable`；生成的 `CAN_*_ERFIFO_DMA_ENABLE`、`FLEXCAN_DMA_ENABLE`；用户手册 DMA 章节 | DMA 开关、watermark、busload、overflow/丢帧计数和 DMA IRQ 时间线 |

对“推荐”“不建议”等工程判断，回答时注明来自 EB 配置说明；只有目标版本实测或缺陷记录才能把它写成目标项目结论。
