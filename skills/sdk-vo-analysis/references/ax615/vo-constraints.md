# AX615 VO 关键约束内联（速查）

> 本文件内联 AX615 VO 模块的**已验证关键约束**，供诊断时直接引用，避免每次重新检索知识库、避免给出泛化建议。
> 条目用于**事实确认**（某约束是否成立）；把它与客户现场证据（返回值/日志/proc/复现规律）连成因果链
> 才能确认本次根因——**条目本身不能单独证明本次故障的因果**（证据链三段见 SKILL.md 第 5 步）。
> 每条约束注明来源；诊断结论引用本文件时沿用来源标注。来源简称：
> **API文档** = 知识库《32 - AX VO API 文档.docx》｜**开发指南** = 知识库《29 - AX VO 开发指南.docx》
> **ax_vo_api.h** = 公开头文件内化副本 [sdk-inline/ax_vo_api.h](sdk-inline/ax_vo_api.h)（行号与原文一致，可引用）
> **ax_global_type.h** = [sdk-inline/ax_global_type.h](sdk-inline/ax_global_type.h)（同上）
> **已验证时序表** = [vo-timing-table.json](vo-timing-table.json)（54 组；**SDK V3.14.0 实现行为，需按版本核验**）
> **sample 时序表** = [sample-vo-timings.json](sample-vo-timings.json)（官方 sample 内置 19 组，含表间差异说明）
> **PCLK 表** = [vo-pclk-table.json](vo-pclk-table.json)（离散档位表；**SDK V3.14.0 实现行为，需按版本核验**）
> **行为摘要** = [vo-sdk-behavior-notes.md](vo-sdk-behavior-notes.md)（每条均带固定版本标注 **SDK V3.14.0 实现行为，需按版本核验**）
> **官方 sample** = 官方 SDK sample（文件名/common_vo.c 等、参数与调用顺序可引用）
> 来源分级与使用边界见 [vo-knowledge-provenance.md](vo-knowledge-provenance.md)。

## 1. 调用顺序与模式约束

| 约束 | 来源 |
|---|---|
| 标准顺序：`Init → SetPubAttr → (SetDataPinMap) → (SetCSC) → Enable → SendFrame2Disp`；退出顺序：`UnReg VSYNC → Disable → Deinit` | 官方 sample；API文档 |
| 官方 sample 中 `AX_VO_SetAspectRatio` 紧随 `AX_VO_SetPubAttr` 之后调用（在 Enable 之前） | 官方 sample（common_vo.c 调用顺序） |
| `AX_VO_SetCSC` 在 `SetPubAttr` **成功之后**即可调用：合法状态为「已配置 / 已使能 / 已 Disable」，即 **Enable 前、Enable 后均可**；未 SetPubAttr 或未 Init 时报 `AX_ERR_VO_NOT_PERM` | 行为摘要 2.x；API文档 |
| `AX_VO_SendFrame2Disp` 须工作在 Offline 模式（`AX_VO_MODE_OFFLINE`） | API文档 |
| 自定义时序须 `enIntfSync = AX_VO_OUTPUT_USER`，此时 `stSyncInfo` 生效，**正确性由用户保证**（用户态不校验 porch/pclk/刷新率） | API文档；行为摘要 2.2 |
| `AX_VO_Enable` 成功后再次 `SetPubAttr` 返回 `AX_ERR_VO_NOT_PERM`，必须先 Disable | 行为摘要 2.1 |
| `AX_VO_Disable` 前必须先注销全部 VSYNC 回调，否则 Disable 失败；Deinit 前必须所有设备已 Disable | 行为摘要 2.4、2.5、7.4 |

## 2. 输出接口约束（AX615 特有形态）

