# AX615 VO API 关键定义内化副本

> 本文件是官方 SDK 发布包头文件（ax_vo_api.h / ax_global_type.h）关键段落的**逐字内化副本**，
> 内化日期 2026-09-11，供诊断时直接引用，避免依赖外部本地目录。原文件变更时需重新内化核对。
>
> **2026-09-14 补充**：头文件**完整版**已逐字内化到 [sdk-inline/ax_vo_api.h](sdk-inline/ax_vo_api.h) 与
> [sdk-inline/ax_global_type.h](sdk-inline/ax_global_type.h)（脱敏版权头、行号与原文对齐）。
> 本文件保留为关键段速查；需完整定义（全部结构体/枚举/错误码/API 签名）时优先查 sdk-inline 完整副本。

## 1. 错误码构成公式（ax_global_type.h:581-582, 367）

```c
#define AX_DEF_ERR( module, sub_module, errid) \
    ((AX_S32)( (0x80000000L) | ((module) << 16 ) | ((sub_module)<<8) | (errid) ))
```
`AX_ID_VO = 0x03`（ax_global_type.h:367）

## 2. VO 错误码宏（ax_vo_api.h:41-61，AX_ID_VO_PUB_SMOD=0x8A，ax_vo_api.h:41）

> hex 值按 `AX_DEF_ERR` 公式展开计算；其中 INVALID_DEVID~QUEUE_FULL 九行已与知识库官方文档
> 《52 - AX 软件错误码文档.docx》表 17-1 逐行核对一致，TIMED_OUT 与 0x83~0x89 行为公式计算值
> （TIMED_OUT 另有通用错误表 errid 0x27 佐证）。
> （2026-09-14 修正：2026-09-11 版表中 01/02/03/04/05/06 六值为未验证的序号推断，与实际 errid
> 不符，已全部更正。）

| 宏 | errid | hex 值 |
|---|---|---|
| AX_ERR_VO_INVALID_DEVID | AX_ERR_INVALID_DEVID (0x02) | 0x80038A02 |
| AX_ERR_VO_INVALID_CHNID | AX_ERR_INVALID_CHNID (0x04) | 0x80038A04 |
| AX_ERR_VO_ILLEGAL_PARAM | AX_ERR_ILLEGAL_PARAM (0x0A) | 0x80038A0A |
| AX_ERR_VO_NULL_PTR | AX_ERR_NULL_PTR (0x0B) | 0x80038A0B |
| AX_ERR_VO_NOT_PERM | AX_ERR_NOT_PERM (0x15) | 0x80038A15 |
| AX_ERR_VO_NODEV | AX_ERR_UNEXIST (0x17) | 0x80038A17 |
| AX_ERR_VO_NOMEM | AX_ERR_NOMEM (0x18) | 0x80038A18 |
| AX_ERR_VO_NOT_SUPPORT | AX_ERR_NOT_SUPPORT (0x14) | 0x80038A14 |
| AX_ERR_VO_QUEUE_FULL | AX_ERR_QUEUE_FULL (0x23) | 0x80038A23 |
| AX_ERR_VO_TIMED_OUT | AX_ERR_TIMED_OUT (0x27) | 0x80038A27 |
| AX_ERR_VO_DEV_OP_FAIL | 0x80 | 0x80038A80 |
| AX_ERR_VO_LAYER_OP_FAIL | 0x81 | 0x80038A81 |
| AX_ERR_VO_CHN_OP_FAIL | 0x82 | 0x80038A82 |
| AX_ERR_VO_INVALID_LAYERID | 0x83 | 0x80038A83 |
| AX_ERR_VO_OPEN_FILE_FAIL | 0x84 | 0x80038A84 |
| AX_ERR_VO_WBC_OP_FAIL | 0x85 | 0x80038A85 |
| AX_ERR_VO_WBC_INVALID_FD | 0x86 | 0x80038A86 |
| AX_ERR_VO_HDMI_OP_FAIL | 0x87 | 0x80038A87 |
| AX_ERR_VO_MODE_NOT_FOUND | 0x89 | 0x80038A89 |

> errid 为平台通用错误枚举值，完整枚举已内化于 [sdk-inline/ax_global_type.h](sdk-inline/ax_global_type.h)
> 第 536-573 行。

## 3. AX_VO_SYNC_INFO_T 结构体（ax_vo_api.h:169-189，逐字）

