# AX615 图像插值与超分放大实战指南 (Interpolation Guide)

本文档归纳 AX615 / AXERA camera-kit (AXCK) 平台在 Sensor 原生分辨率基础上的主码流/辅码流插值（Upscaling / Interpolation）配置原理、级联拓扑调整、CMM 内存池联动预算与板端实证数据。

---

## 1. 业务场景与技术背景

在车载行车记录仪、安防 IPC 等实际产品中，出于产品差异化或清晰度规格需求，常使用 4M 原生 Sensor（如 OS04D10: 2560x1440, SC438HAI: 2688x1520）通过硬件图像处理器（IVPS）插值放大输出 3K/5M（如 2880x1620, 16:9）的超分辨率视频流并进行 H.264/H.265 硬件编码。

AX615 多媒体架构由 **VIN -> IVPS -> VENC** 级联组成，插值放大的核心原则是：**前端保持原生捕获，中端硬件缩放放大，后端编码与缓冲池全面匹配。**

---

## 2. 拓扑与关键参数映射

以 **OS04D10 (2560x1440@30fps)** 插值放大至 **2880x1620@30fps** 为例：

### 2.1 缩放比与硬件对齐约束
- **水平缩放比**：$2880 / 2560 = 1.125\times$
- **垂直缩放比**：$1620 / 1440 = 1.125\times$
- **16 字节对齐约束**：
  - 目标宽度：$2880 \pmod{16} == 0$（严格满足 VENC 硬件编码对齐）
  - 目标高度：$1620 \pmod{2} == 0$（严格满足 YUV420SP NV12 对齐）

### 2.2 配置文件修改清单

以 **OS04D10 (2560x1440@30fps)** 插值放大至 **2880x1620@30fps (3K)** 或 **3840x2160@25fps (4K)** 为例：

| 配置文件 | 配置项 | 原始值 (Native 2.5K) | 插值 3K (2880x1620) | 插值 4K (3840x2160) | 作用说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`sns_info.json`** | `sns_attr.width/height` | `2560x1440` | `2560x1440` (不变) | `2560x1440` (不变) | SIF/VIN 必须以 Sensor 原生时序接收 RAW10 |
| **`ppl_config.json`** | `ivps[0].filter[0]` | `2560x1440` | `2560x1440` (不变) | `2560x1440` (不变) | IVPS 输入 Filter 接收 ISP 原生尺寸 |
| **`ppl_config.json`** | `ivps[0].output[0].filter[0].width/height` | `2560x1440` | **`2880x1620`** | **`3840x2160`** | IVPS 主通道由 SCL 引擎插值放大 |
| **`ppl_config.json`** | `ivps[0].output[0].filter[0].engine` | `"scl"` | **`"scl"`** | **`"scl"`** | 必须指定 `scl` (缩放放大引擎) |
| **`ppl_config.json`** | `ivps[0].output[0].filter[0].scl_type` | `2` | **`2`** | **`2`** | 高质量平滑插值滤波算法 |
| **`ppl_config.json`** | `cache[0].vout.width/height` | `2560x1440` | **`2880x1620`** | **`3840x2160`** | 主视频缓存输出与 VENC0 编码器对齐 |
| **`app_config.json`** | `pool.private[0]` | `2560x1440` | `2560x1440` (不变) | `2560x1440` (不变) | PIPE0 私有 RAW 缓冲，保持 Sensor 原生尺寸 |
| **`app_config.json`** | `pool.common[0]` | `2560x1440` | `2560x1440` (或2880) | `2560x1440` (保持原生) | VIN->IVPS 间公共帧缓冲保持 Sensor 原生尺寸 |
| **`app_config.json`** | `pool.common[1]` | `2560x128` | **`2880x128`** | **`3840x128`** | **SW_LOW_MEM (HSK ring)** 切片缓冲宽度必须与输出 Stride 对齐 |
| **`app_config.json`** | `venc[0].bitrate` | `20480` | `4096` | `4096` | 默认编码码率优化配置 (4Mbps) |


---