| 约束 | 来源 |
|---|---|
| BT656/BT601/BT1120 输出**只支持 YUV422**（`AX_VO_OUT_FMT_YUV422`），其他格式返回参数非法 | 行为摘要 4.1；官方 sample |
| **DPI 不是只支持 RGB565**：并行 `RGB565`，串行 `SRGB565/SRGB666`（×2）、`SRGB565S/SRGB888`（×3）、`SRGB888A/SRGB888B`（×4）；其余格式非法 | 行为摘要 4.2 |
| DPI 串行格式的 `u32Pclk` 与并行语义不同：配置公式刷新率 = `u32Pclk×1000/(htotal×vtotal) ÷ 倍率`（×2/×3/×4） | 行为摘要 4.3 |
| BT1120 默认线序：VO_D0-D7=Y 通道 8 根，VO_D10-D17=UV 通道 8 根；板级连线不同必须 `AX_VO_SetDataPinMap` | API文档 SetDataPinMap 示例 |
| SOC 共 19 个输出管脚：data0-15、16=DE、17=hsync、18=vsync；DataPinMap 调用后**屏蔽默认引脚映射**，且不做取值校验 | API文档 SetDataPinMap 注意；行为摘要 8.2、8.3 |
| **AX615D 不支持 BT1120 和并行 DPI**（VO 仅 11 pin）；**AX615D 串行 sRGB 可用，但受能力矩阵上限 640×480@30 约束**；**AX615Q 支持** BT1120/并行 DPI。诊断 BT1120/并行 DPI 问题先确认芯片型号 | 开发指南 表3-1；串行上限见 vo-config-reference.md 第 4 节 |
| **DSI / LVDS / CSI 输出在本实现中不可用**（SetPubAttr 前置校验即拒绝）；接口枚举中的 DSI/LVDS 为跨芯片通用定义 | 行为摘要 11.1；API文档 表1-1 |
| 无 CVBS/模拟（VENC/DAC）输出通路；Coax（HDCVI 风格）通路已实现，可按 Coax 专属属性开启 | 行为摘要 9.3、9.4 |

## 3. 时序与时钟约束（花屏/黑屏首要怀疑对象）

| 约束 | 来源 |
|---|---|
| `bIop`：0=隔行(i) 1=逐行(p)，须与屏扫描方式一致；隔行会实质改写垂直时序（vbp/vfp/vpw 减半、有效高减半） | ax_vo_api.h:171；行为摘要 2.x；开发指南 |
| `u32Pclk` 单位 **kHz**；`bDlbClk` ddr 双沿模式 | ax_vo_api.h:184,188 |
| BT656 是 8bit 接口：**单沿(SDR)下 u32Pclk = 像素时钟×2**（每时钟 1 字节，1 像素 2 字节）；**双沿(DDR, bDlbClk=1)下 u32Pclk = 像素时钟**。1080p30 bt656：SDR 用 148500、DDR 用 74250。API 文档注释"pixel clock"易被误解，以时序表数据与实测为准 | 已验证时序表条目 `1920x1080@30f_bt656`/`1920x1080@30f_bt656_db-edge`；sample 时序表第 4/6 条（官方 sample） |
| `u8DelaySel` 是**独立时序字段**，不同条目取值不同（0/3/4 等均有出现）：**不得简化为"DDR=3、非 DDR=0"**；客户未提供或表条目未记录时按 unknown 处理，不得默认等价 | 已验证时序表（对照 `2880x1620@25f_bt1120`=4 与 sample 第 12 条=0）；行为摘要 8.x |
| 刷新率**配置公式值**：`u32Pclk×1000 / (htotal×vtotal)`；BT656/601 且 YUV422 且 SDR 时**再 ÷2**；DPI 串行按格式再 ÷2/÷3/÷4。该值为公式值，**实际输出以 proc `Refresh`/`OutFps` 与 VSYNC 实测为准**（SDK V3.14.0 实现行为，需按版本核验） | 行为摘要 4.3；`scripts/check_vo_timing.py` |
| htotal=Hact+Hbb+Hfb+Hpw；vtotal=Vact+Vbb+Vfb+Vpw | 公开头文件字段语义（ax_vo_api.h:169-189） |
| **PCLK 是 5×16 离散档位表**：5 个固定源 {36000, 108000, 118800, 198000, 297000} kHz × 分频 {1,2,4,6,8,...,30}，共 80 槽位、**62 个唯一可达值**（完整枚举见 [vo-pclk-table.json](vo-pclk-table.json)）。**必须精确命中，无容差、无就近取整**；不命中时 SetPubAttr 失败，**公开 API 侧返回 `AX_ERR_VO_DEV_OP_FAIL`，内核日志出现 `unsupport clk`（须结合 dmesg 定位）** | 行为摘要 2.2；PCLK 表（SDK V3.14.0 实现行为，需按版本核验） |
| 非整除档位按源频率**截断取整**：例如 36000÷14 → 2571（不是 2571.43）、297000÷14 → 21214；客户须填**表内值**，填数学计算值必不命中 | PCLK 表 |
| 33300 不可达（最近为 33000 = 198000÷6）；640x480@60 的 25175、800x600@60 的 40000、1024x768@60 的 65000、2560x1600@60 的 348500 等常见标准值均**不在表内** | PCLK 表 |
| 800x480 屏可考虑预设模式 `AX_VO_OUTPUT_800x480_60`：**预设名/API 语义由公开头文件确认，但不代表"天然可用"或"由 SDK 保证"**——最终时钟仍须经过当前 SDK 的离散 PCLK 档位表与接口/芯片能力校验，须实机核验；需自定义时序时走 `AX_VO_OUTPUT_USER` + PCLK 离散表 | API文档 预设模式；ax_vo_api.h:115；**已授权源码核验的 SDK 行为约束（当前内化版本行为，需按版本核验）** |
| `SetPubAttr`(USER) 只校验 Hact(16-3840 且偶数)/Vact(4-8190)；**`AX_VO_Enable` 不做任何时序校验**——"API 全返回 0 + 无日志"≠ 时序正确 | 行为摘要 2.2、2.3；ax_vo_api.h:22-29 |
| 排查客户时序一律对照两张表（54 组已验证 / 19 组 sample），可用 `scripts/check_vo_timing.py` 自动比对（`--intf dpi` 必须显式 `--fmt`）；两表存在差异时不静默合并（例见 sample 时序表 conflicts 段） | 已验证时序表；sample 时序表 |

