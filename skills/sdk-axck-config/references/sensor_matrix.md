# AX615 常用 Sensor 模组参数与驱动特性矩阵 (Sensor Matrix)

本文档整理 AX615 平台通过标准接口接入测试验证的各类传感器模组（包含标准 RAW Sensor 与 YUV/AHD 转接模组）的驱动、参数配置与模式矩阵。

> **接入架构说明**：
> AX615 Demo 板本身无板载传感器。所有传感器均属于通过标准扩展接口外接的**可拔插/可替换模组**。
> 无论接入 RAW 模组还是 AHD 转接芯片（XS9950/TP9963 等），均通过统一的 I2C、GPIO、MIPI D-PHY 标准接口接入。

---

## 1. 传感器驱动特性表

| Sensor 模组型号 | 信号类型 | `sns_id` | 7-bit I2C 地址 | 动态链接库 (`sns_lib.lib`) | 驱动导出对象 (`sns_lib.obj`) | 典型模式 / 分辨率 | MIPI Lane 支持 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SC438HAI** | RAW10 (Bayer RGGB) | 8 | `0x30` (48) 或 `0x0` | `libsns_sc438hai.so` | `gSnssc438haiObj` | 2688x1520 @ 30fps (SDR/HDR) | 4-Lane / 2-Lane |
| **OS04D10** | RAW10 (Bayer RGGB) | 9 | `0x36` (54) / `0x10` / `0x0` | `libsns_os04d10.so` | `gSnsos04d10Obj` | 2560x1440 @ 25/30fps | 2-Lane |
| **SC431HAI** | RAW10 (Bayer RGGB) | 14 | `0x30` (48) 或 `0x0` | `libsns_sc431hai.so` | `gSnssc431haiObj` | 2560x1440 @ 25/30fps | 2-Lane / 4-Lane |
| **SC431AI** | RAW10 (Bayer RGGB) | 4 | `0x30` (48) 或 `0x0` | `libsns_sc431ai.so` | `gSnssc431aiObj` | 2560x1440 @ 25/30fps | 2-Lane |
| **SC533HAI** | RAW10 (Bayer RGGB) | 15 | `0x30` (48) 或 `0x0` | `libsns_sc533hai.so` | `gSnssc533haiObj` | 2880x1620 @ 25/30fps | 4-Lane / 2-Lane |
| **SC235HAI** | RAW10 (Bayer RGGB) | 11 | `0x30` (48) 或 `0x0` | `libsns_sc235hai.so` | `gSnssc235haiObj` | 1920x1080 @ 30fps | 2-Lane |
| **SC465SL** | RAW10 (Bayer RGGB) | 12 | `0x30` (48) 或 `0x0` | `libsns_sc465sl.so` | `gSnssc465slObj` | 2560x1440 @ 30fps | 2-Lane / 4-Lane |
| **MIS20S1** | RAW10 (Bayer RGGB) | 13 | `0x30` (48) 或 `0x0` | `libsns_mis20s1.so` | `gSnsmis20s1Obj` | 1920x1080 @ 30fps | 2-Lane |
| **XS9950** | YUV422 (AHD 解串器) | 6 | `0x30` (48) / `0x33` (51) | `libsns_xs9950.so` | `gSnsxs9950Obj` | 1920x1080 @ 25fps (1080P AHD) | 2-Lane |
| **TP9963** | YUV422 (AHD 解串器) | 7 | `0x45` (69) / `0x44` (68) | `libsns_tp9963.so` | `gSnstp9963Obj` | 1920x1080 @ 25fps | 2-Lane |

---

## 2. 模组配置与驱动加载铁律

1. **`sns_ahd` 标记区分**：
   - 普通 RAW 图像传感器模组：`sns_ahd: 0`，`sns_type: "mipi"`，`pixel_fmt: "raw10bpppkd"`。
   - AHD 模拟高清转接模组 / YUV 格式外设：`sns_ahd: 1`，`sns_type: "mipiyuv"`，`pixel_fmt: "yuv422uyvy"`。
2. **`dev_id` 硬件逻辑通道绑定**：
   - 外部接入的 RAW Sensor（通常走标准接口通道 0）：配置 `rx_dev: 0`，`dev_id: 0`，`pipe_id: 0`。
   - 外部接入的 YUV/AHD 转接模组：无论物理接在通道 0 还是通道 1，**`dev_id` 必须配置为 1 或 2**（AX615 SIF 硬件通道 dev 0 为 RAW 专用），`pipe_id: 1`。
3. **驱动导出符号检查**：
   - 动态链接库（.so）必须导出 `obj` 声明的全局 Sensor 结构体实例（如 `gSnsos04d10Obj`）。
