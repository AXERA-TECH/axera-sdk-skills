# AX615 VO SDK 行为摘要（版本化，客户端核验用）

> 本文件把经**已授权源码核验**的 SDK **行为结论**转换为可用的排查/生成约束（均为当前内化版本行为）。
> **每一条行为结论均来自行为观察，不含实现路径、文件名、内部符号与源码行号**。
> 所有条目的固定版本标注：**SDK V3.14.0 实现行为，需按版本核验**。
> 客户侧核验方式一栏给出该条的现场取证手段；版本不同的客户 SDK 必须重新实测确认。

## 0. 总则

- 客户侧 API 名、错误码名、`/proc` 路径与字段、公开头文件定义名可直接引用。
- 「未文档化」≠「不稳定」：下列行为多数未写入 API 文档，属实现侧事实，排查时用于解释现象，
  向客户表述时应同时给出客户可执行的核验手段。
- 判定顺序建议：**公开头文件/文档 → 官方 sample → 本摘要行为约束 → proc/dmesg 实测**。
- **预设模式不等于免检**：公开头文件只确认**预设名与 API 语义**；预设是否真的可用（时钟是否被当前 SDK
  接受、接口/芯片能力是否满足）属实现行为，按本摘要的行为约束引用并须实机核验——不得表述为
  "天然可用""由 SDK 保证"，也不得由"头文件里有该预设名"推出"该预设在目标 SDK 上可用"。
- **证据分层**：本摘要条目用于**事实确认**（某行为是否如此）；把条目与客户现场证据（代码/返回值/proc/dmesg/复现）连成因果链才构成**根因确认**，修复建议经实机复现才算**修复验证**——**本摘要不能单独证明客户本次故障的因果**（详见 SKILL.md 第 5 步）。
- **版本差异注记**：本摘要覆盖 V3.0.0 至今（V3.14.x）。V3 系列仅三个实质差异点——Clip 仅 BT
  生效自 V3.1.0（9.2）、VSYNC 事件线程机制重构自 V3.5.0（7.3）、数字 Coax 数据裁剪修复自
  V3.11.0（9.4）；其余区间已收录记录未发现相关差异（**不构成行为保证，目标环境仍需核验**），详见 version-routing.md 第 6 节。

## 1. SendFrame2Disp：错误返回与 s32MS

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 1.1 | `AX_VO_SendFrame2Disp` 的返回码会被**用户态统一包装**：帧指针为空 → `AX_ERR_VO_NULL_PTR`；设备号越界 → `AX_ERR_VO_INVALID_DEVID`；设备未使能 → `AX_ERR_VO_DEV_OP_FAIL`；帧参数非法（格式/宽高/stride/crop/LBA）→ `AX_ERR_VO_ILLEGAL_PARAM`（原样透传）；设备句柄不可用 → `AX_ERR_VO_OPEN_FILE_FAIL` | 逐个打印返回值并转 hex 对照 [sdk-inline/ax_vo_api.h](sdk-inline/ax_vo_api.h) 错误码表 | SDK V3.14.0 实现行为，需按版本核验 |
| 1.2 | **不可假设公开 API 会直接透传队列满/超时**：底层队列满与超时在用户态被统一改写为 `AX_ERR_VO_DEV_OP_FAIL`（0x80038A80）。客户若声称收到 `AX_ERR_VO_QUEUE_FULL`/`AX_ERR_VO_TIMED_OUT`，需先确认其 SDK 版本与打印位置（是否取自内核日志） | 同时抓 `dmesg` 与 `/proc/ax_proc/vo/display_status`：`InFifoSize`/`DiscFrames` 判断是否积压，`InFps`/`OutFps` 判断送帧是否过快 | SDK V3.14.0 实现行为，需按版本核验 |
| 1.3 | `s32MS` 语义：**0 = 非阻塞**（队列满立即失败，不等待）；**正值 = 最多等待该毫秒数**；**负值（含 -1）= 阻塞直到可入队**。用户态不解释该参数，语义由内核决定 | 用同一帧源分别在 s32MS=0 与 -1 下复现，观察返回码与丢帧变化 | SDK V3.14.0 实现行为，需按版本核验 |
| 1.4 | 返回 0 **仅表示帧已入队**，不表示显示侧已读完该 buffer；入队后立即覆写同一物理 buffer 会造成花屏/撕裂 | 花屏形态固定、与送帧节奏相关时可复现；改用池内存 + 引用计数或双/三缓冲后现象消失 | SDK V3.14.0 实现行为，需按版本核验 |
| 1.5 | 输入 FIFO 深度由 `u32InFifoDepth` 控制，默认 3、范围 [1,8]；**取值 0 或 >8 不报错，静默回退为 3**（`AX_VO_GetPubAttr` 读回的是生效值 3） | `AX_VO_GetPubAttr` 读回 `u32InFifoDepth` 是否为 3；或看 proc 的 FIFO 相关字段 | SDK V3.14.0 实现行为，需按版本核验 |