## 4. CSC 与颜色

| 约束 | 来源 |
|---|---|
| 显示设备 CSC **默认 AX_VO_CSC_MATRIX_BT601_TO_BT601**——不调用 SetCSC ≠ 不做转换；源为 BT.709/RGB 时按 BT601 解释会产生系统性偏色（"默认配置"是既定行为，不是芯片缺陷） | API文档 SetCSC 注意 |
| 亮度/色度/饱和度/对比度默认**未开启**；开启时四项推荐值均为 50，越界 [0,100] 报错 | API文档 SetCSC 注意 |
| 输出 YUV422 时：源为 RGB → `enCscMatrix` **不能配 IDENTITY**；源为 YUV → 内部不转换，可用 IDENTITY | API文档 SetCSC 注意 |
| **AX615 不支持 Layer 级 CSC**（Layer 系列接口全部返回 `AX_ERR_VO_NOT_SUPPORT`），只有设备级 `AX_VO_SetCSC` | 行为摘要 10.2 |
| 矩阵选项共 14 种（BT601/BT709/RGB×PC/TV 组合）：`ax_vo_api.h:280-295` | ax_vo_api.h |
| 不调用 `AX_VO_SetClipParam` 时默认输出范围 Y 16-235、Cb/Cr 16-240；Clip 参数下发前被钳位到 [1,254] 且要求下限 ≤ 上限，非法即报错；Coax 模式强制关闭 Clip | API文档 SetClipParam 注意；行为摘要 9.1、9.2 |
| 自填 `AX_VIDEO_FRAME_T` 须正确填 `stColorGamut`/`stDynamicRange`（默认 0=BT601），与实际源一致 | ax_global_type.h:328-329 |

## 5. SendFrame2Disp 与帧缓冲

