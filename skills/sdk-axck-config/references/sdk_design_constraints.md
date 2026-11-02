# AX615 官方 SDK 核心设计限制与拓扑铁律精要

本文档全面提取自官方文档：
- `12 - AX Sensor 调试指南.docx`
- `10 - AX VIN 开发参考.docx`
- `11 - AX MIPI 开发参考.docx`
- `46 - AXCK 多媒体开发指南.docx`

---

## 1. MIPI D-PHY 硬件限制与 Lane 分布（SDK 11 文档）

### 1.1 芯片物理规格差异
- **AX650A/N**：拥有 8 个独立的 PHY，每个 PHY 包含 1 个 Clk Lane 和 2 个 Data Lane。
- **AX615 / AX630C / AX620Q**：**仅拥有 1 个物理综合 PHY，全芯片总共只有 2 个 Clk Lane 和 4 个 Data Lane！**
  - 单摄 4-Lane：将这单个 PHY 的全部 4 个 Data Lane 聚合给单个 Sensor。
  - 双摄 2-Lane：将该 PHY 拆分为两组（物理 Lane 0~2 分配给 Sensor 0，Lane 3~5 分配给 Sensor 1）。
  - **硬件限制**：AX615 **绝对无法支持同时接入两个 4-Lane 摄像头**，亦不支持 3 路 MIPI CSI 同时输入（AX615 最大 2 路 MIPI，或 2 路 MIPI + 1 路 BT656）。
  - **不支持 sub-LVDS / SLVS**：官方文档明文指出 AX615 不支持 LVDS / sub-LVDS 接口。
  - **最大速率限制**：D-PHY 模式下每 Lane 速率上限为 **2.5 Gbps**。

### 1.2 物理 Lane 组间与组内约束
- **组 0 (Lane 0 ~ 2)**：包含 Data Lane 0 (Pin 42/43), Data Lane 1 (Pin 44/45), Clock Lane 0 (Pin 46/47)。
  - 组内 3 个 Lane 允许做硬件 Swap，但 Clock Lane 只能在 0~2 之间，Data Lane 只能在 0~2 之间。
- **组 1 (Lane 3 ~ 5)**：包含 Data Lane 2 (Pin 49/50), Data Lane 3 (Pin 51/52), Clock Lane 1 (Pin 53/54)。
  - 组内 3 个 Lane 允许做硬件 Swap，Clock Lane 只能在 3~5 之间，Data Lane 只能在 3~5 之间。
- **铁律**：Clock 0 不能跨到 Lane 3~5，Clock 1 也不能跨到 Lane 0~2。在 4-Lane 模式下，Clock Lane 推荐配置为 `[2, 5]`（使用 Clk0=2，虚拟映射 Clk1=5）。

---

## 2. Sensor 调试与行长（HTS）硬件约束（SDK 12 文档 5.9 节）

### 2.1 SIF 处理能力与最小行长公式
AX 芯片 SIF（Sensor Interface）硬件时钟与像素处理能力存在物理上限。为了防止 SIF FIFO 溢出导致硬件异常或丢包，Sensor 输出的时序（HTS/HBLANK）必须严格满足最小行长约束：

| 平台 | SIF 硬件主频 | SIF 像素吞吐能力 | 最小行长（单位：微秒 us） |
|---|---|---|---|
| **AX650** | 624 MHz | 1 cycle 处理 2 pixel | `width / 624 / 2` |
| **AX620Q / AX630C**| 416 MHz | 1 cycle 处理 1 pixel | `width / 412` |
| **AX615** | **367 MHz** | **1 cycle 处理 2 pixel** | **`width / 367 / 2`** |

> **计算示例（AX615 平台 4M 分辨率 2688x1520）**：
> - 图像有效宽度 `width = 2688`。
> - 最小行长 `min_line_time = 2688 / 367 / 2 ≈ 3.662 us`。
> - **物理限制**：如果 Sensor 厂家提供的 setting 中 HTS（Total Horizontal Size）配得过小，导致单行时间小于 3.662 微秒，SIF 将来不及处理行内像素，产生前端溢出。