## 2. SetPubAttr / Enable / Disable / Init / Deinit 状态机

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 2.1 | `AX_VO_SetPubAttr` 的合法调用状态为「Init 后未配置 / 已配置 / 已 Disable」；**Enable 成功后再次调用返回 `AX_ERR_VO_NOT_PERM`，必须先 Disable**；重复 SetPubAttr（未 Enable）允许，直接重新下发 | 按顺序打印各 API 返回码；Enable 后改配置须先 Disable | SDK V3.14.0 实现行为，需按版本核验 |
| 2.2 | `AX_VO_SetPubAttr` 在 USER 模式只校验显示宽高范围与对齐，**不校验 porch/pclk/刷新率的合法性**；时序合法性由内核判定，失败时统一返回 `AX_ERR_VO_DEV_OP_FAIL` | SetPubAttr 返回 `AX_ERR_VO_DEV_OP_FAIL` 时结合 `dmesg` 是否出现 `unsupport clk` 等内核日志区分原因 | SDK V3.14.0 实现行为，需按版本核验 |
| 2.3 | `AX_VO_Enable` **不做任何时序校验**，只检查状态（未 SetPubAttr 直接 Enable → `AX_ERR_VO_NOT_PERM`）并发下使能；重复 Enable 幂等返回 0 | 「API 全返回 0 但黑屏」时不能排除时序错误，必须看 proc 的 `ScanType/Refresh/Pclk` 并与屏规格核对 | SDK V3.14.0 实现行为，需按版本核验 |
| 2.4 | `AX_VO_Disable` 重复调用幂等；但**存在已注册的 VSYNC 回调时 Disable 直接失败**（返回 `AX_ERR_VO_DEV_OP_FAIL`），不会自动注销回调 | 退出流程顺序固定为「注销 VSYNC 回调 → Disable → Deinit」；有 dmesg/日志时可见 "vsync should be unregister" 类提示 | SDK V3.14.0 实现行为，需按版本核验 |
| 2.5 | `AX_VO_Init` 带引用计数：重复 Init 直接返回成功；`AX_VO_Deinit` 在任一设备仍处于 Enable 状态时失败（返回 `AX_ERR_VO_DEV_OP_FAIL`），要求先 Disable | 反复 Init/Deinit 的客户代码需检查是否遗漏 Disable；失败码是否为 `AX_ERR_VO_DEV_OP_FAIL` | SDK V3.14.0 实现行为，需按版本核验 |
| 2.6 | `AX_VO_Deinit` 会清空 VSYNC 回调链表并关闭设备句柄；Deinit 后再次 Init 可恢复，但**上次的 PubAttr 不会被重置**，重新 Enable 前应重新 SetPubAttr | Deinit→Init 循环后先 `AX_VO_GetPubAttr` 读回确认，再决定是否重新下发 | SDK V3.14.0 实现行为，需按版本核验 |
| 2.7 | 未 Init 就调用其他 API：SetPubAttr/SetCSC/Enable/Disable/SetAspectRatio → `AX_ERR_VO_NOT_PERM`；SendFrame2Disp → `AX_ERR_VO_DEV_OP_FAIL`；DataPinMap/Coax/Clip 类只判句柄 → `AX_ERR_VO_OPEN_FILE_FAIL` | 客户报「参数没问题但一直报错」时先确认 Init/Deinit 配对 | SDK V3.14.0 实现行为，需按版本核验 |

