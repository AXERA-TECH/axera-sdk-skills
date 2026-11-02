# AX615D 硬件引脚与 Sensor 标准接口电气契约规范 (AX615 Hardware Contract)

本文档归纳 AX615 / AX615D 芯片引脚与核心主板（如 Demo / Cust / P105）的传感器扩展接口物理定义。

> **核心硬件架构说明**：
> AX615 Demo 板本身为**独立的处理器主板，板卡自身不集成板载 Sensor**。
> 各种图像传感器（不管是 RAW Sensor 如 SC438HAI/OS04D10/SC431HAI，还是外接模拟高清转接芯片 AHD/YUV 如 XS9950/TP9963，或其它标准模组）均通过板卡上的**标准排针/FPC/接插件接口**外接引入。

---

## 1. 传感器物理扩展接口与 I2C 总线映射

AX615 支持多个硬件 I2C 控制器，在 Linux 内核中注册为 `i2c-0` ~ `i2c-5`。外部传感器模组接入标准接口时，`sns_info.json` 中的 `i2c_dev` 必须与接口引脚的 I2C 通道严格对应：

| I2C 设备号 (`i2c_dev`) | 典型管脚号 (PIN) | 信号定义 | 默认复用功能 | 板级扩展接口分配与走线特例 |
| :--- | :--- | :--- | :--- | :--- |
| **I2C0** (`0`) | Pin 78 / Pin 79 | `I2C0_SCL` / `I2C0_SDA` | GPIO1_A29 / GPIO1_A30 | **Demo 板 J10 (RX1) 专用总线**（注意：走线位于 J10 Pin 14/15，见下文避坑指南） |
| **I2C1** (`1`) | Pin 80 / Pin 81 | `I2C1_SCL` / `I2C1_SDA` | GPIO1_A31 / GPIO2_A0 | **AX615D Demo 板标准 J11 (RX0) 与 J9 (RX2) 扩展总线**（位于 Pin 12/13） |
| **I2C2** (`2`) | Pin 25 / Pin 26 | `I2C2_SCL` / `I2C2_SDA` | GPIO1_A6 / GPIO1_A7 | 拓展板 / 辅助传感器接口 |
| **I2C5** (`5`) | Pin 35 / Pin 36 | `I2C5_SCL` / `I2C5_SDA` | SPI_M0 复用引脚 | **P105 / P105T 板专用扩展总线** |

### ⚠️ Demo 板 J11 (RX0) vs J10 (RX1) 接口线序与通用模组避坑铁律 (High-Voltage Gotcha)
- **J11 (RX0) 与 J9 (RX2)**：
  - I2C 控制总线走 `/dev/i2c-1`，引脚为 **Pin 12 (SDA) / Pin 13 (SCL)**。
  - 属于标准通规模组线序（如通用 AHD 转接板 XS9950、普通 RAW Sensor）。Pin 14 为标准 GND。
- **J10 (RX1 1x2LANE)**：
  - Demo 板默认 BOM 下，Pin 12 / Pin 13 的电阻（R186/R178）**未贴片 (NC)**！
  - J10 的 I2C 走线通过 R823/R822 (0R) 引出至 **Pin 14 (`I2C0_SDA_AON`)** 与 **Pin 15 (`I2C0_SCL_AON`)**，挂在 `/dev/i2c-0`。
  - **严重故障模式**：若将通用标准线序小板（如 XS9950，其 Pin 14 为 GND，Pin 12/13 为 I2C）直接插入 J10：
    1. 小板 I2C 信号（Pin 12/13）悬空断开。
    2. 小板 Pin 14 (GND) 直接通过 R823 将主板 `/dev/i2c-0` 的 SDA 信号拉死到 GND！导致 `i2c transfer error`、整条 I2C0 总线被锁死挂死。
  - **双摄互换拓扑支持（实测验证）**：
    - **拓扑 A（标准出厂推荐）**：RX0 (J11) 插 XS9950（`i2c_dev: 1`, 从机 `0x30`），RX1 (J10) 插 OS04D10（`i2c_dev: 0`, 从机 `0x3c`）。
    - **拓扑 B（用户接线互换）**：RX0 (J11) 插 OS04D10（`i2c_dev: 1`, Reset GPIO 69），RX1 (J10) 插 XS9950（`i2c_dev: 0`, 从机 `0x30`, Reset GPIO 66, Power GPIO 71）。
    - 两种接法在 Camera-Kit 中均已通过独立配置文件（`*_os04d10_xs9950.json`）完整闭环调通，VIN/IVPS/VENC/JENC 全通道 25fps 满帧稳定出流。
- **双摄 MCLK 约束**：
  - Demo 板 J10 的 MCLK 硬件上贴片 R168，与 J11 共用 `SENSOR_MCLK0`（R761 MCLK1 为 NC）。
  - 双摄工作时，两路模组的 `sns_clk.clk_rate` 必须统一（例如均为 27MHz；OS04D10 选择 27M settingindex 3，XS9950 亦为 27MHz），或辅摄使用模组自带晶振解耦。

