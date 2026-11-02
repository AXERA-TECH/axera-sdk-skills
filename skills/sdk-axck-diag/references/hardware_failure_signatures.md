# AX615 硬件故障签名与排查指南

## 1. SIF FIFO 溢出

**关键字**: `sif fifo overflow`, `sif fifo full`, `sif overrun`

**根因**: Sensor 输出行数据速率超过 AX615 SIF 硬件处理能力。

**AX615 SIF 硬件参数**:
- 主频: 367 MHz
- 处理能力: 2 pixel/cycle
- 最小行时间: `min_line_time = width / 367 / 2` (us)

**常见分辨率最小行时间**:
| 分辨率宽度 | 最小行时间 |
|-----------|-----------|
| 2880 | 3.924 us |
| 2688 | 3.662 us |
| 2560 | 3.488 us |
| 1920 | 2.616 us |
| 1280 | 1.744 us |

**排查步骤**:
1. 确认 Sensor 的 HTS (Horizontal Total Size) 满足最小行时间
2. 核对 settingindex 是否正确（不同 Index 对应不同 HTS）
3. 确认 MCLK 频率匹配（24M vs 27M 不匹配将改变实际行时间）

---

## 2. MIPI D-PHY 故障

### 2.1 CRC 错误
**关键字**: `mipi crc error`, `checksum fail`

**根因**: MIPI 数据包校验失败，通常由信号完整性问题引起。

**排查步骤**:
1. 检查 MIPI 走线质量（等长、阻抗匹配）
2. 确认 lane_map 和 clk_lane 配置与物理连线匹配
3. 确认终端电阻正确
4. 降低 MIPI 数据速率（选择低速 settingindex）

### 2.2 PLL/Lock 失败
**关键字**: `mipi pll fail`, `mipi lock lost`, `phy lock timeout`

**根因**: D-PHY 物理层无法与 Sensor MIPI 输出同步。

**排查步骤**:
1. 确认 MCLK 已正确输出（示波器测量 24M/27M）
2. 确认 Sensor 供电稳定
3. 确认 Reset GPIO 已释放（高电平）
4. 检查 clk_lane 配置：Clock 0 属于 Lane 0~2，Clock 1 属于 Lane 3~5

### 2.3 ECC 错误
**关键字**: `mipi ecc error`

**根因**: MIPI 包头 ECC 纠错失败，通常是 PCB 走线问题。

---

## 3. I2C 通信故障

### 3.1 I2C NACK 与总线被拉死挂死 (Remote I/O Error)
**关键字**: `i2c nack`, `i2c nak`, `Remote I/O error`, `Failed to read reg: Remote I/O error`

**根因**: Sensor 未响应 I2C 总线寻址，或 I2C 总线信号被硬件短路接地/未拉高。

**常见原因（按可能性排序）**:
1. **接口物理线序错位（Demo 板 J10 vs 通用小板）**: Demo 板 J10 (RX1) 的 I2C 走线在 Pin 14 (`I2C0_SDA`) 与 Pin 15 (`I2C0_SCL`)。若将通用相机小板（Pin 12/13 为 I2C，Pin 14 为 GND，如 XS9950）插入 J10，其 Pin 14 会直接将主板 `I2C0_SDA` 短路到 GND，锁死整个 `/dev/i2c-0`，导致所有 I2C 访问均报 `Remote I/O error`。
2. **I2C 地址错误**: 误配 8-bit 写地址而非 7-bit。例如 SC438HAI/XS9950 应为 `0x30`（7-bit），不是 `0x60`（8-bit 写）；OS04D10 7-bit 为 `0x3c`。
3. **Sensor 未上电**: power_gpio 未拉高（AHD 传感器如 XS9950 需要供电使能）。
4. **Reset GPIO 错误或未释放**: reset_gpio 配置为 `-1` 导致驱动打开 `/sys/class/gpio/gpio-1` 报错崩溃，或 reset_gpio 仍为低电平（RX0 典型为 69，RX1 模组典型为 67）。
5. **I2C 总线编号错误**: Demo 板 RX0 走 `i2c_dev: 1`，RX1 模组走 `i2c_dev: 0`，p105 板走 `i2c_dev: 5`。
6. **MCLK 未输出**: 部分 Sensor 需要 MCLK 驱动后内部 PLL 启动才响应 I2C。Demo 板 J10 与 J11 共用 MCLK0，两路 Sensor 的时钟频率配置必须相同（如均为 27MHz）。