## 3. GetPubAttr 的特殊行为

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 3.1 | Init 后**未 SetPubAttr** 时 `AX_VO_GetPubAttr` 返回 0，且输出结构体为全 0（不报错） | 读到全 0 结构体时说明尚未配置，不是「读失败」 | SDK V3.14.0 实现行为，需按版本核验 |
| 3.2 | Disable **不清除**已保存的 PubAttr，`AX_VO_GetPubAttr` 仍返回上次配置 | 退出/重启流程中读回值非 0 属正常 | SDK V3.14.0 实现行为，需按版本核验 |
| 3.3 | **未 Init（或 Deinit 后）调用 `AX_VO_GetPubAttr` 会返回 0 且不写输出结构体**（调用方无法区分成功与未初始化），属实现特例 | 需要区分时先在代码里保证 Init 后再读，或改为读 `dmesg`/proc | SDK V3.14.0 实现行为，需按版本核验 |
| 3.4 | 该 API 不做 memset 清零；输出缓冲区的初值会被保留到被成功赋值 | 客户代码请先自行初始化结构体再传入 | SDK V3.14.0 实现行为，需按版本核验 |

## 4. 格式白名单（接口 × 输出格式）

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 4.1 | BT601/BT656/BT1120 输出**只允许 `AX_VO_OUT_FMT_YUV422`**；其他格式在 SetPubAttr 前置校验即返回 `AX_ERR_VO_ILLEGAL_PARAM` | 客户代码 `enIntfFmt` 逐字核对；非法组合不会走到内核 | SDK V3.14.0 实现行为，需按版本核验 |
| 4.2 | **DPI 不是只支持 RGB565**：允许 `RGB565`（并行）、`SRGB565`/`SRGB666`（串行 ×2）、`SRGB565S`/`SRGB888`（串行 ×3）、`SRGB888A`/`SRGB888B`（串行 ×4）；其余格式返回 `AX_ERR_VO_ILLEGAL_PARAM` | 按屏接口类型（并行 RGB / 串行 sRGB）选格式；串行格式的时钟倍率见 4.3 | SDK V3.14.0 实现行为，需按版本核验 |
| 4.3 | 串行 sRGB 的 `u32Pclk` 语义与并行不同：**送入显示通路的时钟 = u32Pclk × 倍率**（×2/×3/×4，按 4.2 的格式分组），真实刷新率 = 配置公式值 ÷ 倍率；并行 RGB565 无倍率 | 串行屏：目标像素时钟 = u32Pclk×倍率；用 proc `Refresh`/`OutFps` 或 VSYNC 计数核对 | SDK V3.14.0 实现行为，需按版本核验 |
| 4.4 | USER 自定义时序路径下 **BT1120 的接口×格式组合不做前置校验**（同一非法组合在预设模式会被拒、在 USER 模式会下发到内核，最终以 `AX_ERR_VO_DEV_OP_FAIL` 形式失败） | USER 模式同样按 4.1 自查格式，不要依赖前置报错 | SDK V3.14.0 实现行为，需按版本核验 |
| 4.5 | 输入帧格式（`AX_VIDEO_FRAME_T.enImgFormat`）与输出接口格式**无一致性校验**，输入白名单为 NV12/NV21、NV16/NV61、YUV422 交织（YUYV/YVYU/UYVY/VYUY）、RGB565 系、RGB888 系、ARGB/RGBA 系、YUV400 等；不在白名单 → `AX_ERR_VO_ILLEGAL_PARAM` | 自填帧结构体时逐字核对格式枚举名 | SDK V3.14.0 实现行为，需按版本核验 |