### ⚠️ I2C 从机地址（7-bit vs 8-bit）铁律
- **Linux 内核与 SDK 驱动严格要求配置 7-bit 地址**。
- 若传感器模组手册给出写地址 `0x60`、读地址 `0x61`，其 7-bit 地址为 `0x60 >> 1 = 0x30`（十进制 48）。
- 若配置大于 `0x7F`（例如误写 `0x60` 或 `0x6C`），底层 I2C 驱动将直接报 `i2c transfer error` 或找不到设备。
- `i2c_addr` 配置为 `0` 或 `0x00` 表示跳过配置直接采用 Sensor 动态驱动（.so）内部的默认地址。

---

## 2. 外部模组复位（Reset）与供电使能（Power）控制 GPIO

AX615 GPIO 编号计算公式为：`GPIO_NUM = Bank * 32 + Pin_Index`。
Demo 板接口引脚与控制定义如下：

| GPIO 编号 (`reset_gpio` / `power_gpio`) | 芯片管脚号 | 芯片引脚名称 | Demo 板接口网络名 | 作用与约束 |
| :--- | :--- | :--- | :--- | :--- |
| **69** (`GPIO2_A5`) | Pin 84 | `GPIO2_A5` | `SENSOR0_RSTN` | **标准 Sensor 接口通道 0 复位引脚**。高电平有效/低电平复位。 |
| **67** (`GPIO2_A3`) | Pin 76 | `GPIO2_A3` | `I2C2_SCL` / `GPIO2_A3` | **Demo 板 J10 (RX1) Sensor 模组标准复位引脚**（FRTDemo / QSDemo 双摄第二路 Sensor 默认配置）。 |
| **66** (`GPIO2_A2`) | Pin 83 | `GPIO2_A2` | `SENSOR1_RSTN` / `AHD_RESET` | **Demo 板 MIPI_SEL1 拨码状态监测 / AHD_RESET 引脚**。 |
| **70** (`GPIO2_A6`) | Pin 85 | `GPIO2_A6` | `GPIO2_A6` | **Cust 板通道 0 复位 / 部分工程主摄复位**。 |
| **71** (`GPIO2_A7`) | Pin 86 | `GPIO2_A7` | `SENSOR_PWR` / `AHD_PWR_ON` | **扩展接口模组供电 LDO 控制引脚**。高电平开启 3.3V/1.8V 供电。 |
| **99** (特殊) | - | - | - | **内部虚拟 GPIO / 跳过复位**。用于外部模组自带独立电源管理或常开场景。 |

---

## 3. MIPI D-PHY 物理通道与 Lane 映射（扩展接口连线）

AX615 芯片具备一套硬件 D-PHY，包含 **4 条数据通道（Data Lanes）** 与 **2 条时钟通道（Clock Lanes）**，引出到标准相机扩展接口：

### 物理引脚分布：
- **RX0 端口组（接口通道 0）**：
  - `RX_CD0_P/N` (Pin 42/43) -> Physical Data Lane 0
  - `RX_CD1_P/N` (Pin 44/45) -> Physical Data Lane 1
  - `RX_CD2_P/N` (Pin 46/47) -> **Physical Clock Lane 0** (索引为 2)
- **RX1 端口组（接口通道 1）**：
  - `RX_CD3_P/N` (Pin 49/50) -> Physical Data Lane 3
  - `RX_CD4_P/N` (Pin 51/52) -> Physical Data Lane 4
  - `RX_CD5_P/N` (Pin 53/54) -> **Physical Clock Lane 1** (索引为 5)

### 接口接入场景拓扑：
1. **单模组 4-Lane 场景（如 SC438HAI / SC533HAI 等高分辨率模组）**：
   - 外部模组连接接口占用全部 4 条 Data Lane：`lane: "lane_4"`
   - `lane_map: [0, 1, 3, 4]`, `clk_lane: [2, 5]`
   - 此时 MIPI RX 资源全部用尽，接口无法再接入第二路 MIPI 模组。
2. **双模组 2-Lane + 2-Lane 场景（任意两路 RAW / AHD 组合，如 OS04D10 + XS9950 或双 SC235HAI）**：
   - 接口通道 0（`rx_dev: 0`）：分配 RX0（Data 0, 1 + Clk 0），`lane: "lane_2"`
   - 接口通道 1（`rx_dev: 1`）：分配 RX1（Data 3, 4 + Clk 1），`lane: "lane_2"`
   - 两路外接模组各自独占硬件 PHY，时钟完全解耦。
3. **三模组场景（2-Lane + 2-Lane + BT656/DVP 并行接口）**：
   - 两路 MIPI 模组走 2-Lane + 2-Lane，第三路模组连接 BT656/DVP 扩展排针（Pin 27~41）。
