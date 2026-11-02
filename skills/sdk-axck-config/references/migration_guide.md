# AX615 Sensor 模组迁移与 settingindex 自动选择指南

## 1. 模组接入架构与 settingindex 逻辑

AX615 Demo 板为独立主板，本身不集成传感器，传感器模组通过标准接口接入。

`settingindex` 是由各 Sensor 厂家 FAE 固化在驱动动态库中的时序与寄存器序列配置索引：
1. 输出分辨率（Width × Height）
2. 动态范围模式（SDR / Linear vs HDR）
3. 数据格式与位宽（RAW10 vs RAW12）
4. Bayer 排列（RGGB）
5. 基准帧率（25fps / 30fps）
6. 接口 MIPI PHY 物理 Lane 数（4-Lane vs 2-Lane）
7. 接口输入 MCLK 主频（24MHz vs 27MHz）
8. 单 Lane 高速数据吞吐率（MIPI Data Rate）

### 自动选择规则

| 条件 | 适配策略 |
|------|---------|
| 单模组接入 | 若模组支持，可选择 4-Lane 获得更低 MIPI 单线速率，降低干扰 |
| 双模组接入 | 两个接口必须均配置为 2-Lane（AX615 全芯片仅 4 条 Data Lane，两路平分）|
| MCLK 频率 | 必须与模组当前 settingindex 严格匹配，24M 与 27M 错配将导致帧率偏移 11.1% |

### 各常见模组预设表

| Sensor 模组 | 单模组 Index | 单模组 Lane/MCLK | 双模组 Index | 双模组 Lane/MCLK | 分辨率 |
|------------|-------------|-----------------|-------------|-----------------|--------|
| SC438HAI   | 1 (SDR)     | 4L / 27M        | 3 (SDR)     | 2L / 24M        | 2688×1520 |
| SC431HAI   | 1 (SDR)     | 2L / 24M        | 1 (SDR)     | 2L / 24M        | 2560×1440 |
| SC431AI    | 1 (SDR)     | 4L / 24M        | 33 (SDR)    | 2L / 27M        | 2688×1520 / 2560×1440 |
| OS04D10    | 1 (SDR)     | 2L / 24M        | 1 (SDR)     | 2L / 24M        | 2560×1440 |
| MIS20S1    | 2 (SDR)     | 2L / 24M        | 2 (SDR)     | 2L / 24M        | 1920×1080 |
| XS9950     | 1 (AHD)     | 2L / 24M        | 1 (AHD)     | 2L / 24M        | 1920×1080 |
| TP9963     | 1 (AHD)     | 2L / 24M        | 1 (AHD)     | 2L / 24M        | 1920×1080 |

---

## 2. 标准扩展接口引脚映射

### Demo 板 (AX615D_DEMO 标准接口)

| 信号类别 | 扩展接口通道 0 (cam_pos=0) | 扩展接口通道 1 (cam_pos=1) |
|---------|---------------------------|---------------------------|
| I2C 总线 | `i2c_dev: 1`              | `i2c_dev: 1` (支持共享总线) |
| 复位引脚 | `69` (SENSOR0_RSTN, Pin 84)| `66` (SENSOR1_RSTN, Pin 83)|
| 供电使能 | 板级基准供电               | `71` (SENSOR_PWR / 模组供电使能, Pin 86) |
| MIPI D-PHY | RX0 (Data 0, 1 + Clk 0)  | RX1 (Data 3, 4 + Clk 1)   |

### P105 板
- I2C 总线：`i2c_dev: 5`
- 复位引脚：`99`（跳过软复位）

### Cust 板
- I2C 总线：`i2c_dev: 0`
- 复位引脚：`70`（通道 0）/ `66`（通道 1）

---

## 3. RAW 与 YUV/AHD 模组接入通道规则

AX615 SIF 硬件通道分工：
- `dev_id: 0` → 专供 RAW Sensor 硬件解马赛克与 ISP 链路。
- `dev_id: 1` 或 `2` → 供 YUV / AHD 解串模组使用。

**特别说明**：即使 YUV/AHD 转接模组物理上插在接口通道 0，其逻辑 `dev_id` 也必须设置为 1 或 2，不可设为 0。

---

## 4. 迁移事务安全与回滚

- **备份**：每次写入自动生成时间戳备份 `.backup_YYYYMMDD_HHMMSS`。
- **预览**：`--dry-run` 输出完整差异，确认无误后再落地。
- **复验**：修改后自动运行 `axck-tool validate` 保证配置无语法与硬件冲突。
- **回滚**：支持通过 `--rollback <timestamp>` 恢复历史正常版本。