## 5. 帧缓冲：stride / FBC / 尺寸 / plane / crop / LBA

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 5.1 | 非压缩帧：**`u32PicStride[0]` 必须 16 字节对齐**（`AX_VO_STRIDE_ALIGN_VAL=16`），否则 `AX_ERR_VO_ILLEGAL_PARAM`；仅校验 plane0 的 stride | 客户 stride 计算式按 16 对齐取整 | SDK V3.14.0 实现行为，需按版本核验 |
| 5.2 | 带 FBC（LOSSY）压缩的帧：**`u32PicStride[0]` 必须 128 字节对齐**（不是 16/64）；帧高按 2 行成对组织 | FBC 帧的 stride 按 128 对齐分配；异常花屏先查 stride | SDK V3.14.0 实现行为，需按版本核验 |
| 5.3 | 帧宽高约束：宽 [16,3840] 且 2 对齐、高 [4,8190] 且 2 对齐（USER 显示宽高同源），否则 `AX_ERR_VO_ILLEGAL_PARAM` | 客户自定义分辨率与帧尺寸逐字核对 | SDK V3.14.0 实现行为，需按版本核验 |
| 5.4 | **隔行（bIop=0）的 BT 接口不支持压缩帧**：601/656/1120 且在隔行模式且帧为 LOSSY 压缩时返回 `AX_ERR_VO_ILLEGAL_PARAM`（无损/非压缩不拦） | 隔行输出场景改用非压缩帧或改逐行 | SDK V3.14.0 实现行为，需按版本核验 |
| 5.5 | **源尺寸与输出尺寸**：VO 不执行通用缩放；未使用 LBA/Coax 时要求「crop 后的源尺寸 ≥ 显示尺寸」，否则 `AX_ERR_VO_ILLEGAL_PARAM`；开启 LBA(AUTO/MANUAL) 或 Coax 后不采用该前置尺寸判据，最终画面处理效果仍需实机确认 | 源小于输出时，优先在上游完成缩放；若使用 LBA 仅按补边/区域布局能力配置并实测，不将其视为缩放器 | SDK V3.14.0 实现行为，需按版本核验 |
| 5.6 | 图像读取尺寸优先级：**crop 尺寸优先于整帧尺寸**；crop 有效时按 crop 偏移取图，显示时序独立于源尺寸 | 需要局部放大/裁剪显示时用帧结构体的 crop 字段 | SDK V3.14.0 实现行为，需按版本核验 |
| 5.7 | `plane` 由实现侧推导，客户结构体**不回写**：必填 `u32Width/u32Height`、`enImgFormat`、`u32PicStride[0]`、`u64PhyAddr[0]` 或有效 `u32BlkId[0]`（二者皆空 → `AX_ERR_VO_ILLEGAL_PARAM`）；`u32PicStride[1]`/`u64PhyAddr[1]` 可留 0 由实现推导；第 3 组地址不使用 | YUV 半平面帧只填 plane0 与（可选）plane1 | SDK V3.14.0 实现行为，需按版本核验 |
| 5.8 | **crop 约束**：`cropX + cropW ≤ width`、`cropY + cropH ≤ height`；crop 宽高 >0 时要求 `cropX/cropY ≥ 0`；crop 全 0 = 全图 | 客户裁剪参数按上述不等式自查 | SDK V3.14.0 实现行为，需按版本核验 |
| 5.9 | **LBA（`AX_VO_SetAspectRatio`）**：MANUAL 模式要求 `image_w + LeftSize + RightSize == 显示宽`（高同理），否则 `AX_ERR_VO_ILLEGAL_PARAM`；MANUAL 的 `u16LeftSize` 必须为偶数；BT 系接口的背景色 Y/U/V 三分量须各在 [16,235]；参数非法直接报错不钳位；该 API 仅在「已配置/已使能」状态可调用 | LBA 配置后画面出现黑边/偏移，按上述等式核对 | SDK V3.14.0 实现行为，需按版本核验 |
| 5.10 | **Pool block Release 与直接覆写物理 buffer 必须区分**：帧 buffer 来自 SDK 池时，池引用计数负责回收，跨模块/跨线程的释放须成对；直接覆写物理 buffer（裸 malloc 转向量或 mmap 直写）绕过引用计数，显示侧仍在读时即产生撕裂/花屏，且 Disable/Deinit 时的池回收不会保护这类内存 | 排查 buffer 生命周期：确认每帧来自池且释放与获取配对；把「立即覆写」改成「等显示读完/双缓冲」后复现验证 | SDK V3.14.0 实现行为，需按版本核验 |

