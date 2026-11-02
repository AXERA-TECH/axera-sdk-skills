# AX615 DDR 代码地图

本文档是公开版源码导航，记录 DDR 初始化入口、关键调用链、配置来源和证据定位方法。它不包含芯片级内部资料、原始地址清单、位域清单或 PHY 物理实现细节。

> **使用边界**：下表中的行号来自当前参考源码，源码变更后可能漂移。实际分析时应先用符号和日志文本重新定位，再引用本次实际源码的 `文件:行号`。

## 1. 使用方法

1. 在 S1 确认实际构建所用源码、commit 和 BL1 镜像。
2. 从 `ax615_ddr_init()` 确认实际 `chip_type`、`ddr_type`、频率和协议 flow。
3. 沿对应 flow 检查 DDRMC pre-init、DDRPHY pre-init、power-up、post-init 和 training。
4. 将源码实际选择的配置与颗粒规格、板级设计和稳定配置对照。
5. 所有结论引用本次实际源码；本文件只提供候选位置和搜索关键字。

推荐只读定位命令：

```bash
DDR_SRC=/boot/bl1/driver/ddr/ax615_ddr
rg -n "ax615_ddr_init|ddr_freqs_get|ddr_ldo_output_config|ddrphy_pinmux_set" "$DDR_SRC"
rg -n "ddr2_init_flow|ddr3_init_flow|lpddr2_init_flow|lpddr3_init_flow" "$DDR_SRC"
rg -n "training|train|timeout|error|fail|BIST|bist" "$DDR_SRC"
```

上述搜索结果只能用于定位候选代码，不能替代逐段阅读源码、公开芯片手册或颗粒数据手册。

## 2. 顶层入口与环境来源

| 模块/符号 | 当前参考位置 | 用途 | 分析时必须确认 |
|---|---|---|---|
| `ax615_ddr_init()` | `ddr_init.c:1688-1722` | DDR 初始化入口；选择协议 flow 并调度后续测试 | 实际入口、最终选择的 flow、是否存在版本差异 |
| `ddr_freqs_get()` | `ddr_init.c:1641-1686` | 根据型号和编译配置选择频率及类型 | 日志实际频率、构建宏、默认分支 |
| `ddr_ldo_output_config()` | `ddr_init.c:1594-1639` | 按型号和配置选择供电方向 | 内置/外置供电、板级实测值、颗粒规格 |
| `ddrphy_pinmux_set()` | `ddr_init.c:807-920` | 按型号和 DDR 类型选择 PHY pinmux 配置 | 实际型号、`ddr_type`、板级连接 |
| `ddrmc_phy_init()` | `ddr_init.c:922-936` | 发起 PHY 初始化并等待完成 | 首个 timeout、前置 flow 和后续处理 |
| `ddr3_ddrphy_pre_init()` | `ddr_init.c:1021-1082` | DDR3 PHY 前置配置和初始化握手 | timing、pinmux、校准和型号特例 |
| `ddrmc_train_flow_no_lp.c` | 多个 training 函数 | 训练阶段调度、结果日志和超时处理 | 当前协议是否实际调用该文件 |

## 3. 协议 flow 与关键阶段

`ax615_ddr_init()` 的当前参考映射：

| `chip_type` | 协议 flow | 当前依据 | 备注 |
|---|---|---|---|
| `AX615DV100`、`AX615CV100` | `ddr2_init_flow()` | `ddr_init.c:1335-1341`、`1699-1705` | DDR2 路径 |
| `AX615DV110`、`AX615CV110` | `lpddr2_init_flow()` | `ddr_init.c:1315-1324`、`1706-1710` | LPDDR2 路径 |
| `AX615DV210` | `lpddr3_init_flow()` | `ddr_init.c:1307-1313`、`1711-1714` | LPDDR3 路径 |
| 其他类型，包括当前 AX615E 分支 | `ddr3_init_flow()` | `ddr_init.c:1326-1333`、`1715-1718` | default 不等于正式产品规格，必须核实 |

分析每条 flow 时按以下顺序记录，不要只截取最终 `fail`：

| 阶段 | 要找的代码行为 | 要收集的现场证据 |
|---|---|---|
| 频率/PLL | 频率选择、时钟配置、等待条件 | 目标频率、日志频率、时钟实测 |
| DDRMC pre-init | 协议、位宽、Rank、容量和 timing 选择 | 配置快照、颗粒规格和稳定对照 |
| DDRPHY pre-init | timing、pinmux、校准和型号特例 | `chip_type`、`ddr_type`、日志和板级信息 |
| DRAM power-up | reset、CKE、模式命令和等待 | 协议匹配、首个 timeout/error |
| DDRMC post-init | 控制器状态切换和功能使能 | 时间线和后续日志 |
| training | 阶段推进、pass/fail、timeout 和返回值 | 每个阶段结果、首个失败点 |
| BIST/memtest | 测试范围、模式、完成条件和错误输出 | 结果矩阵、失败地址/数据、复现率 |

