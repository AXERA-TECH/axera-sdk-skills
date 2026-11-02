# AX615 VO 配置生成知识内联（速查）

> 本文件内联 sdk-vo-analysis 生成配置所需的**结构体/枚举/约束**，供生成时直接引用。
> 来源简称：
> **API文档** = 知识库《32 - AX VO API 文档.docx》｜**开发指南** = 知识库《29 - AX VO 开发指南.docx》
> ｜**公共结构体文档** = 知识库《50 - AX 公共数据结构文档.docx》
> ｜**ax_vo_api.h** = 公开 SDK 头文件（完整逐字内化于本 skill 的
> [sdk-inline/ax_vo_api.h](sdk-inline/ax_vo_api.h)，已脱敏版权头、行号与原文对齐；关键段另见
> 本 skill 的 vo-api-inline.md，本文件引用其语义）
> ｜**ax_global_type.h** = [sdk-inline/ax_global_type.h](sdk-inline/ax_global_type.h)（同上）
> ｜**已验证时序表** = [vo-timing-table.json](vo-timing-table.json)（54 组；**SDK V3.14.0 实现行为，需按版本核验**）
> ｜**sample 时序表** = [sample-vo-timings.json](sample-vo-timings.json)（官方 sample 19 组）
> ｜**PCLK 表** = [vo-pclk-table.json](vo-pclk-table.json)（离散档位表；**SDK V3.14.0 实现行为，需按版本核验**）
> ｜**行为摘要** = [vo-sdk-behavior-notes.md](vo-sdk-behavior-notes.md)（每条带固定标注 **SDK V3.14.0 实现行为，需按版本核验**）
> ｜**Python 约定** = [vo-python-binding.md](vo-python-binding.md)（客户可见调用约定摘要）
> ｜**官方 sample** = 官方 SDK sample（文件名/common_vo.c 等、参数与调用顺序可引用）
> 内化日期 2026-09-14（时序表与 PCLK 表 2026-09-15 扩充）。条目行号未标注者为本次检索原文转录，
> 标注【检索原文】；头文件内化条目标注【内化头文件 行号】。

## 0. 来源分级与使用边界

| 级别 | 来源 | 生成时的用法 |
|---|---|---|
| A | 公开头文件（`ax_vo_api.h`/`ax_global_type.h`） | 字段/枚举/错误码逐字核对，可直接引用行号 |
| B | 官方 sample | 调用顺序、buffer/送帧用法、19 组时序参数 |
| C | 知识库文档 | 能力表、错误码表、proc 字段说明 |
| D/E | 时序表 / PCLK 表 / 行为摘要 | 作为参数与行为判据引用，必须同时引用固定版本标注，并先按 [version-routing.md](version-routing.md) 判定版本匹配；目标版本不同或未知时只能生成候选，不能声称目标版本已验证 |

- 生成配置时**不得**出现实现侧源码路径/文件名/内部符号名/源码行号；需要更细证据时转 A/B/C 级。
- **证据分层**：本文件条目与表数据用于**事实确认**（字段语义、能力边界、时序取值）；生成配置是否解决客户现场问题属**修复验证**，须按第 9 节实机回归，不能凭文档条目宣称已验证。
- 运行时默认只读本 skill 的 references；**用户显式提供的材料（客户日志、代码、屏规格书、版本文件等）允许读取**，但不访问外部源码树，也不主动读取凭据/密钥文件。能力判定只引用第 4 节能力矩阵与第 8 节闸门条目（脚本求解无解不构成能力证明）。

## 1. 核心结构体定义（生成配置的主输入）

### AX_VO_PUB_ATTR_T（API文档 4 数据结构；公开头文件 ax_vo_api.h:192-201）【检索原文】