### 2.2 MCLK 与 I2C 总线要求
- **MCLK 时钟源**：主芯片提供 24MHz 与 27MHz 两档输出。Sensor settings 内部的 PLL 乘除法系数完全是基于特定 MCLK 设计的。若 setting 期望 27MHz，而系统配置提供 24MHz，则实际输出帧率、曝光时间与 MIPI 速率将成比例偏移约 11.1%，导致严重频闪或 MIPI CRC 错误。
- **I2C 总线与从机地址**：
  - I2C 寻址必须统一使用 7-bit 地址（0x00 ~ 0x7F）。8-bit 写地址需右移 1 位。
  - 同一 I2C 总线上禁止两个传感器地址重叠（如 SC438HAI 与 XS9950 均挂在 I2C 1 且都配 0x30 时，会导致总线 ACK 冲突死锁）。

---

## 3. VIN 开发核心限制（SDK 10 文档）

### 3.1 硬件拓扑与模式限制
1. **DEV 与 MIPI 绑定**：`dev_id` 与 `mipi_id` 必须对应。
   - `dev 0` 专用于 SIF RAW（Sensor 0）。
   - `dev 1` 对应 Sensor 1（次摄 RAW 或后拉）。
   - `dev 2` 对应 AHD / DVP 输入。
2. **VC（Virtual Channel）通道数**：
   - AX615 每个 DEV 最多支持 **2 个 VC**（用于 HDR 2DOL 的长帧与短帧），不支持 3DOL。
3. **PIPE 物理通道限制**：
   - **AX615 每一个 PIPE 物理上仅支持 1 个物理通道（CHN0）！** 如需生成多种尺寸的分辨率（主码流、子码流、缩放预览），**必须且只能通过绑定 IVPS 模块来完成缩放（VPP）**，禁止直接在 VIN 配置多个输出通道。
4. **吞吐性能上限**：
   - AX615 PIPE 仅支持：**双摄最大 5M HDR FBC 写出**，或者 **单摄 8M HDR FBC 写出**。超过此规格会导致硬件带宽耗尽或掉帧。
5. **Dump Raw 限制**：
   - 双摄场景下，硬件同时**只支持 dump 1 路 sensor 原始 raw**，支持在两路之间动态切换，不支持双路同时 dump。

---

## 4. AXCK 多媒体解决方案级约束（SDK 46 文档）

1. **Pipeline 级联标准链路**：
   - 典型链路为：`Sensor -> VIN -> IVPS -> VENC/JENC -> App/DTCF`。
   - 必须通过 `ppl_config.json` 的 `chn_pipe` 建立从属关系：
     - `src: {dev: 0, pipe: 0, chn: 0}` 必须绑定到 `dst: {grp: 0}`（IVPS Group 0）。
2. **HDR 支持约束**：
   - 系统能否运行 HDR，前置取决于 `app_config.json` 中是否配置了 `hdr_support`，且 `sns_info.json` 中 `settingindex[2]` 必须配置大于 0 的有效 HDR setting。
3. **VENC / JENC 硬件通道号隔离**：
   - AX615 硬件编码器 VENC 与 JENC 共享 0~15 通道号。`app_config.json` 中的 `venc_chn_attr` 与 `jenc_chn_attr` 的 `chn_id` 严禁冲突重叠。
4. **内存池（VB Pool）规划**：
   - AX615 需为每个 PIPE 配置专有私有内存池，`PoolName` 中必须显式带有 `pipe0`, `pipe1` 等标识以完成内部管道匹配。

---

## 5. 图像插值与 CMM Pool 内存预算铁律 (Interpolation & CMM Pools)

1. **插值放大架构分工**：
   - 前端 VIN 严格保持 Sensor 原生分辨率（例如 OS04D10 为 2560x1440 RAW10，`pool.private` 保持原生 6 块缓冲）。
   - IVPS Group 0 的 Input Filter 保持接收原生 2560x1440，Output Chn 0 经由 `scl` 引擎插值至目标分辨率（如 2880x1620）。
2. **CMM Pool 联动配比规则**：
   - **主码流帧缓冲**：`pool.common` 中必须包含与目标插值尺寸完全吻合的 NV12 缓冲池（例如 2880x1620, blk: 2, compress: mode 2 level 10）。
   - **SW_LOW_MEM 切片编码环形缓冲**：必须包含宽度与目标插值宽度一致的切片缓冲池（例如 2880x128, blk: 1, compress: mode 2 level 4）。若切片缓冲宽度未同步调整，VENC 流式编码将发生跨距越界。
