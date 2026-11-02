# AX615 / AXCK Sensor Settings 配置依据与驱动契约指南

## 1. 概述与核心结论

在 `camera-kit` 的配置文件（如 `sns_info.json`, `sns_info_dual.json` 等）中，`sns_attr` 包含了关键配置字段：
```json
"settingindex_des": "[none, sdr, hdr] refer to <sensor>_settings.h",
"settingindex": [-1, 1, 2]
```

很多工程师容易将 `settingindex` 误认为是一个“随意指定的编号”或者“驱动内部的无关参数”。
**核心结论**：`settingindex` 是 **Sensor 厂家 FAE 提供的固化寄存器序列索引（Hardware Timings & Register Array Preset）**。
它在驱动中是一个强耦合的枚举值，**严格决定并绑定了 8 大底层硬件要素**：
1. **输出分辨率（Width × Height）**
2. **工作模式（SDR / Linear vs HDR_2DOL）**
3. **数据位宽（RAW10 vs RAW12）**
4. **Bayer 格式（RGGB）**
5. **硬件帧率基线与上限（如 25fps, 30fps, 50/60fps）**
6. **MIPI PHY 物理 Lane 数量（4-Lane vs 2-Lane）**
7. **输入 MCLK 频率（24MHz vs 27MHz）**
8. **单 Lane 高速数据速率（MIPI Data Rate，如 360M, 630M, 720M, 900M, 1080M, 1188M 等）**

---

## 2. SettingIndex 的加载机理与运行时调用链

### 2.1 Camera-Kit 应用层解析（`axck_sns_info.c`）
在 `camera-kit/service/mid/axck_camera/axck_sns_info.c` 的 `GetSnsAttr` 函数中：
```c
cJSON* pMap = cJSON_GetObjectItem(pCfg, "settingindex");
if (AX_NULL != pMap && cJSON_IsArray(pMap)) {
    for (AX_S32 nIdx = 0; nIdx < cJSON_GetArraySize(pMap); ++nIdx) {
        cJSON* pTemp = cJSON_GetArrayItem(pMap, nIdx);
        pObjt->zSnsSettingIndex[nIdx] = (AX_U8)pTemp->valuedouble;
    }

    // 根据 sns_mode (1: SDR/Linear, 2: HDR) 选取对应 settingindex
    if (pAttr->eSnsMode == AX_SNS_HDR_2X_MODE) {
        pAttr->nSettingIndex = pObjt->zSnsSettingIndex[2];
    } else {
        pAttr->nSettingIndex = pObjt->zSnsSettingIndex[1];
    }
} else {
    pAttr->nSettingIndex = 0;
}
```
- `settingindex` 数组固定为 3 个元素：`[none, sdr, hdr]`。
- 下标 0 为占位保留（通常为 `-1`）。
- 下标 1 为 SDR 模式下的 `settingindex`。
- 下标 2 为 HDR 模式下的 `settingindex`。

### 2.2 驱动层生效机制（以 `sc438hai.c` 为例）
当 ISP 初始化调用 `sc438HAI_sensor_set_mode` 时：
```c
// 1. 默认兜底：若未显式指定 settingindex，驱动根据 width, height, raw, mode 进行匹配
if (sns_mode->nWidth == 2688 && sns_mode->nHeight == 1520 && ...) {
    sns_setting_index = e_SC438HAI_2688X1520_LINEAR_10bit_RGGB_30FPS_SDR_4LANE_27M_900Mbps;
}

// 2. 显式覆盖（优先）：如果应用层传入的 nSettingIndex > 0，则直接强制使用该 Index！
if (sns_mode->nSettingIndex > 0) {
    sns_setting_index = sns_mode->nSettingIndex;
}

// 3. 校验并提取硬件基准帧率
if (sns_setting_index == e_SC438HAI_2688X1520_HDR_10bit_RGGB_25FPS_2LANE_24M_1188Mbps) {
    setting_fps = 25.0f;
} else {
    setting_fps = 30.0f;
}
```
在 `sc438HAI_write_settings` 中：
```c
// 根据 sns_obj->eImgMode (即 settingindex) 选取真实的 camera_i2c_reg_array 数组并逐个写入 Sensor
sc438HAI_select_setting(nPipeId, &setting, &reg_cnt);
for (i = 0; i < reg_cnt; i++) {
    sc438HAI_write_register(nPipeId, (setting + i)->addr, (setting + i)->value);
}
```