```c
typedef struct axVO_PUB_ATTR_S {
    AX_VO_MODE_E        enMode;       /* 工作模式；只有 VO0 支持 ONLINE，SendFrame2Disp 须 OFFLINE */
    AX_VO_INTF_TYPE_E   enIntfType;   /* 接口类型 */
    AX_VO_OUT_FMT_E     enIntfFmt;    /* 接口格式；此配置主要只对 BT/DPI 输出有效 */
    AX_VO_INTF_SYNC_E   enIntfSync;   /* 预设模式或 USER */
    AX_VO_SYNC_INFO_T   stSyncInfo;   /* enIntfSync=USER 时生效 */
    AX_U32              u32Flags;
    AX_U32              u32InFifoDepth; /* 输入 FIFO 深度，默认 3，范围 [1,8]；0 或 >8 静默回退为 3 */
    AX_VO_CLK_SINGLE_EDGE_E enClkEdge;  /* SDR_EDGE_DOWN=0 下降沿发数据 / SDR_EDGE_UP=1 上升沿发数据 */
} AX_VO_PUB_ATTR_T;
```

### AX_VO_CSC_T（API文档；头文件 ax_vo_api.h:297-303）【检索原文】

```c
typedef struct {
    AX_VO_CSC_MATRIX_E enCscMatrix;
    AX_U32 u32Luma;       /* luminance: 0 ~ 100 */
    AX_U32 u32Contrast;   /* contrast : 0 ~ 100 */
    AX_U32 u32Hue;        /* hue : 0 ~ 100 */
    AX_U32 u32Satuature;  /* satuature: 0 ~ 100（原文拼写如此） */
} AX_VO_CSC_T;
```

开启四项时推荐值均为 50；越界 [0,100] 报错（API文档 SetCSC 注意）。
调用时机：`AX_VO_SetCSC` 合法状态为「已配置/已使能/已 Disable」——**Enable 前、Enable 后均可**，未 SetPubAttr 时返回 `AX_ERR_VO_NOT_PERM`。

### AX_VIDEO_FRAME_T（公开头文件 ax_global_type.h:323-360）【检索原文，节选关键字段】

```c
typedef struct axVIDEO_FRAME_T {
    AX_U32 u32Width;  AX_U32 u32Height;   /* 宽 [16,3840] 且 2 对齐；高 [4,8190] 且 2 对齐 */
    AX_IMG_FORMAT_E    enImgFormat;       /* 受帧格式白名单约束 */
    AX_VSCAN_FORMAT_E  enVscanFormat;
    AX_DYNAMIC_RANGE_E stDynamicRange;    /* 默认 0 */
    AX_COLOR_GAMUT_E   stColorGamut;      /* 默认 0=BT601，须与实际源一致 */
    AX_U32 u32PicStride[AX_MAX_COLOR_COMPONENT]; /* [0] 非压缩 16 对齐 / FBC 128 对齐 */
    AX_U32 u32ExtStride[AX_MAX_COLOR_COMPONENT];
    AX_U64 u64PhyAddr[AX_MAX_COLOR_COMPONENT];   /* 必须物理地址；[0] 与 u32BlkId[0] 至少一个有效 */
    AX_U64 u64VirAddr[AX_MAX_COLOR_COMPONENT];
    AX_U32 u32BlkId[AX_MAX_COLOR_COMPONENT];     /* SDK 池内存须回填 block id */
    AX_S16 s16CropX; AX_S16 s16CropY;
    AX_S16 s16CropWidth; AX_S16 s16CropHeight;   /* 缺省 0=全图；crop 优先于整帧 */
    AX_U64 u64PTS;
    AX_U64 u64SeqNum;
    AX_U64 u64UserData;
    /* 另有 u32FrameSize 等，详见公共结构体文档；u32FrameSize 仅 Coax 模式使用 */
} AX_VIDEO_FRAME_T;
```

## 2. 关键枚举

### AX_VO_INTF_TYPE_E（ax_vo_api.h:87-96）【内化头文件 87-96】
`AX_VO_INTF_DPI=0, BT601=1, BT656=2, BT1120=3, DSI=4, LVDS=5, CSI=6, BUTT=7`
> **AX615 实现侧只接受 DPI/BT601/BT656/BT1120**；`enIntfType >= AX_VO_INTF_DSI` 在 SetPubAttr 前置校验被拒（`AX_ERR_VO_ILLEGAL_PARAM`）。DSI/LVDS/CSI 枚举为跨芯片通用定义（**SDK V3.14.0 实现行为，需按版本核验**）。