```c
typedef struct axVO_SYNC_INFO_T {
    AX_BOOL bSynm;      /* sync mode(0:timing,as BT.656; 1:signal,as LCD) */
    AX_BOOL bIop;       /* interlaced or progressive display(0:i; 1:p) */
    AX_U16 u16Vact;     /* vertical active area */
    AX_U16 u16Vbb;      /* vertical back blank porch */
    AX_U16 u16Vfb;      /* vertical front blank porch */
    AX_U16 u16Hact;     /* herizontal active area */
    AX_U16 u16Hbb;      /* herizontal back blank porch */
    AX_U16 u16Hfb;      /* herizontal front blank porch */
    AX_U16 u16Hmid;     /* bottom herizontal active area */
    AX_U16 u16Bvact;    /* bottom vertical active area */
    AX_U16 u16Bvbb;     /* bottom vertical back blank porch */
    AX_U16 u16Bvfb;     /* bottom vertical front blank porch */
    AX_U16 u16Hpw;      /* horizontal pulse width */
    AX_U16 u16Vpw;      /* vertical pulse width */
    AX_U32 u32Pclk;     /* pixel clock, in kHz */
    AX_BOOL bIdv;       /* inverse data valid of output */
    AX_BOOL bIhs;       /* inverse horizontal synch signal */
    AX_BOOL bIvs;       /* inverse vertical synch signal */
    AX_BOOL bDlbClk;    /* ddr mode:double clk */
    AX_U8   u8DelaySel; /* delay value for clock*/
} AX_VO_SYNC_INFO_T;
```

## 4. CSC 矩阵枚举（ax_vo_api.h:280-295，逐字，共 14 种有效取值）

```c
typedef enum {
    AX_VO_CSC_MATRIX_IDENTITY = 0,
    AX_VO_CSC_MATRIX_BT601_TO_BT601,
    AX_VO_CSC_MATRIX_BT601_TO_BT709,
    AX_VO_CSC_MATRIX_BT709_TO_BT709,
    AX_VO_CSC_MATRIX_BT709_TO_BT601,
    AX_VO_CSC_MATRIX_BT601_TO_RGB_PC,
    AX_VO_CSC_MATRIX_BT709_TO_RGB_PC,
    AX_VO_CSC_MATRIX_RGB_TO_BT601_PC,
    AX_VO_CSC_MATRIX_RGB_TO_BT709_PC,
    AX_VO_CSC_MATRIX_RGB_TO_BT2020_PC,
    AX_VO_CSC_MATRIX_BT2020_TO_RGB_PC,
    AX_VO_CSC_MATRIX_RGB_TO_BT601_TV,
    AX_VO_CSC_MATRIX_RGB_TO_BT709_TV,
    AX_VO_CSC_MATRIX_BUTT
} AX_VO_CSC_MATRIX_E;
```

## 5. 色域枚举（ax_global_type.h:199-206）

```c
typedef enum axCOLOR_GAMUT_E
{
    AX_COLOR_GAMUT_BT601 = 0,
    AX_COLOR_GAMUT_BT709,
    AX_COLOR_GAMUT_BT2020,
    AX_COLOR_GAMUT_USER,
    AX_COLOR_GAMUT_BUTT
} AX_COLOR_GAMUT_E;
```
默认值 0 = BT601：`AX_VIDEO_FRAME_T` 中 `stDynamicRange`/`stColorGamut` 字段
（ax_global_type.h:328-329），自填帧结构体时须与实际源一致。

## 6. 已启用 API（绑定层 15 个，官方 SDK 发布包 vo RPC 生成配置）

`AX_VO_Init` / `AX_VO_Deinit` / `AX_VO_SetPubAttr` / `AX_VO_GetPubAttr` /
`AX_VO_SetCSC` / `AX_VO_GetCSC` / `AX_VO_Enable` / `AX_VO_Disable` /
`AX_VO_VSYNC_RegCallbackFunc` / `AX_VO_VSYNC_UnRegCallbackFunc` / `AX_VO_SendFrame2Disp` /
`AX_VO_SetAspectRatio` / `AX_VO_GetAspectRatio` / `AX_VO_SetDataPinMap` / `AX_VO_GetDataPinMap`。
Layer/Chn/WBC/Batch API 及 CscMatrix 在绑定层未启用。