| 约束 | 来源 |
|---|---|
| `s32MS` 语义：**-1 阻塞 / 0 非阻塞 / 正值 超时等待（ms）**——0 时队列满立即失败不等待 | 行为摘要 1.3；API文档 SendFrame2Disp 参数 |
| **公开 API 的错误码是被包装过的，不能假设透传队列满/超时**：设备未使能、底层 ioctl 失败（含队列满/超时）等统一返回 `AX_ERR_VO_DEV_OP_FAIL`（0x80038A80）；仅帧参数非法原样返回 `AX_ERR_VO_ILLEGAL_PARAM`；另有 NULL_PTR/INVALID_DEVID/OPEN_FILE_FAIL | 行为摘要 1.1、1.2 |
| 因此客户报「SendFrame2Disp 返回超时/队列满」时：**须先确认 SDK 版本与打印位置**，并抓 dmesg + proc 佐证（`InFifoSize`/`DiscFrames`/`InFps`/`OutFps`）；错误码对照表见 [vo-api-inline.md](vo-api-inline.md) | 行为摘要 1.1、1.2 |
| 返回 0 **仅代表帧已入队**，不代表显示已读完该 buffer | 行为摘要 1.4 |
| **Pool block Release 与直接覆写物理 buffer 要区分**：帧 buffer 走 SDK 池时由引用计数保护，获取/释放须成对；直接覆写物理 buffer（裸 malloc 转向量、mmap 直写）绕过引用计数，显示侧仍在读时即花屏/撕裂，且 Disable/Deinit 时的池回收不保护这类内存 | 行为摘要 5.10 |
| `u32InFifoDepth` 输入 FIFO 深度：默认 3，范围 [1,8]；**0 或 >8 不报错而是静默回退为 3**（GetPubAttr 读回生效值） | 行为摘要 1.5 |
| 帧 buffer 建议走 SDK 池内存（`AX_POOL_GetBlock`+物理地址）或 `AX_SYS_MemAlloc`（物理连续），`u64PhyAddr` 必须填物理地址 | 官方 sample 用法；SYS API 文档 |
| 送帧率 > 显示刷新率会导致 FIFO 积压/失败；建议 VSYNC 回调（`AX_VO_VSYNC_RegCallbackFunc`）节拍送帧 | API文档；行为摘要 7.3 |

## 6. 帧格式、尺寸与裁剪约束（送帧前自检）

| 约束 | 来源 |
|---|---|
| 帧宽高：宽 [16,3840] 且 2 对齐；高 [4,8190] 且 2 对齐；USER 显示宽高同源约束 | 行为摘要 5.3；ax_vo_api.h:22-27 |
| 非压缩帧 `u32PicStride[0]` **16 字节对齐**；FBC(LOSSY) 压缩帧 `u32PicStride[0]` **128 字节对齐**（不是 16/64） | 行为摘要 5.1、5.2；ax_vo_api.h:28-29 |
| **隔行 BT 接口不支持压缩帧**：601/656/1120 + bIop=0 + LOSSY 压缩 → 参数非法 | 行为摘要 5.4 |
| 必填字段：`u32Width/u32Height`、`enImgFormat`（白名单）、`u32PicStride[0]`、`u64PhyAddr[0]` 或有效 `u32BlkId[0]`；plane1 stride/地址可留 0 自动推导，第 3 组地址不使用 | 行为摘要 5.7 |
| VO **无缩放能力**：未开 LBA/Coax 时要求「crop 后的源尺寸 ≥ 显示尺寸」；否则用 `AX_VO_SetAspectRatio`(LBA) 补边 | 行为摘要 5.5 |
| crop 优先级高于整帧：`cropX+cropW ≤ width`、`cropY+cropH ≤ height`，crop 宽高 >0 时 cropX/Y 须 ≥ 0；全 0 = 全图 | 行为摘要 5.6、5.8 |
| LBA MANUAL：`image_w + LeftSize + RightSize == 显示宽`（高同理），`u16LeftSize` 须偶数，BT 背景色 Y/U/V 各 ∈[16,235]；非法直接报错不钳位；仅「已配置/已使能」状态可设 | 行为摘要 5.9 |
| FrCtrl/PTS：帧率控制开启时 `PTS == -1` 的帧被丢弃、PTS 非单调按非法帧处理；Coax 模式下 PTS/帧大小字段另有用途 | 行为摘要 6.1-6.3 |