### AX_VO_OUT_FMT_E（ax_vo_api.h:147-162）【内化头文件 146-162】
`AX_VO_OUT_FMT_UNUSED=0, RGB565, RGB666, RGB666LP, RGB888, YUV422, YUV420(仅 CSI_TX), SRGB565, SRGB565S, SRGB666, SRGB888, SRGB888A, SRGB888B, BUTT`

### AX_VO_MODE_E（ax_vo_api.h:81-85）【内化头文件】
`AX_VO_MODE_OFFLINE, AX_VO_MODE_ONLINE, AX_VO_MODE_BUTT`——只有 VO0 能支持 ONLINE；SendFrame2Disp 须 OFFLINE。

### AX_VO_CLK_SINGLE_EDGE_E（ax_vo_api.h:163-167）【内化头文件】
`AX_VO_CLK_SDR_EDGE_DOWN = 0, /*下降沿发送数据*/ AX_VO_CLK_SDR_EDGE_UP = 1, /*上升沿发送数据*/`
> 特例：非法取值返回 `AX_ERR_VO_INVALID_DEVID`（不是 ILLEGAL_PARAM）（**SDK V3.14.0 实现行为，需按版本核验**）。

### AX_VO_INTF_SYNC_E 预设模式（API文档 + 完整成员已逐字内化）
> 完整逐字成员列表见 [sdk-inline/ax_vo_api.h](sdk-inline/ax_vo_api.h) 第 98-145 行【内化头文件
> 98-145，2026-09-14】。全部成员已确认（39 个预设模式 + USER + BUTT）：
> `AX_VO_OUTPUT_576P50 / 576I50 / 480P60 / 480I60 / 720P25 / 720P30 / 720P50 / 720P60 /
> 1080P24 / 1080P25 / 1080P30 / 1080P50 / 1080P60 /
> 640x480_60 / 800x480_60 / 800x600_60 / 1024x600_60 / 1024x768_60 / 1280x1024_60 /
> 1366x768_60 / 1280x800_60 / 1440x900_60 / 1600x1200_60 / 1680x1050_60 / 1920x1200_60 /
> 2560x1600_60 / 3840x2160_24/25/30/50/60 / 4096x2160_24/25/30/50/60 /
> 720x1280_60 / 1080x1920_60 / 1080x1920_30 / USER / BUTT`
> 生成时预设名**以该内化头文件逐字为准**；头文件未列的成员不得虚构。
> **预设名/API 语义由公开头文件（A 级）确认，但不等于"天然可用"或"由 SDK 保证"**：最终时钟仍须经过
> 当前 SDK 的离散 PCLK 档位表与接口/芯片能力校验（第 4 节能力矩阵与第 8 节闸门对预设模式同样适用，
> 如 AX615D 串行 sRGB 的 640×480@30 上限），因此预设配置同样需要实机核验；该可用性判定属
> 「**已授权源码核验的 SDK 行为约束**」（**当前内化版本行为，需按版本核验**）。
> USER 模式正确性由用户保证（用户态只校验显示宽高范围与 2 对齐，
> 不校验 porch/pclk/刷新率）。
> 注意：`720x1280_60 / 1080x1920_60 / 1080x1920_30` 注释标为 DSI 用途，而 AX615 的 DSI 通路不可用，
> 不要用这三个预设支撑 DSI 场景。
> 另注意：**部分常见标准 PCLK 不在可选档位表内**（如 640x480@60 的 25175、800x600@60 的 40000、
> 1024x768@60 的 65000、2560x1600@60 的 348500）——**不能据此推断预设在目标 SDK 上一定可用**
> （预设时钟同样要经过当前 SDK 的离散 PCLK 与接口/芯片能力校验，须实机核验），
> 但**客户自己写 USER 时序时必须先查 [vo-pclk-table.json](vo-pclk-table.json)**（**SDK V3.14.0 实现行为，需按版本核验**）。

### AX_VO_CSC_MATRIX_E（ax_vo_api.h:280-295）
14 种有效取值：IDENTITY / BT601_TO_BT601 / BT601_TO_BT709 / BT709_TO_BT709 /
BT709_TO_BT601 / BT601_TO_RGB_PC / BT709_TO_RGB_PC / RGB_TO_BT601_PC /
RGB_TO_BT709_PC / RGB_TO_BT2020_PC / BT2020_TO_RGB_PC / RGB_TO_BT601_TV /
RGB_TO_BT709_TV / BUTT。默认 BT601_TO_BT601。