---

## 3. 各主流 Sensor SettingIndex 硬件参数字典

驱动头文件定义在 `msp/component/isp_proton/sensor/driver/<sensor>/<sensor>_settings.h` 中。

### 3.1 SC438HAI (`sc438hai_settings.h`)
| Index | 枚举常量 | 分辨率 | 模式 | 位宽 | 帧率 | Lane数 | MCLK | MIPI速率 |
|---|---|---|---|---|---|---|---|---|
| 1 | `e_SC438HAI_2688X1520_LINEAR_10bit_RGGB_30FPS_SDR_4LANE_27M_900Mbps` | 2688x1520 | SDR | RAW10 | 30fps | 4 Lane | 27MHz | 900Mbps |
| 2 | `e_SC438HAI_2688X1520_LINEAR_10bit_RGGB_30FPS_HDR_4LANE_27M_756Mbps` | 2688x1520 | HDR | RAW10 | 30fps | 4 Lane | 27MHz | 756Mbps |
| 3 | `e_SC438HAI_2688X1520_LINEAR_10bit_RGGB_30FPS_2LANE_24M_900Mbps` | 2688x1520 | SDR | RAW10 | 30fps | 2 Lane | 24MHz | 900Mbps |
| 4 | `e_SC438HAI_2688X1520_HDR_10bit_RGGB_25FPS_2LANE_24M_1188Mbps` | 2688x1520 | HDR | RAW10 | 25fps | 2 Lane | 24MHz | 1188Mbps |
| 5 | `e_SC438HAI_2688X1520_SDR_10bit_RGGB_30FPS_4LANE_27M_720Mbps` | 2688x1520 | SDR | RAW10 | 30fps | 4 Lane | 27MHz | 720Mbps |
| 6 | `e_SC438HAI_2688X1520_HDR_10bit_RGGB_30FPS_4LANE_27M_720Mbps` | 2688x1520 | HDR | RAW10 | 30fps | 4 Lane | 27MHz | 720Mbps |
| 7 | `e_SC438HAI_2688X1520_SDR_10bit_RGGB_30FPS_2LANE_27M_900Mbps` | 2688x1520 | SDR | RAW10 | 30fps | 2 Lane | 27MHz | 900Mbps |
| 8 | `e_SC438HAI_2688X1520_HDR_10bit_RGGB_25FPS_2LANE_27M_1188Mbps` | 2688x1520 | HDR | RAW10 | 25fps | 2 Lane | 27MHz | 1188Mbps |

> **配置依据示例**：
> - 单摄 4-Lane 27M MCLK 方案：配 `[-1, 1, 2]`。
> - 双摄 2-Lane 24M MCLK 方案：配 `[-1, 3, 4]`。
> - 双摄 2-Lane 27M MCLK 方案：配 `[-1, 7, 8]`。

---

### 3.2 SC431HAI (`sc431hai_settings.h`)
| Index | 枚举常量 | 分辨率 | 模式 | 位宽 | 帧率 | Lane数 | MCLK | MIPI速率 |
|---|---|---|---|---|---|---|---|---|
| 1 | `e_SC431HAI_MIPI_24M_630MBPS_2LANE_2560x1440_10BIT_SDR_25FPS` | 2560x1440 | SDR | RAW10 | 25fps | 2 Lane | 24MHz | 630Mbps |
| 2 | `e_SC431HAI_MIPI_24M_1080MBPS_2LANE_2560x1440_10BIT_HDR_25FPS` | 2560x1440 | HDR | RAW10 | 25fps | 2 Lane | 24MHz | 1080Mbps |
| 3 | `e_SC431HAI_MIPI_27M_315MBPS_4LANE_2560x1440_10BIT_SDR_30FPS` | 2560x1440 | SDR | RAW10 | 30fps | 4 Lane | 27MHz | 315Mbps |
| 4 | `e_SC431HAI_MIPI_27M_652MBPS_4LANE_2560x1440_10BIT_HDR_30FPS` | 2560x1440 | HDR | RAW10 | 30fps | 4 Lane | 27MHz | 652Mbps |