**快速验证**: 
- `i2cdetect -y -r <bus_num>` 检查总线上是否有 ACK 响应。
- 若整条总线扫描非常慢或所有地址均报超时/IO error，排查是否有引脚接地短路。

### 3.2 I2C 传输超时
**关键字**: `i2c transfer timeout`, `i2c error`

**根因**: I2C 总线通信中断，可能由总线竞争或硬件故障引起。

---

## 4. YUV dev_id 硬件约束违反

**关键字**: `mipi yuv dev_id 0 is invalid`

**根因**: AX615 SIF dev 0 硬件专用于 RAW Bayer 解马赛克。YUV 传感器必须使用 dev_id 1 或 2。

**影响传感器**: XS9950, TP9963 等所有 AHD/YUV 芯片

**修复**: 修改 `app_config.json` 中对应 camera 的 `dev_id` 为 `1`。

---

## 5. 编码器通道冲突

**关键字**: `AX_VENC_CreateChn fail`, `0x80070216`

**根因**: VENC（视频编码）和 JENC（JPEG 抓拍编码）共享 0~15 硬件通道号。

**排查**: 检查 `ppl_config.json` 中所有 `cache.enc_chnl` 和 `thumb.enc_chnl` 值，确保无重复。

---

## 6. CMM 内存池耗尽

**关键字**: `AX_POOL_GetBlock fail`, `pool get block fail`, `cmm alloc fail`

**根因**: 物理内存不足或 buffer 泄漏。

**排查步骤**:
1. 检查 `/proc/ax_proc/mem_cmm_info` 确认 CMM 剩余空间
2. 区分 pipe0 和 pipe1 池——双摄场景各有独立池
3. 增加 `app_config.json` 中 pool 的 `block_count`
4. 降低分辨率或编码通道数以减少内存需求

---

## 7. ITP 旋转 Line Buffer 耗尽

**关键字**: `itp line_buf exhaust`, `rotation overflow`

**根因**: ITP 硬件旋转需要 line buffer，高分辨率旋转超出硬件资源。

**排查**: 降低旋转通道的分辨率，或关闭不必要的旋转/转置操作。

---

## 8. 录像封装切文件关键帧等待时序异常 (MP4 Muxer NAL 约束)

**关键字**: `[MUX_MP4][mp4mux_h265_write_nal][E] Need vps: 1 need SPS: 1 need PPS: 1 needIDR: 1`

**根因**: 
切文件（SwitchFile）瞬间，伴随生成的缩略图帧（`effIsThumb`）先于真正的视频 IDR 关键帧到达。若录像控制层（如 `axck_record_api.c` 的 `ChkCanWrite()`）在等待关键帧（`rwsWaitKey`）期间将缩略图帧误判为解除等待条件，过早将状态置为 `rwsWaitNone`，会导致旧 GOP 残留的普通 P 帧被提前放行写入。MP4 Muxer 新文件初始化尚未收到 IDR 帧，无法解析 P 帧，从而触发主动拦截并连续打印该 Error 日志。

**排查与修复**:
1. 检查 `service/mod/axck_record/axck_record_api.c` 中的 `ChkCanWrite()`。
2. 确认当处于 `rwsWaitKey` 时：
   - 缩略图帧（`effIsThumb`）仅允许穿透写入缩略图 box，不得将状态从 `rwsWaitKey` 提前解除；
   - 仅当真正视频关键帧（`effIsKey`）到达时，才将状态置为 `rwsWaitNone`；
   - 其余非关键帧（旧 GOP P 帧）保持拦截（返回 `rwsWaitKey`）。

---

## 9. 根因追溯原则

### 时间线优先级
1. **CRITICAL 级最早事件**（排除 heartbeat timeout）= 根因
2. **ERROR 级最早事件** = 次优根因候选
3. **WARNING 级事件** = 辅助线索

### 常见级联模式
```
I2C NACK → Sensor 探测失败 → VIN 启动失败 → IVPS 无输入 → heartbeat timeout
MCLK 错误 → D-PHY 失锁 → SIF FIFO 溢出 → 帧率异常 → heartbeat timeout
dev_id 错误 → VIN 创建失败 → VENC 无法绑定 → heartbeat timeout
通道冲突 → VENC 创建失败 → 编码线程退出 → heartbeat timeout
```

**铁律**: 始终修复最上游的 CRITICAL 事件，忽略下游连锁反应。