### 其他生成相关枚举（ax_vo_api.h）【内化头文件】
- `AX_VO_ASPECT_RATIO_E`（413-419）：NONE(=0，关 LBA) / AUTO(=1) / MANUAL(=2) / BUTT
- `AX_VO_ASPECT_RATIO_ALIGN_E`（421-458）：水平 CENTER/LEFT/RIGHT，垂直 CENTER/TOP/BOTTOM
- `AX_VO_COAX_MODE_E`（473-480）：10M/20M × BCH/NOBCH（HDCVI）
- `AX_VO_CLIP_ADJ_PARAM_T`（488-494）：`bClipEn` + Y/U/V 各 `[下限,上限]`（各值 [1,254]，下限 ≤ 上限）

## 3. 标准调用序列与逐步要点（API文档 图5-2 + 官方 sample）

```
AX_VO_Init
  → AX_VO_SetPubAttr        （每步检查返回值，非 0 按错误码表定位）
  → AX_VO_SetAspectRatio    （可选；官方 sample 在 Enable 前调用；仅「已配置/已使能」可设）
  → AX_VO_SetDataPinMap     （板级连线与默认映射不一致时必须调用）
  → AX_VO_SetCSC            （SetPubAttr 成功之后即可；Enable 前后均可）
  → AX_VO_Enable            （不做时序校验）
  → AX_VO_SendFrame2Disp    （循环；VSYNC 回调节拍送帧）
  → AX_VO_VSYNC_UnRegCallbackFunc → AX_VO_Disable → AX_VO_Deinit（退出）
```

要点（均标注 **SDK V3.14.0 实现行为，需按版本核验**）：
- `AX_VO_Enable` 后改配置须先 `AX_VO_Disable`；重复 Enable/Disable 幂等返回 0。
- **VSYNC teardown**：Disable 前必须先注销回调，否则 Disable 失败；Deinit 前须所有设备已 Disable。
- **FIFO**：`u32InFifoDepth` 默认 3；送帧率不得超过显示刷新率。

## 4. 能力矩阵（生成前置校验，命中即拒绝生成或改方案）

| 场景 | 结论 | 来源 |
|---|---|---|
| BT656/BT601/BT1120 输出 | **只支持 YUV422**（enIntfFmt=AX_VO_OUT_FMT_YUV422）；其他格式前置校验即报 `AX_ERR_VO_ILLEGAL_PARAM` | 行为摘要 4.1；官方 sample |
| DPI 输出 | **并行 `RGB565`；串行 sRGB 组**：`SRGB565`/`SRGB666`（×2）、`SRGB565S`/`SRGB888`（×3）、`SRGB888A`/`SRGB888B`（×4）；其余格式非法 | 行为摘要 4.2（**SDK V3.14.0 实现行为，需按版本核验**） |
| DPI 串行时钟 | 配置公式刷新率 = `u32Pclk×1000/(htotal×vtotal) ÷ 倍率`；高倍率（×4）等效压低可用像素时钟上限 | 行为摘要 4.3（同上标注） |
| AX615D | **不支持 BT1120 和并行 DPI**（VO 仅 11 pin）；**串行 sRGB 可用，上限 640×480@30fps**；BT656/601 可用 | 开发指南 表3-1；串行上限见下一行 |
| AX615D serial RGB | **最大 640×480@30fps** | 开发指南 1.1【检索原文】 |
| AX615Q | 支持 BT656/601/1120/DPI/sRGB | 开发指南 表3-1 |
| DSI/LVDS/CSI | **不支持输出**：SetPubAttr 前置校验直接拒绝，实现侧无通路（枚举为跨芯片通用定义） | 行为摘要 11.1（标注同上）；API文档 表1-1 |
| CVBS / 模拟输出 | **无 CVBS/VENC/DAC 通路**；作为替代，**Coax（HDCVI 风格）通路已实现**（`AX_VO_SetCoaxAttr`，模式 10M/20M × BCH/NOBCH），但 Coax 属专项方案，**默认不生成**，客户确有需求时须先与产品线确认板级支持 | 行为摘要 9.3、9.4（保守结论，标注同上） |
| SendFrame2Disp | 须 OFFLINE 模式（enMode=AX_VO_MODE_OFFLINE） | API文档 |
| 自定义时序 | 须 enIntfSync=AX_VO_OUTPUT_USER，stSyncInfo 生效 | API文档 |
| 缩放 | **无缩放器**：源（crop 后）≥ 显示尺寸；小于时用 LBA（AspectRatio）补边，或改显示尺寸 | 行为摘要 5.5 |