> **配置依据**：
> - 4-Lane 27M 30FPS 方案：配置 `[-1, 3, 4]`。
> - 2-Lane 24M 25FPS 方案：配置 `[-1, 1, 2]`。

---

### 3.3 SC431AI (`sc431ai_settings.h`)
SC431AI 引入了特殊编号区段（`0x20 = 32` 起始）：
| Index | 枚举常量 | 分辨率 | 模式 | 帧率 | Lane数 | MCLK | MIPI速率 |
|---|---|---|---|---|---|---|---|
| 1 | `e_SC431AI_2688X1520_LINEAR_10bit_RGGB_30FPS_4LANE_24M_360Mbps` | 2688x1520 | SDR | 30fps | 4 Lane | 24MHz | 360Mbps |
| 2 | `e_SC431AI_2688X1520_HDR_10bit_RGGB_30FPS_4LANE_24M_720Mbps` | 2688x1520 | HDR | 30fps | 4 Lane | 24MHz | 720Mbps |
| 32 | `e_SC431AI_setting_special_idx` | 保留基准 | - | - | - | - | - |
| 33 | `e_SC431AI_2560X1440_LINEAR_10bit_RGGB_30FPS_2LANE_27M_720Mbps` | 2560x1440 | SDR | 30fps | 2 Lane | 27MHz | 720Mbps |
| 34 | `e_SC431AI_2688X1520_LINEAR_10bit_RGGB_25FPS_2LANE_24M_720Mbps` | 2688x1520 | SDR | 25fps | 2 Lane | 24MHz | 720Mbps |
| 35 | `e_SC431AI_2688X1520_HDR_10bit_RGGB_25FPS_2LANE_24M_1120Mbps` | 2688x1520 | HDR | 25fps | 2 Lane | 24MHz | 1120Mbps |

> **深度释疑（为什么 p105 工程是 `[-1, 33, 0]`？）**：
> p105 板使用 2-Lane 物理连线，分辨率裁切为 2560x1440，且板载晶振提供 27MHz MCLK。因此必须选用 Index `33`，若误填 `1`，驱动会按照 4-Lane 24M 下发初始化寄存器，直接导致 MIPI 接收断流和时钟失锁！

---

### 3.4 OS04D10 (`os04d10_settings.h`)
| Index | 枚举常量 | 分辨率 | 模式 | 帧率 | Lane数 | MCLK | MIPI速率 |
|---|---|---|---|---|---|---|---|
| 0 | 默认匹配（驱动内部默认） | 2560x1440 | Linear | 30fps | 2 Lane | 24MHz | 720Mbps |
| 1 | `e_OS04D10_2lane_2560x1440_10bit_Linear_30fps` | 2560x1440 | Linear | 30fps | 2 Lane | 24MHz | 720Mbps |

> **说明**：OS04D10 在单/双摄中多用于 2-Lane 24M 30FPS，填 `[-1, 0, 0]` 或 `[-1, 1, 0]`。

---

