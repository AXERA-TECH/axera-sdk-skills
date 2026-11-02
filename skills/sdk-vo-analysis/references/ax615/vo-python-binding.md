# AX615 VO Python（MicroPython RPC）调用约定摘要

> 本文件是 AX615 VO Python 侧绑定层（官方 SDK 发布包自动生成的 RPC 封装与 natmod 绑定）
> 的**客户可见调用约定摘要**（不含逐字产物代码）。SDK 版本 **V3.14.0**；
> 版本标注：**SDK V3.14.0 实现行为，需按版本核验**。
> 客户 SDK 版本与内化版本不同时，一律以客户实际封装为准，摘要仅用于核对调用形状与命名。

## 1. 模块与命名（客户可见）

| 名称 | 角色 |
|---|---|
| `mdk_vo` | Linux 侧 mdk 顶层 VO 模块名（来自 VO 的 PC 端 RPC 封装） |
| `uax_vo_api` | MicroPython natmod 模块名（由 `ax_vo_api.h` 头文件自动生成，承载 `AX_VO_*` 函数） |
| `ax_vo_api` | 结构体/枚举定义模块（如 `AX_VO_PUB_ATTR_T`、`AX_VIDEO_FRAME_T`、`AX_VO_CSC_T`、`AX_VO_ASPECT_RATIO_T`、`AX_VO_PIN_DATA_BUTT`） |
| `common.new` | 结构体实例化辅助：`new(AX_VO_PUB_ATTR_T)`，非 C 式初始化 |

Python 侧典型 import 形状：

```python
from uax_vo_api import AX_VO_Init, AX_VO_SetPubAttr, AX_VO_GetPubAttr, ...
from ax_vo_api import AX_VO_PUB_ATTR_T, AX_VO_CSC_T, AX_VIDEO_FRAME_T
```

## 2. 包装函数命名约定

- 每个已启用 API 提供 `Call_AX_VO_*` 包装（PC 端 RPC 封装）；MicroPython 侧调用 `mdk_vo` 模块的同名包装，如
  `MDK.Call_AX_VO_SendFrame2Disp(dev, packet, timeout)`。
- **Getter 统一返回 `(s32Ret, stXxx)` 元组**：例如 `Call_AX_VO_GetPubAttr(VoDev)` → `(s32Ret, stPubAttr)`，
  `Call_AX_VO_GetCSC(VoDev)`、`Call_AX_VO_GetAspectRatio(VoDev)`、`Call_AX_VO_GetDataPinMap(VoDev)` 同理。
  客户代码若只接一个返回值，是常见用法错误，先核对。
- 其余 API 返回 `s32Ret`（0 成功，非 0 为错误码）。

## 3. 已启用 API（15 个，客户 Python 侧可直接调用）

`AX_VO_Init` / `AX_VO_Deinit` / `AX_VO_SetPubAttr` / `AX_VO_GetPubAttr` / `AX_VO_SetCSC` /
`AX_VO_GetCSC` / `AX_VO_Enable` / `AX_VO_Disable` / `AX_VO_VSYNC_RegCallbackFunc` /
`AX_VO_VSYNC_UnRegCallbackFunc` / `AX_VO_SendFrame2Disp` / `AX_VO_SetAspectRatio` /
`AX_VO_GetAspectRatio` / `AX_VO_SetDataPinMap` / `AX_VO_GetDataPinMap`

**未启用**（绑定层未导出，Python 侧不可调用）：`AX_VO_EnumMode`、Layer 系列、Chn 系列、WBC 系列、
Batch 系列以及 `Call_AX_VO_CscMatrix`。客户在 Python 侧遇到这些问题时，排查手段以 C API 用法、
proc 与日志为准。

## 4. 关键参数形状（客户可见）

- **DataPinMap**：数据线数组以 uctypes 定义（`array` + `UINT8`，长度 `AX_VO_PIN_DATA_BUTT`），
  逐位赋值后调用 `AX_VO_SetDataPinMap(VoDev, stVoDataLineSel)`。
- **VSYNC 回调**：回调结构体含回调函数指针与私有数据指针，注册/注销成对调用
  （`AX_VO_VSYNC_RegCallbackFunc(VoDev, stCallbackFunc)` / `AX_VO_VSYNC_UnRegCallbackFunc(VoDev, stCallbackFunc)`）。
- **送帧**：`AX_VO_SendFrame2Disp(VoDev, stVoFrame, s32MS)`，`stVoFrame` 为 `AX_VIDEO_FRAME_T` 实例
  （须填物理地址；池内存场景同时回填 block id）。
- **CSC**：`AX_VO_SetCSC(VoDev, stVideoCSC)`，`stVideoCSC` 为 `AX_VO_CSC_T` 实例。

## 5. 典型送帧节拍（客户可见约定）

VO 送帧在客户 Python 应用中通常按 VSYNC 节拍或按显示刷新率送帧；超时参数建议取阻塞或带超时值
（正值，单位 ms），**不要**用 0（非阻塞）配高帧率循环送帧——这会立即打满输入 FIFO。
具体语义见 [vo-sdk-behavior-notes.md](vo-sdk-behavior-notes.md) 第「SendFrame2Disp」节。

## 6. 客户侧核对清单

1. Getter 是否按 `(s32Ret, obj)` 元组接收；
2. 是否调用了未导出的 API（EnumMode/Layer/Chn/WBC/Batch）；
3. DataPinMap 数组长度与 `AX_VO_PIN_DATA_BUTT` 是否一致；
4. 帧结构体是否填了物理地址与 block id；
5. 客户 SDK 版本与本文档版本的差异（**SDK V3.14.0 实现行为，需按版本核验**）。