## 5. 时序求解规则（配合 scripts/gen_vo_timing.py）

- 刷新率**配置公式值**：`u32Pclk×1000 / (htotal×vtotal)`；BT656/601 且 YUV422 且 SDR(bDlbClk=0) 时**再 ÷2**（DDR 不再除）；DPI 串行格式再 ÷2/÷3/÷4。
  该值为公式值，**实际输出以 proc `Refresh`/`OutFps` 与 VSYNC 实测为准**（**SDK V3.14.0 实现行为，需按版本核验**）
- **PCLK 离散档位表（5×16，必须精确命中）**：源 {36000, 108000, 118800, 198000, 297000} kHz × 分频 {1,2,4,6,…,30}；
  80 槽位、62 个唯一值（完整枚举见 [vo-pclk-table.json](vo-pclk-table.json)）；**无容差、无就近取整**；
  非整除档位按截断取整（如 36000÷14=2571），必须填表内值。
  不命中时公开 API 侧表现为 `AX_ERR_VO_DEV_OP_FAIL`，需结合 dmesg 的 `unsupport clk` 定位
- BT656 8bit：SDR 下 u32Pclk=像素时钟×2（1080p30→148500）；DDR(bDlbClk=1) 下 u32Pclk=像素时钟（1080p30→74250）
- **`u8DelaySel` 是独立字段，按表条目取（0/3/4 等均有）**，不得简化为"DDR=3、非 DDR=0"；
  客户未提供或表条目未记录时按 unknown 处理，不得默认取值
- 隔行 bIop=0 会改写垂直时序（vbp/vfp/vpw 减半、有效高减半），逐行屏必须 bIop=1；
  隔行 BT 接口**不支持压缩帧**
- 三级求解：① 已验证表精确命中（最高可信）② 近邻模板推导（**标注推导值须实机验证**）③ 客户屏规格书给定 porch 时用 `--verify` 校验
- **求解失败不是能力证明**：`gen_vo_timing.py` 搜索无解（退出码 1）只说明当前模板 + PCLK 档位组合内无解（未扩展 DDR 搜索），**不得据此判定"场景无法实现"**；能力结论只引用第 4 节能力矩阵或第 8 节闸门条目
- 两表（54 组已验证 / 19 组 sample）**独立保存、不静默合并**；差异见 [sample-vo-timings.json](sample-vo-timings.json) 的 `conflicts` 段

## 6. 帧格式/尺寸/stride/crop/LBA 生成自检（送帧前）

| 项 | 约束 | 标注 |
|---|---|---|
| 帧宽高 | [16,3840] 且 2 对齐；[4,8190] 且 2 对齐 | SDK V3.14.0 实现行为，需按版本核验 |
| stride[0] | 非压缩 16 字节对齐；FBC(LOSSY) 128 字节对齐 | 同上 |
| 帧格式 | 输入格式白名单（NV12/NV21、NV16/NV61、YUV422 交织、RGB565 系、RGB888 系、ARGB/RGBA 系、YUV400 等） | 同上 |
| plane 地址 | `u64PhyAddr[0]` 或有效 `u32BlkId[0]` 至少一个；plane1 可留 0 自动推导；第 3 组不用 | 同上 |
| crop | `cropX+cropW ≤ width`、`cropY+cropH ≤ height`；crop 宽高 >0 时 cropX/Y ≥ 0；优先于整帧 | 同上 |
| LBA | MANUAL：`image_w + LeftSize + RightSize == 显示宽`（高同理）；`u16LeftSize` 偶数；BT 背景色 Y/U/V ∈[16,235] | 同上 |
| Clip | 6 个范围值 [1,254] 且下限 ≤ 上限；不设置时默认 Y 16-235、U/V 16-240；Coax 下强制关闭 | 同上 |
| FIFO | `u32InFifoDepth` ∈ [1,8]，非法静默回退 3 | 同上 |
| Pool buffer | 帧走 SDK 池内存（`AX_POOL_GetBlock` + 物理地址 + block id 回填）；**池 block 的释放与直接覆写物理 buffer 是两回事**，后者绕过引用计数导致撕裂 | 同上 |