## 3. CMM 内存池 (Pool) 联动预算机制 (Critical)

如果仅修改了 IVPS 和 VENC 分辨率，而遗漏了 `app_config.json` 中的 `pool.common`，会导致系统初始化时由于无法获取足够尺寸的 VB 内存块而抛出错误码 **`0x80050004` (AX_ERR_POOL_UNEXIST / 内存池耗尽)**。

### 3.1 主流 FBC 缓冲池 (`pool.common[0]`)
- **配置规则**：`width: 2880, height: 1620, pixel_format: 3 (NV12), blk: 2`
- **压缩属性**：`compress: {mode: 2, level: 10}`（AXERA 专有 FBC 压缩）
- **驱动内核分配大小**：通过 `/proc/ax_proc/pool` 可查实，单块分配大小由原本的 3.7MB 扩展至约 4.78MB (`4781056` 字节)。

### 3.2 低内存切片编码环形缓冲 (`SW_LOW_MEM`，`pool.common[1]`)
- **配置规则**：`width: 2880, height: 128, pixel_format: 3, blk: 1, compress: {mode: 2, level: 4}`
- **铁律**：`SW_LOW_MEM` 用于 VENC 切片流式编码以极大降低 DDR 占用。其 `width` 必须与主视频流宽度保持严格一致（2880）。若宽度仍为 2560，切片编码行跨度不一致将导致底层行缓冲区越界或硬件丢帧。

---

## 4. 静态工具链验证与门禁 (Tooling Guard)

`sdk-axck-config` 工具链内置了插值拓扑与内存池匹配规则的自动校验：

### 4.1 拓扑审查 (Inspect)
执行 inspect 时自动识别插值放大通道并打印放大倍率：
```bash
python3 scripts/cli.py inspect -c /opt/bin/res/config
```
输出片段示例：
```text
  - Pipeline [front] (ENABLED): 1 IVPS groups
      • IVPS Group 0 (In: 2560x1440):
          - Chn 0: scl 2880x1620 @ 30fps [Scale Up 1.12x1.12]
          - Chn 1: scl 1280x720 @ 0fps
```

### 4.2 规则校验 (Validate)
执行 validate 会进行强一致性检查：
```bash
python3 scripts/cli.py validate -c /opt/bin/res/config
```
- 若 IVPS 输出大于输入，自动检查 `engine` 是否为 `scl` 或 `vpp`。
- 自动校验 `cache[0].vout` 的 `2880x1620` 是否在 `pool.common` 中存在完全吻合的条目。
- 自动校验是否存在 `2880x128` 的低内存切片缓冲池，缺失则报 Warning。

---

## 5. 板端运行实测验证依据 (Empirical Evidence)

在 AX615 + OS04D10 真实开发板上部署该插值配置后，通过 Linux 驱动 procfs 验证各子系统运行指标：

### 5.1 IVPS 硬件插值状态 (`/proc/ax_proc/ivps`)
```text
======================= Grp 0 =======================
Engine: VPP0, InFps: 29.99, OutFps: 29.98
Filter 0: In: 2560x1440, Format: NV12
Chn 0: Out: 2880x1620, Format: NV12, Status: Active
```
*结论：IVPS 成功稳定执行 2560x1440 -> 2880x1620 缩放插值，帧率满帧 30fps。*

### 5.2 VENC 硬件编码状态 (`/proc/ax_proc/venc`)
```text
ChnId: 0, State: RUNNING, Format: H265, Width: 2880, Height: 1620
Send2FwFps: 30.7, OutFps: 29.7, EncSucCnt: 243, EncFailCnt: 0
```
*结论：VENC Chn 0 以 2880x1620 分辨率满速编码，编码成功率 100%，零丢帧。*

### 5.3 录像封装状态
系统 `mp4mux` 录像封装模块正常启动，并写入 TF 卡：
```text
mp4mux_open: bHevc 1, Width: 2880, Height: 1620, FrameRate: 30
File /mnt/tfcard/Normal/F/20260917_xxxxxx.mp4 generated successfully.
```
