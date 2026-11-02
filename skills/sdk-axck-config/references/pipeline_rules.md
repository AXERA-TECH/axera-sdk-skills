# AX615 Pipeline 级联、分辨率对齐与编码冲突铁律 (Pipeline Rules)

本文档归纳 AX615 / AXERA 平台的软件架构、多媒体子系统（VIN、IVPS、VENC、JENC）硬性限制与对齐规则。

---

## 1. 级联模式与系统带宽约束 (`vin_ivps_mode`)

在 `app_config.json` 的 `camera[]` 数组中，`vin_ivps_mode` 决定了图像从 ISP/VIN 送入 IVPS 的硬件传输通路：

| 模式值 | 枚举定义 | 工作原理与特点 | 限制与铁律 |
| :--- | :--- | :--- | :--- |
| **0** | `AX_ITP_OFFLINE_VPP` | 离线内存模式。VIN 将图像存入 DDR，IVPS 再从 DDR 读图。 | 占用 DDR 带宽最大，但最灵活，支持任意旋转、复杂 Dewarp。 |
| **1** | `AX_GDC_ONLINE_VPP` | GDC 在线直连 VPP。硬件内部流式处理。 | **推荐默认模式**。兼顾低时延与 Dewarp/旋转能力。 |
| **2** | `AX_ITP_ONLINE_VPP` | ITP 硬件行缓存直接送入 VPP。时延最低、不占 DDR。 | **⚠️ 严禁 90°/270° 大分辨率旋转**。因 ITP 内部 Line Buffer 无法暂存整帧做转置，会导致硬件溢出或花屏。 |

---

## 2. 几何变换与旋转翻转 (`rotate`, `mirror`, `flip`)

- `rotate`: 0: 0°, 1: 90°, 2: 180°, 3: 270°。
- **镜像与翻转**: `mirror: 1`（水平镜像），`flip: 1`（垂直翻转）。
- **旋转尺寸对调**: 当 `rotate` 为 1 或 3 时，输出图像的宽和高必须在后续 IVPS 通道与 VENC 中调换（例如 1920x1080 变为 1080x1920）。
- **AHD 倒车后视规范**: 模拟高清倒车影像（如 XS9950）通常作为车内流媒体后视镜使用，默认配置必须带 `mirror: 1` 以符合驾驶员视觉习惯。

---

## 3. 分辨率对齐与内存跨距 (`Stride`) 约束

1. **宽高必须为偶数**:
   - YUV420SP (NV12) 色度采样（UV）为 2x2 共享，任何输入输出宽高出现奇数（如 `width % 2 != 0`）将直接触发驱动内核断言或驱动拒绝启动。
2. **16 字节对齐 (16-Byte Stride Alignment)**:
   - 绝大多数硬件视频编码器（VENC H.264/H.265）要求输入宽度为 16 的整数倍（`width % 16 == 0`）。
   - 若宽度非 16 对齐（例如宽 200、宽 1080 等），必须在 IVPS 输出端开启 Stride 补偿（内存行对齐填充），否则编码器会出现绿边、斜纹或内存越界。

---

## 4. VENC 与 JENC 通道号命名空间冲突规避 (AX615 Iron Rule)

在 AX615 硬件架构中，**VENC (Video Encoder) 与 JENC (JPEG Encoder) 共享底层的 0~15 硬件通道**。

### 🚨 绝对禁止：
- 视频流占用的 `enc_chnl`（如主摄录像 Chn 0、辅码流 Chn 1、后摄录像 Chn 2、后摄辅码流 Chn 3）与 JPEG 拍照/缩略图占用的 `enc_chnl` **重叠**！
- 若 `ppl_config.json` 中配置了 `front.cache[0].thumb.enc_chnl: 0`，同时该 cache 的视频编码也是 `enc_chnl: 0`，系统在初始化抓拍模块时会直接强杀或覆盖正在录像的通道，导致抓拍死锁或视频录像中断。

### 推荐分配规范：
- **单摄场景**：
  - 视频流：Chn 0 (Main), Chn 1 (Sub)
  - 拍照/抓拍 JENC：Chn 3 (Full Snap)
  - 抓拍缩略图 JENC：Chn 4 (Thumb)
- **双摄场景**：
  - 前摄视频流：Chn 0 (Front Main), Chn 1 (Front Sub)
  - 后摄视频流：Chn 2 (Rear Main), Chn 3 (Rear Sub)
  - 前摄抓拍 JENC：Chn 4
  - 后摄抓拍 JENC：Chn 5
  - 缩略图 JENC：Chn 6 / Chn 7

---

## 5. IVPS 图像缩放与插值放大铁律 (Interpolation & Upscaling)

在车载记录仪与 IPC 项目中，常需要通过 IVPS 将低像素 Sensor（如 4M 2560x1440）插值放大输出更高规格的码流（如 2880x1620 或 3840x2160）：

1. **引擎分配强制约束**：
   - IVPS 进行图像插值放大（Upscaling，即输出宽高任一大于输入宽高）时，其硬件 engine 字段**必须显式指定为 `scl` 或 `vpp`**。
   - 严禁在插值通道使用 `tdp` 或未配置 engine 运行放大逻辑，否则驱动会报告非法引擎或触发硬件异常。
   - `scl_type` 建议配置为 `2`（高阶双三次/保边插值平滑算法），获得最佳主观清晰度。
2. **硬件 16 字节对齐铁律**：
   - 插值后的目标分辨率宽度必须为 16 的整数倍（例如 2880 % 16 == 0），高度必须为偶数。
3. **CMM Pool 级联联动**：
   - 进行插值后，`app_config.json` 中的 `pool.common` 必须同步增加或修改对应分辨率的 YUV 缓冲池及低内存切片缓冲池（SW_LOW_MEM），否则将抛出 `0x80050004` (内存池耗尽)。