## 7. 错误码速查（生成代码返回值检查用）

宏定义逐字见 [sdk-inline/ax_vo_api.h](sdk-inline/ax_vo_api.h) 第 41-61 行【内化头文件 41-61】；
hex 值按 `AX_DEF_ERR(0x03, 0x8A, errid)` 公式重算【内化头文件 ax_global_type.h 581-582】；
其中 INVALID_DEVID~QUEUE_FULL 九行与知识库官方文档《52 - AX 软件错误码文档.docx》表 17-1
逐行核对一致（2026-09-14），TIMED_OUT 与 0x83~0x89 行为公式计算值。

| hex | 宏 | 含义 | 生成侧注意 |
|---|---|---|---|
| 0x80038A02 | AX_ERR_VO_INVALID_DEVID | 无效设备 ID | `enClkEdge` 非法值也返回此码（特例） |
| 0x80038A04 | AX_ERR_VO_INVALID_CHNID | 无效通道 ID | AX615 无可用通道级 API |
| 0x80038A0A | AX_ERR_VO_ILLEGAL_PARAM | 参数非法 | 帧参数/格式/宽高/stride/crop/LBA 非法时原样返回 |
| 0x80038A0B | AX_ERR_VO_NULL_PTR | 空指针 | — |
| 0x80038A14 | AX_ERR_VO_NOT_SUPPORT | 不支持 | EnumMode/Layer/Chn/WBC/CscMatrix 均返回此码 |
| 0x80038A15 | AX_ERR_VO_NOT_PERM | 当前状态不允许 | Enable 后改配置、回调未注销时 Disable 等 |
| 0x80038A17 | AX_ERR_VO_NODEV | 设备不存在 | — |
| 0x80038A18 | AX_ERR_VO_NOMEM | 内存不足 | 回调注册内存分配失败等 |
| 0x80038A23 | AX_ERR_VO_QUEUE_FULL | 队列满（送帧快于显示消费） | **本实现用户态不直接返回该码** |
| 0x80038A27 | AX_ERR_VO_TIMED_OUT | 超时（s32MS>0 模式超时未入队） | 同上 |
| 0x80038A80 | AX_ERR_VO_DEV_OP_FAIL | 设备操作失败 | **未使能/队列满/超时/内核拒绝统一为此码**，需结合 dmesg/proc |
| 0x80038A81 | AX_ERR_VO_LAYER_OP_FAIL | 层操作失败 | 层接口不支持 |
| 0x80038A82 | AX_ERR_VO_CHN_OP_FAIL | 通道操作失败 | 通道接口不支持 |
| 0x80038A83 | AX_ERR_VO_INVALID_LAYERID | 无效层 ID | — |
| 0x80038A84 | AX_ERR_VO_OPEN_FILE_FAIL | 打开文件失败 | 未 Init / 句柄不可用时出现 |
| 0x80038A85 | AX_ERR_VO_WBC_OP_FAIL | 回写操作失败 | WBC 不支持 |
| 0x80038A86 | AX_ERR_VO_WBC_INVALID_FD | 回写 FD 无效 | 同上 |
| 0x80038A87 | AX_ERR_VO_HDMI_OP_FAIL | HDMI 操作失败 | — |
| 0x80038A89 | AX_ERR_VO_MODE_NOT_FOUND | 模式未找到 | — |

> 上表 OUT 值来自公开头文件与官方错误码文档；"生成侧注意"列引用行为摘要（**SDK V3.14.0 实现行为，需按版本核验**）。

## 8. 能力闸门汇总（命中即不生成）