## 6. FrCtrl / PTS

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 6.1 | 用户态不解释 FrCtrl/PTS，原样下发；**帧率控制由帧标志位或池元数据触发**（二选一），触发后 PTS 参与显示判定 | 客户若依赖帧率控制，需确认帧标志与池元数据的配置，而不是只看结构体默认值 | SDK V3.14.0 实现行为，需按版本核验 |
| 6.2 | 帧率控制模式下的 PTS 特例：**`PTS == -1` 的帧被丢弃不显示**；PTS 不满足单调性时按非法帧处理（返回 `AX_ERR_VO_ILLEGAL_PARAM`） | 客户自填 PTS 时保证单调递增；不需要节流时不要开帧率控制 | SDK V3.14.0 实现行为，需按版本核验 |
| 6.3 | `u64PTS` 在 Coax 模式下另有用途（作为 Coax 时间戳下发）；`u32FrameSize` 仅在 Coax 模式下使用，非 Coax 时被忽略 | Coax 场景按帧大小字段填实际帧字节数 | SDK V3.14.0 实现行为，需按版本核验 |

## 7. VSYNC 回调生命周期

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 7.1 | 注册要求：设备已使能（否则 `AX_ERR_VO_NOT_PERM`）、回调指针非空（否则 `AX_ERR_VO_NULL_PTR`）；**不允许在回调上下文内注册/注销**（`AX_ERR_VO_NOT_PERM`） | 回调内不要调用注册/注销，改到主线程 | SDK V3.14.0 实现行为，需按版本核验 |
| 7.2 | 重复注册同一回调（同一函数+同一私有数据）返回成功但不重复添加；**未注册就注销直接返回成功**（静默无操作） | 代码中不要依赖「注销返回 0」判断是否注册过 | SDK V3.14.0 实现行为，需按版本核验 |
| 7.3 | 回调按场频（VSYNC）触发，**在单一事件线程内串行执行**；回调耗时会阻塞后续回调与注册/注销操作 | 回调内避免耗时操作；送帧节拍建议放在回调里只做投递 | SDK V3.14.0 实现行为，需按版本核验。**事件线程机制自 V3.5.0 重构**：旧版（V3.1.0~V3.4.0）回调串行语义相同，但线程调度与停止时序不同，依赖线程时序的应用须实机验证 |
| 7.4 | **Disable 不会自动注销回调**（有回调时 Disable 直接失败）；Deinit 会清空全部回调。退出顺序必须显式 UnReg | 退出流程按「UnReg → Disable → Deinit」实现 | SDK V3.14.0 实现行为，需按版本核验 |