### 3.5 MIS20S1 (`mis20s1_settings.h`)
| Index | 枚举常量 | 分辨率 | 模式 | 位宽 | 帧率 | Lane数 | 特性 |
|---|---|---|---|---|---|---|---|
| 0 | `e_camera_i2c_reg_array_MIS20S1_MIPI_2LANE_1920x1080_SDR_RAW12_30FPS` | 1920x1080 | SDR | RAW12 | 30fps | 2 Lane | 标准 SDR |
| 1 | `e_camera_i2c_reg_array_MIS20S1_MIPI_2LANE_1920x1080_HDR_RAW12_30FPS` | 1920x1080 | HDR | RAW12 | 30fps | 2 Lane | 标准 HDR |
| 2 | `e_camera_i2c_reg_array_MIS20S1_MIPI_2LANE_1920x1080_SDR_RAW10_30FPS` | 1920x1080 | SDR | RAW10 | 30fps | 2 Lane | RAW10 |
| 3 | `e_camera_i2c_reg_array_MIS20S1_MIPI_2LANE_1920x1080_HDR_RAW10_30FPS` | 1920x1080 | HDR | RAW10 | 30fps | 2 Lane | RAW10 |
| 4 | `e_camera_i2c_reg_array_MIS20S1_MIPI_2LANE_1920x1080_SDR_RAW12_60FPS` | 1920x1080 | SDR | RAW12 | 60fps | 2 Lane | 60fps 高帧 |
| 5 | `e_MIS20S1_MIPI_2LANE_1920x1080_SDR_RAW12_30FPS_VBLANK6MS` | 1920x1080 | SDR | RAW12 | 30fps | 2 Lane | VBlank 6ms 优化 |
| 6 | `e_MIS20S1_MIPI_2LANE_1920x1080_HDR_RAW12_30FPS_VBLANK6MS` | 1920x1080 | HDR | RAW12 | 30fps | 2 Lane | VBlank 6ms 优化 |

> **配置依据**：在 demo 的 `sns_info_mis20s1.json` 中配置的是 `[-1, 5, 6]`，正是启用了防抖动/低功耗的 6ms VBlank 优化序列！

---

### 3.6 XS9950 (AHD 芯片, `xs9950_settings.h`)
| Index | 枚举常量 | 分辨率 | 接口 | 帧率 |
|---|---|---|---|---|
| 0 | `e_XS9950_setting_sel_min` | - | - | - |
| 1 | `e_XS9950_AHD_FHD_1920x1080_LINEAR_RGGB_25FPS_2LANE` | 1920x1080 | MIPI 2-Lane | 25fps |
| 2 | `e_XS9950_AHD_FHD_1920x1080_LINEAR_RGGB_30FPS_2LANE` | 1920x1080 | MIPI 2-Lane | 30fps |
| 3 | `e_XS9950_AHD_HD_1280x720_LINEAR_RGGB_25FPS_2LANE` | 1280x720 | MIPI 2-Lane | 25fps |
| 4 | `e_XS9950_AHD_HD_1280x720_LINEAR_RGGB_30FPS_2LANE` | 1280x720 | MIPI 2-Lane | 30fps |
| 33 | `e_XS9950_AHD_FHD_1920x1080_LINEAR_RGGB_25FPS_BT656` | 1920x1080 | DVP / BT656 | 25fps |
| 34 | `e_XS9950_AHD_FHD_1920x1080_LINEAR_RGGB_30FPS_BT656` | 1920x1080 | DVP / BT656 | 30fps |

> **配置依据**：后拉 AHD 模组根据 PAL 制（25fps）还是 NTSC 制（30fps），以及走 MIPI 还是 BT656 进行选取（如 1080P@25fps MIPI 配 `[-1, 1, 0]`）。

---

## 4. 自动化校验的检查规则 (Validation Iron Rules)

配置校验器 `axck_config_validator.py` 在检查 `sns_info.json` 时，必须实施以下交叉校验：
1. **模式合法性**：`sns_mode=1` (SDR) 时，`settingindex[1]` 必须匹配目标 SDR 序列且 `>= 0`；`sns_mode=2` (HDR) 时，`settingindex[2]` 必须匹配目标 HDR 序列且 `> 0`。
2. **时钟一致性**：若 setting 说明绑定了 `24M`，而 `sns_clk.clk_rate` 配成了 `"27m"`，必须拦截报错。
3. **分辨率一致性**：若 setting 表为 `2560x1440`（如 SC431AI 的 index 33），而 `sns_attr.width/height` 写成 `2688x1520`，必须拦截报错。
4. **Lane 数与 PHY 匹配**：若双摄模式下，两个 Sensor 都配置了 4-Lane 的 settingindex（例如 SC438HAI Index 1），必须拦截报错，因为 AX615 物理上只有 4 条数据 Lane，双摄必须且只能是 2-Lane + 2-Lane！