1. AX615D + BT1120/并行 DPI → 拒绝（串行 sRGB 不拒绝，但受 640x480@30 上限约束），改 AX615Q 或 BT656/串行 sRGB
2. DSI/LVDS/CSI 输出 → 拒绝（给出桥接/换型号方案）
3. BT 系接口 + 非 YUV422 格式 → 拒绝
4. DPI + 非白名单格式（RGB565/6 种 SRGB）→ 拒绝
5. USER 时序 PCLK 不精确命中离散表 → 重算或改预设模式（预设同样受离散 PCLK 与接口/芯片能力校验约束，须实机核验）
6. 帧宽高超限/奇数、stride 未对齐、隔行 + 压缩帧 → 拒绝生成
7. 源尺寸 < 显示尺寸且未用 LBA → 提示补边方案
8. AX615D 串行 sRGB 超 640x480@30 → 拒绝
9. CVBS/模拟输出 → 无通路；Coax 需求走产品线确认
10. 求解失败不等于能力不支持：`gen_vo_timing.py` 无解（退出码 1）只说明当前搜索空间内无解，不构成芯片/接口能力证明；"无法实现"必须引用第 4 节能力矩阵或本节的表证据条目

## 9. sample 回归流程（生成配置后的实机验证建议）

1. **对照官方 sample 用法**：调用顺序、buffer 获取（`AX_POOL_GetBlock` + 物理地址）、VSYNC 节拍送帧
2. **首验**：用 [sample-vo-timings.json](sample-vo-timings.json) 中已知可用的同接口条目（如 1920x1080@30 bt656）
   跑通链路，确认硬件与屏连接无误
3. **替换**：把生成的目标时序替换进已验证骨架，逐项核对返回值（hex 打印）
4. **proc 核对**：`cat /proc/ax_proc/vo/display_status` 检查 `ScanType`/`Refresh`/`Pclk`/`InFifoSize`/`DiscFrames`
   与预期一致；帧率用 VSYNC 回调计数实测
5. **失败定位**：SetPubAttr 返回 `AX_ERR_VO_DEV_OP_FAIL` 时先看 dmesg 是否 `unsupport clk`；
   SendFrame2Disp 返回该码时结合 proc 的 FIFO/丢帧字段判断是否送帧过快
6. **回归闭环**：改动前后各抓一次 proc + 返回值日志，作为"已验证"的证据留档

## 10. 已知知识缺口与版本路由

| 项 | 规则 | 标注 |
|---|---|---|
| `/proc/ax_proc/vo/display_status` 版本 | 版本行应扫描 `[SDK version]:`，不能假设位于物理首行；优先代表运行中 VO 模块版本 | **SDK V3.14.0 实现行为，需按版本核验** |
| `/proc/ax_proc/version` / `AX_SYS_GetSdkVersion()` | 作为系统/内核版本旁证；节点可能不存在，失败不等于 VO 异常 | **SDK V3.14.0 实现行为，需按版本核验** |
| 版本不同 | D/E 级时序、PCLK、行为摘要只能作为候选，须在目标 SDK 重新核验（**无提交/无差异记录不等于行为保证**）；需要新知识时先征得用户许可 | 版本路由规则 |
| 版本未知 | 先询问用户是否按当前内化 V3.14.0 临时基线继续；未同意前不生成版本相关配置，同意后只输出“基于 V3.14.0、须按客户实际版本核验”的候选 | 版本路由规则 |

已知缺口：

1. Python（MicroPython natmod `uax_vo_api` / mdk_vo RPC 封装）逐字签名不再内化；调用约定以
   [vo-python-binding.md](vo-python-binding.md) 摘要为准，**客户 SDK 版本不同时以客户实际封装为准**
2. CVBS/模拟输出无通路（结论已确认）；Coax 板级支持须产品线确认
3. **u32Flags 字段含义**未逐字确认（头文件仅声明字段无注释【内化头文件 198】）；生成时置 0 并标注
4. **DPI 已验证时序条目少**：DPI 场景优先走预设模式（如 `AX_VO_OUTPUT_800x480_60`，同样须实机核验），
   自定义走 USER + 离散档位表求解 + 实机回归（串行格式注意时钟倍率）
5. 预设模式枚举完整成员已逐字内化（见第 2 节），生成前直接核对
   [sdk-inline/ax_vo_api.h](sdk-inline/ax_vo_api.h) 第 98-145 行即可，无需再 kb_query