## 4. PHY、pinmux 与型号特例

| 符号/行为 | 当前参考位置 | 已知分支 | 核对重点 |
|---|---|---|---|
| `ddrphy_pinmux_set()` | `ddr_init.c:807-920` | 多个 AX615 型号和 DDR 类型分支 | 实际型号、`ddr_type`、板级连接 |
| `ddr3_ddrphy_pre_init()` | `ddr_init.c:1021-1082` | 校准、DDR3 timing、型号专用 timing、pinmux 和 `MODE_2T` | 频率、颗粒 speed bin、最终镜像 |
| `lpddr2_ddrphy_pre_init()` | `ddr_init.c:1002-1019` | LPDDR2 专用前置流程 | LPDDR2 型号和厂商分支 |
| `lpddr3_ddrphy_pre_init()` | `ddr_init.c:988-1000` | LPDDR3 专用前置流程 | LPDDR3 配置和训练入口 |
| `ddrmc_phy_init()` | `ddr_init.c:922-936` | 有限轮询；超时后打印日志并返回当前 flow | 后续训练是否在前置失败后继续 |

## 5. 配置头文件地图

| 文件 | 用途候选 | 常用搜索关键字 | 风险 |
|---|---|---|---|
| `ddr/ddr_init_config.h` | 产品、频率、协议和功能开关 | `AX615E_CLK_`、`AX615E_DDR3`、`AX615E_DDR3L`、`INTERNAL_LDO_OPEN`、`D_PINMUX_` | 编译宏不等于硬件规格；需确认实际参与构建 |
| `ddr/ddr_common_config.h` | 公共配置、类型或流程参数 | `DDR`、`TYPE_`、`CS`、`CH`、`X16` | 字段与平台映射需沿调用链确认 |
| `ddr/ddrmc_timing_define_*.h` | 各协议控制器 timing | timing 数组/索引名 | 必须匹配协议、频率和颗粒规格 |
| `ddr/ddrphy_timing_define_*.h` | 各协议 PHY timing | timing 数组/索引名 | 不能跨协议或跨型号套用 |

## 6. Training 反查记录模板

```markdown
### Training 阶段：<阶段名>

- 适用协议/型号：<待填写>
- 入口符号：`<待填写>`
- 调用方：`<待填写>`
- 启动条件：<待填写>
- 完成条件：<待填写>
- 超时条件：<待填写>
- 错误状态/返回值：<待填写>
- 首个异常日志：<待填写>
- 源码依据：<文件:行号>
- 公开规格依据：<章节或待补充>
- 当前判断：<已确认事实 / 待验证假设>
```

当前 DDR3 training 的公开源码入口：

- `ddr3_train_flow_sequence()`：`ddrmc_train_flow_no_lp.c:534-550`；
- `ddr3_ddr4_train_info_pre_set()`：training 公共前置配置；
- `ddr3_train_rdeye_duty_cycle()`：读路径训练调用；
- `ddr3_ddr4_train_wrdsk()`：写 deskew 阶段；
- `ddr3_ddr4_wreye_train_flow()`：写 eye 阶段。

只根据日志判断时，区分 `pass`、`fail` 和 `timeout`。若只有最终失败日志而没有阶段顺序，结论应标为「根因时间点未闭合」。

## 7. BIST/memtest 反查记录模板

```markdown
### 测试：<BIST 或 memtest 名称>

- 调用入口：<待填写>
- 测试模式/数据模式：<待填写>
- 地址范围：<待填写>
- 是否可能覆盖有效内存：<是/否/待确认>
- 完成条件：<待填写>
- timeout/错误判据：<待填写>
- 错误地址、期望值、实际值：<待填写>
- 结果矩阵：<附件路径>
- 源码依据：<文件:行号>
- 公开规格依据：<章节或待补充>
- 安全边界：<启动阶段限定、保留区、禁止在线执行等>
```

当前源码入口：

- `bist_init()`：`ddr_init.c:1116-1176`；
- `bist_test()`：`ddr_init.c:1209-1233`；
- `dram_bist_test()`：`ddr_init.c:1235-1283`；
- `ddr_bist_proc()`：`ddr_init.c:1285-1303`；
- `ddr_env_bist_scan()`：`ddr_init.c:1563-1584`。

BIST 结论必须同时记录“是否完成”和“是否失败”。如果测试没有完成，不要把它写成数据错误。

## 8. 代码地图维护规则

- 新增条目必须包含符号、用途、可搜索特征和证据状态。
- 行号变化时优先保留稳定的符号和日志文本，并更新参考行号。
- 未经公开规格或实际调用链确认的内容标为“用途候选”或“待验证”。
- 发现代码风险时记录到 `reference/known_suspects.md`；形成可复用闭环后再整理进 `reference/FAQ.md`。
- 不在公开文档中记录芯片级内部地址、位域、原始低级转储或内部资料文件名。