## 8. enClkEdge 与 DataPinMap

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 8.1 | `enClkEdge` 合法取值仅 `AX_VO_CLK_SDR_EDGE_DOWN=0` / `AX_VO_CLK_SDR_EDGE_UP=1`；**非法值返回 `AX_ERR_VO_INVALID_DEVID`（不是 ILLEGAL_PARAM）**，属返回码特例 | 看到 `AX_ERR_VO_INVALID_DEVID` 时先检查 enClkEdge 是否填了非法值 | SDK V3.14.0 实现行为，需按版本核验 |
| 8.2 | `AX_VO_SetDataPinMap` 数据线数组固定 19 项（DATA0..DATA15、DE、HSYNC、VSYNC）；**无取值/重复校验**，越界值会串写到相邻配置位（只能在寄存器级表现） | 板级连线与默认映射不同时必须显式设置；逐项按硬件原理图核对 | SDK V3.14.0 实现行为，需按版本核验 |
| 8.3 | 一旦调用过 `AX_VO_SetDataPinMap`，会屏蔽该设备的默认引脚映射；未调用时按默认映射输出 | 换板后画面异常先确认是否沿用了上一次的 pinmap | SDK V3.14.0 实现行为，需按版本核验 |

## 9. Clip 与 Coax

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 9.1 | `AX_VO_SetClipParam` 的 6 个范围值（Y/U/V 各下限+上限）在下发前被钳位到 [1,254]，并要求每通道下限 ≤ 上限，否则 `AX_ERR_VO_ILLEGAL_PARAM`；不调用该 API 时按实现默认（BT 模式默认 Y 16~235、U/V 16~240） | 画面灰阶/黑白位异常时核对 clip 参数是否被显式设置 | SDK V3.14.0 实现行为，需按版本核验 |
| 9.2 | Clip 仅对 BT 输出模式生效；**Coax 模式下强制关闭 Clip** | Coax 场景不要依赖 Clip 调色 | SDK V3.14.0 实现行为，需按版本核验。**该限制自 V3.1.0 起**：V3.0.0 中并行 RGB / 串行 sRGB 信号下 Clip 配置仍生效 |
| 9.3 | **Coax（HDCVI 风格）通路已实现**：`AX_VO_SetCoaxAttr`/`AX_VO_GetCoaxAttr` 可设 `bCoaxEn` 与速率/制式模式；开启后跳过「源≥输出」校验、使用 PTS 与帧大小字段、强制关 Clip | 仅在确认板级为 Coax 输出时启用；能力以客户硬件与产品线确认为准 | SDK V3.14.0 实现行为，需按版本核验 |
| 9.4 | **数字 Coax 帧更新自 V3.11.0 起等待前帧发送完成**（轮询约 100ms 内），修复数字 Coax 数据被裁剪缺陷；V3.10.0 及更早版本存在该缺陷（现象：Coax 数据偶发被裁/异常） | Coax 数据异常时先确认 SDK 版本：≤ V3.10.0 优先建议升级 V3.11.0+ 后复测 | SDK V3.14.0 实现行为，需按版本核验（自 V3.11.0 修复） |
| 9.4 | **无 CVBS/模拟（VENC/DAC）输出通路**：接口枚举只有 DPI/BT601/BT656/BT1120/DSI/LVDS/CSI，无 CVBS 项；BT601/BT656 是数字并口 | 客户要求 CVBS 输出时按「场景无法实现」处理并给出替代方案 | SDK V3.14.0 实现行为，需按版本核验 |