## 7. proc 与 SDK 版本路由

| 约束 | 来源 |
|---|---|
| `/proc/ax_proc/vo/display_status`：显示状态权威信息，字段含 `ScanType`(P/I)、`Refresh`、`Pclk`、`HTimings/VTimings`、`FifoLen`、`InFifoSize`、`InFps/OutFps`、`DiscFrames`、`BlkMiss`、`RefNum`、`PinMap` 等；版本应扫描 `[SDK version]:` 行，不能假设位于物理首行 | API文档 7.2 节；版本路由规则 |
| **联合判据（不只单字段）**：`ScanType=I` 而屏要求逐行 → bIop 错误；`Refresh` 偏离目标 → pclk/porch 错误；`InFps > OutFps` 持续 → 送帧过快；`InFifoSize` 长期等于 `FifoLen` → FIFO 常满；`DiscFrames`/`BlkMiss` 增长 → 丢帧/缺块；结合 `PinMap` 判断 DataPinMap 是否与硬件一致 | API文档 7.2；行为摘要 12 |
| **SendFrame2Disp 报 `AX_ERR_VO_DEV_OP_FAIL` 时必须结合 dmesg/proc**：该码同时覆盖「未使能」「队列满」「超时」「内核拒绝」等多种原因，dmesg 关键字（如 `unsupport clk`、vsync 未注销提示）用于区分 | 行为摘要 1.1、1.2、2.2 |
| **EnumMode 与 QueryChnStatus 不作为 AX615 V3.14.0 的排查手段**：`AX_VO_EnumMode` 返回 `AX_ERR_VO_NOT_SUPPORT`；`AX_VO_QueryChnStatus` 参数空返回 NULL_PTR、否则 NOT_SUPPORT。积压/饥饿改看 proc | 行为摘要 10.1、10.4 |
| **SDK 版本路由**：先运行 [scripts/detect_sdk_version.py](../../scripts/detect_sdk_version.py)，优先取 `/proc/ax_proc/vo/display_status` 中 `[SDK version]:`；按 [version-routing.md](version-routing.md) 的 `same/different/unknown/conflict` 路由。版本未知时，先询问用户是否按当前内化 V3.14.0 临时基线继续；未同意前不形成版本相关诊断结论，同意后 D/E 级资料只能作为“基于 V3.14.0 的推测” | 版本路由规则；相关 proc/log 行为：**SDK V3.14.0 实现行为，需按版本核验** |

## 8. 常见"看似 SDK 缺陷、实为用法/配置问题"的模式（诊断优先级参考）

| 现象 | 先排除的配置/用法项（按顺序） | 再怀疑的 SDK/驱动项 |
|---|---|---|
| 黑屏无信号但 API 全返回 0 | 时序 pclk 是否精确命中离散表、bDlbClk 组合、bIop、enIntfFmt、enMode、DataPinMap | 内核日志 `unsupport clk`、接口 pinmux、硬件连线 |
| 花屏/抖动/撕裂 | 时序 porch/pclk 与屏规格、隔行误配、stride 对齐（16/128）、buffer 提前复用 | 显示通路中断/时钟抖动（需 proc + DDR 带宽证据） |
| 偏色 | CSC 矩阵与源色域不匹配、Clip 范围、帧色域字段（stColorGamut）、DataPinMap 线序 | CSC 硬件通路（AX615 仅设备级） |
| SendFrame2Disp 报 DEV_OP_FAIL | 设备是否已使能、送帧率是否 > 刷新率、s32MS 取值、buffer 是否池内存 | 抓 dmesg/proc 判断队列满/超时/时钟 |
| 退出/重启异常 | 退出顺序是否为 UnReg → Disable → Deinit、是否重复 Init/Deinit | 设备句柄/回调清理 |
