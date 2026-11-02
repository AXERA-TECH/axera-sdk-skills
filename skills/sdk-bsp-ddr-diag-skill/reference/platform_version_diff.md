# AX615 DDR 平台与版本差异

本文档用于 S1 环境与版本落定、S2 现象归属和 S4 源码反查。

> **分类来源说明**：本文档中的“合封 DDR：AX615D/C/Q 系列、外挂 DDR：AX615E 系列”来自用户提供的硬件分类。当前 DDR 源码直接识别的是 `chip_type` 枚举，并没有一个统一的“合封/外挂”字段。因此排查时必须同时记录 `chip_type`、`ddr_type`、DDR 协议、频率、配置宏和实际执行的初始化分支，不能只依据产品系列名称推断最终配置。

## 1. 芯片类型与产品分类

`AX_CHIP_TYPE_E` 定义于 `kernel/osdrv/ext_drv/include/ax_iram_misc_info.h:26-41`。

| 值 | `chip_type` | 产品分类 | 当前源码中的主要 DDR 行为 |
|---:|---|---|---|
| `0x1` | `AX615DV200` | AX615D，合封 | 默认走 DDR3 初始化路径；PHY pinmux 按 `ddr_type` 区分若干已知分支 |
| `0x2` | `AX615DV201` | AX615D，合封 | 使用独立 PHY pinmux 配置 |
| `0x3` | `AX615QV200` | AX615Q，合封 | 当前 DDR 主流程未见独立协议分支；具体产品配置待确认 |
| `0x4` | `AX615QV201` | AX615Q，合封 | 有独立 PHY 初始化相关分支 |
| `0x5` | `AX615DV100` | AX615D，合封 | DDR2、`1333 Mbps` 配置分支 |
| `0x6` | `AX615DV210` | AX615D，合封 | LPDDR3、`2133 Mbps` 配置分支 |
| `0x7` | `AX615CV100` | AX615C，合封 | 与 `AX615DV100` 共用 DDR2、频率和电源分支 |
| `0x8` | `AX615CV200` | AX615C，合封 | 与 `AX615DV200` 共用 DDR3 PHY pinmux 分支；完整 DDR 配置待确认 |
| `0x9` | `AX615DV110` | AX615D，合封 | LPDDR2、`800 Mbps` 配置分支 |
| `0xa` | `AX615DV220` | AX615D，合封 | DDR3、`1600 Mbps`，按频率选择 timing index，并有专用配置 |
| `0xb` | `AX615E` | AX615E，外挂 | 由编译宏选择 DDR3/DDR3L 和 `1333/1600/1866/2133 Mbps` |
| `0xc` | `AX615CV110` | AX615C，合封 | 与 `AX615DV110` 共用 LPDDR2、频率和电源分支 |

源码本身定义的是具体型号枚举；“产品分类”列使用用户提供的硬件定义，不能作为源码直接证明的硬件拓扑结论。

## 2. `chip_type`、`ddr_type` 的来源与覆盖风险

### 2.1 eFuse 读取路径

`board.c:get_chip_type()`（实际源码位置需按当前工程重新定位）执行以下类型的操作：

1. 从芯片非易失配置区域读取芯片类型；
2. 对原始值执行平台解码；
3. 将结果写入运行时芯片信息；
4. 读取 DDR 类型并写入运行时 DDR 信息；
5. 对未知芯片类型执行默认回退；
6. 将结果写入供后续启动阶段读取的公共信息位置。

`AX_DDR_TYPE_E` 同样定义于 `ax_iram_misc_info.h`。不同枚举值可能触发不同的 PHY pinmux 或 timing 分支；具体语义必须以当前源码和客户颗粒信息共同确认。

建议同时收集：

```text
产品丝印/具体型号：<待填写>
eFuse 解码 chip_type：<待填写>
eFuse ddr_type：<待填写>
DDR 初始化实际 chip_type：<待填写>
DDR 初始化实际 ddr_type：<待填写>
启动日志中的 ddr freq：<待填写>
SPL/FDL 构建时间：<待填写>
```