## 10. EnumMode / Layer / Chn / WBC / QueryChnStatus 支持情况

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 10.1 | **`AX_VO_EnumMode` 在本实现中返回 `AX_ERR_VO_NOT_SUPPORT`**，不能作为排查手段 | 不要用 EnumMode 探测支持模式；改查公开头文件的预设枚举与 [vo-timing-table.json](vo-timing-table.json) | SDK V3.14.0 实现行为，需按版本核验 |
| 10.2 | **Layer 级接口全部返回 `AX_ERR_VO_NOT_SUPPORT`**：创建/销毁层、层属性、层 CSC、层使能/绑定、取层 fd、取/放层帧等；Chn 级接口（含 `AX_VO_SendFrame`、通道属性、显示/隐藏通道等）同样全部不支持 | 客户代码出现 Layer/Chn 调用即属用法错误（AX615 不可用），改用设备级 API | SDK V3.14.0 实现行为，需按版本核验 |
| 10.3 | **WBC 全部接口与 `AX_VO_CscMatrix` 返回 `AX_ERR_VO_NOT_SUPPORT`** | 需要回写/矩阵转换时不要走这些接口 | SDK V3.14.0 实现行为，需按版本核验 |
| 10.4 | **`AX_VO_QueryChnStatus` 不作为排查手段**：参数为空返回 `AX_ERR_VO_NULL_PTR`，否则落到不支持路径返回 `AX_ERR_VO_NOT_SUPPORT`；`AX_VO_ClearChnBuf` 同样不支持 | 判断积压/饥饿请改用 proc 的 `InFifoSize`/`DiscFrames`/`InFps`/`OutFps` | SDK V3.14.0 实现行为，需按版本核验 |
| 10.5 | 例外：`AX_VO_BindVideoLayer`/`AX_VO_UnBindVideoLayer`（及图形层绑定版本）**有实现**（忽略层号，等价于开关图形层通路），不在不支持之列 | 仅在这两个接口上不要按「Layer 全不支持」下结论 | SDK V3.14.0 实现行为，需按版本核验 |

## 11. DPI / DSI / LVDS 能力闸门

| # | 行为约束 | 客户侧核验方式 | 标注 |
|---|---|---|---|
| 11.1 | **DSI / LVDS / CSI 在本实现的 SetPubAttr 前置校验即被拒绝**（`AX_ERR_VO_ILLEGAL_PARAM`），实现侧无对应输出通路；接口枚举中的 DSI/LVDS 为跨芯片通用定义 | 客户要求 MIPI DSI/LVDS 输出 → 终态「场景无法实现」，给出桥接/换型号方案 | SDK V3.14.0 实现行为，需按版本核验 |
| 11.2 | 预设模式中的竖屏项（`AX_VO_OUTPUT_720x1280_60` 等）注释标为 DSI 用途，与 DSI 通路不可用相互独立，不要据此认为 DSI 可用 | 竖屏需求走 DPI/BT 接口的自定义 USER 时序 | SDK V3.14.0 实现行为，需按版本核验 |
| 11.3 | DPI 串行格式×4（如 SRGB888A/B）会把显示时钟放大 4 倍，等效压低可达像素时钟上限（离散档位表最高 297000 kHz） | 高分辨率串行屏先算 4 倍时钟是否命中离散档位表 | SDK V3.14.0 实现行为，需按版本核验 |

## 12. 排查取证的推荐组合

> 本表是取证索引：所列行为条目的完整约束与固定版本标注见其对应小节（**SDK V3.14.0 实现行为，需按版本核验**）。

| 现象 | 客户侧取证 | 对应本文件条目 |
|---|---|---|
| SendFrame2Disp 返回 `AX_ERR_VO_DEV_OP_FAIL` | dmesg + proc（`InFifoSize`/`DiscFrames`/`InFps`/`OutFps`） | 1.1、1.2（SDK V3.14.0 实现行为，需按版本核验） |
| 黑屏但 API 全 0 | proc `ScanType/Refresh/Pclk` + 屏规格书 + [vo-pclk-table.json](vo-pclk-table.json) | 2.2、2.3（SDK V3.14.0 实现行为，需按版本核验） |
| 花屏/撕裂 | buffer 来源与生命周期、stride 对齐、crop/LBA 参数 | 1.4、5.1、5.2、5.8、5.9、5.10（SDK V3.14.0 实现行为，需按版本核验） |
| 偏色 | CSC 配置、Clip 参数、帧色域字段、DataPinMap | 8.2、9.1（SDK V3.14.0 实现行为，需按版本核验） |
| 退出/重启异常 | 调用顺序（UnReg→Disable→Deinit）、重复 Init/Deinit | 2.4、2.5、2.6、7.4（SDK V3.14.0 实现行为，需按版本核验） |