## 3. AX615D/C/Q 合封 DDR 的当前源码映射

### 3.1 明确的协议、频率和配置分支

`ddr_freqs_get()` 位于 `ddr_init.c:1641-1686`，当前可确认的映射如下：

| `chip_type` | DDR 协议 | 频率 | 说明 |
|---|---|---:|---|
| `AX615DV100`、`AX615CV100` | DDR2 | `1333 Mbps` | 使用 DDR2 配置分支 |
| `AX615DV110`、`AX615CV110` | LPDDR2 | `800 Mbps` | 使用 LPDDR2 配置分支 |
| `AX615DV210` | LPDDR3 | `2133 Mbps` | 使用 LPDDR3 配置分支 |
| `AX615DV220` | DDR3 | `1600 Mbps` | 按频率选择 timing index |
| 其他未单独处理的类型 | 默认 DDR3 路径 | 由当前源码 default 决定 | 必须结合完整上下文核实 |

相应的初始化 flow 在 `ddr_init.c:1307-1341` 和 `1699-1719`：

- `AX615DV100`、`AX615CV100` → `ddr2_init_flow()`；
- `AX615DV110`、`AX615CV110` → `lpddr2_init_flow()`；
- `AX615DV210` → `lpddr3_init_flow()`；
- 其他类型 → `ddr3_init_flow()`。

每条流程都组合 controller pre-init、PHY pre-init、post-init 和 training sequence。看到 training 失败时，应先确认实际协议路径，不能把 DDR2、LPDDR2、LPDDR3 和 DDR3 日志混用解释。

### 3.2 供电分支

`ddr_ldo_output_config()` 位于 `ddr_init.c:1594-1639`，在 `INTERNAL_LDO_OPEN` 为真时依据 chip type 选择相应供电配置。当前代码注释涉及不同 DDR 协议的电压方向，但这些是代码分支和注释中的配置依据，不替代板级实测，也不能在缺少具体颗粒资料时直接建议改电压。

### 3.3 PHY pinmux 与特殊型号

`ddrphy_pinmux_set()` 位于 `ddr_init.c:807-920`：

- 多个型号使用独立 PHY pinmux 分支；
- `AX615DV200`、`AX615CV200` 还按 `ddr_type` 区分已知分支；
- `AX615DV110` 的 LPDDR2 分支存在两种颗粒厂商分支（`ddr_type` 为 ELPIDA 与 JSC）。排查 DV110 相关问题时必须向客户确认颗粒厂商与料号，避免按错误分支解释 training 结果或给出配置建议。来源：团队客诉经验记录；源码侧对应的 `ddr_type` 分支取值待复核；
- `AX615DV210`、`AX615DV110` 使用对应 LPDDR 专用 pinmux 函数；
- 未知或未覆盖类型可能落入默认分支。

`ddr3_ddrphy_pre_init()` 位于 `ddr_init.c:1021-1082`，包含校准来源、DDR3 mode、timing、型号/频率特例、pinmux 和 `MODE_2T` 相关行为。涉及内部实现细节时，公开文档只保留“存在该配置阶段”的描述，具体值和低级定义需在受控环境由原厂确认。

## 4. AX615E 外挂 DDR 的当前源码映射

### 4.1 当前编译宏

`ddr/ddr_init_config.h` 中存在 AX615E 频率、DDR3/DDR3L、供电和 pinmux 相关编译宏。它们是编译期选择，不是运行时自动探测结果，也不是所有 AX615E 硬件的固定规格。排查时必须确认最终构建所用头文件和 BL1 镜像是否确实包含这些值。

### 4.2 AX615E 的专用行为

当前源码对 `AX615E` 有独立的 pinmux、timing、供电和频率选择分支，并在 `ax615_ddr_init()` 中进入 DDR3 flow 的 default 路径。外挂 DDR 排查必须进一步核对：颗粒料号、DDR3/DDR3L、电压、位宽、Rank、容量、时序、板级走线和实际配置。不能仅凭“AX615E + DDR3”结束判断。

## 5. 当前配置与版本差异风险

### 5.1 默认分支不等于正式产品支持

当前代码存在多个 default 行为：

- `ddr_freqs_get()` default 使用默认频率/timing；
- `ddrphy_pinmux_set()` default 使用默认 pinmux；
- `ax615_ddr_init()` default 使用 `ddr3_init_flow()`。

遇到未知型号或解码异常时，应把这些行为记录为“错误回退或待确认”，不能写成该型号的正式配置。

### 5.2 当前源码、最终镜像和输入信息可能不一致

必须分别确认：

1. 当前工作区源码版本；
2. 实际构建使用的 `ddr_init.c` 和 `ddr_init_config.h`；
3. 最终 BL1 镜像校验值/构建时间；
4. 芯片类型和 DDR 类型来源信息；
5. 启动日志中实际频率、协议和 training 分支；
6. 是否存在 `ax615_ddr_init()` 的硬编码覆盖。

如果以上信息不一致，结论应限制为“环境/版本尚未闭合”，不能直接归因到 PHY、颗粒或板级信号完整性。

### 5.3 配置宏不能误写成芯片硬件规格

以下内容只能写成“当前源码宏配置”：

- `AX615E_CLK_*`；
- `AX615E_DDR3L`、`AX615E_DDR3`；
- `INTERNAL_LDO_OPEN`；
- `D_PINMUX_*` 及其他平台配置宏。

不能据此断言所有 AX615E 板卡都必须使用同一频率、电压或 pinmux。必须结合板卡版本、颗粒资料和最终镜像验证。

## 6. 排查时的最小信息集

### 6.1 所有平台都要收集

```text
具体 chip type：<例如 AX615DV220/AX615QV201/AX615E>
产品/封装分类：<AX615D/C/Q 合封，或 AX615E 外挂>
输入信息原始/解码值：<待填写>
实际初始化 chip_type：<待填写>
实际初始化 ddr_type：<待填写>
DDR 颗粒厂商和料号：<待填写>
DDR 协议：<DDR2/DDR3/DDR3L/LPDDR2/LPDDR3/待确认>
目标频率与启动日志实际频率：<待填写>
板型和芯片 revision：<待填写>
SDK 版本与 BL1 构建时间：<待填写>
```

### 6.2 合封 DDR（AX615D/C/Q）

优先顺序：

1. 具体型号是否与 `AX_CHIP_TYPE_E` 一致；
2. 是否进入预期的 DDR2、LPDDR2、LPDDR3 或 DDR3 flow；
3. 频率、容量和位宽配置是否匹配；
4. PHY pinmux、校准和型号专用 timing 是否命中；
5. 再分析 training、BIST 和运行时错误。

### 6.3 外挂 DDR（AX615E）

优先顺序：

1. 确认 `AX615E` chip type 实际生效；
2. 确认 DDR3/DDR3L 宏与颗粒规格和板级电压一致；
3. 确认 `AX615E_CLK_*` 只有一个有效选择；
4. 确认位宽、Rank、容量与配置类型一致；
5. 确认 AX615E 专用 pinmux、timing 和初始化行为；
6. 再区分软件配置、颗粒兼容性、电源和信号完整性问题。

## 7. 证据纪律

- `training fail` 不直接等同于 PHY 故障；先确认失败阶段和前置配置。
- `memtest/BIST fail` 不直接等同于 DDR 颗粒损坏；先区分地址映射、位宽、频率、时序、电源和板级问题。
- 同一频率不代表同一 timing、pinmux、VDDQ、Rank 或容量配置。
- 看到 `dram type is DDR3` 不能直接判断是 AX615E；AX615D/C/Q 的多个型号也会走 DDR3 初始化流。
- 没有颗粒规格、公开芯片手册或稳定对照组时，不给出具体电压、阻抗、驱动强度、ODT 或时序修改值。
- 每条最终结论至少引用一个源码文件和行号、公开规格章节或客户原始输出。
- 用户硬件分类、源码事实、当前宏配置和待确认假设必须分开标注。
- 不在公开文档中复制芯片级内部寄存器地址、位域、原始低级转储或内部资料文件名。
