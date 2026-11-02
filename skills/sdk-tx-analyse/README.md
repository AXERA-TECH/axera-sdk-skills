# sdk-tx-analyse — AX615 TX 分析与代码生成 Skill

此 skill 覆盖 AX615 外部模拟同轴发送芯片（AX_TX）的两类需求：**问题分析/客户答疑** 和 **示例代码生成/修改**。

---

## 功能概览

### §A 分析答疑模式（只读）

适用于：

- TX 同轴无输出、花屏、画面抖动、DVR 锁不上
- VO timing 与 TX 参数是否匹配
- BtClk / BtWorkMode / SDR / DDR 该怎么选
- 某个 AX_TX API 或枚举含义、返回错误码代表什么
- RS485 或正/反向音频异常分析
- 给客户讲解 TX 通路行为与排查步骤

**此模式只给出分析结论和排查步骤，不产出任何代码改动。** 若最终确认需要改代码，可在对话中切换到代码生成模式。

### §B 代码生成模式

适用于：

- 在 `msp/sample/vin_ivps_vo_tx` 中新增或修改 TX/VO 输出制式
- 增删 `VIDEO_PARAM_MAP_S` 映射表行（BtClk / BtWorkMode / InFmt / OutFmt 成套更新）
- 新增 `VO_INTF_FMT_TYPE_E` 枚举和对应 `gastPubAttr[]` timing 项
- 配置 TX_CLK / TX_VI / TX_VO 生命周期
- 增加 RS485、正向/反向音频、colorbar 测试通路
- 更新命令行参数（`-o` VO intf、`-t` TX proto）

---

## 知识库

skill 内置 `knowledge-base/AX615 VO时序配置.md`，包含 27 条 BT656 SDR/DDR USER timing 权威参数表（逐格转录自官方 PDF，时序公式交叉校验）。生成或核对 `AX_VO_SYNC_INFO_T` 时此表为首要依据，无需另查 PDF。

---

## 使用方式

在 Claude Code 中输入：

```
/sdk-tx-analyse
```

然后描述你的需求，skill 会根据意图自动选择分析模式或生成模式。

**示例提问：**

```
# 分析模式
我的 TVI 4M30 通路 DVR 锁不上，VO proc 帧率正常，怎么排查？

# 生成模式
在 vin_ivps_vo_tx 中增加 AHD 2880x1620@25fps 输出

# 分析+生成
先帮我分析 CVI 2592x1944@20fps 的 VO和TX 参数是否匹配，确认后帮我补完映射表
```

---

## 注意事项

### 必须与仓库文件对照，不凭记忆断言

skill 会实际读取以下文件，结论与代码均有引用来源：

- `header/external/ax_tx_api.h`、`ax_tx_common.h`、`ax_vo_api.h`
- `msp/sample/vin_ivps_vo_tx/sample_tx.c/h`、`sample_vo.c/h`、`sample_main.c/h`
- `knowledge-base/AX615 VO时序配置.md`

### VO×TX 必须成套更新

修改任何制式时，以下六个字段是一个整体，不能只改其中几个：

| 字段 | 含义 |
|---|---|
| `enVoIntf` | VO 侧 timing 类型（同时对应 `gastPubAttr[]` 和枚举） |
| `enTxVideoProto` | CVI / AHD / TVI / CVBS |
| `enBtClkFreq` | BtClk 频率（36M / 74.25M / 148.5M） |
| `enBtWorkMode` | 单沿 HD1 / 双沿 DUL_HD1 / SD |
| `enInFmt` | TX 输入制式（分辨率帧率） |
| `enOutFmt` | TX 输出制式（前缀决定协议族） |

遗漏任何一项会导致 DVR 锁不上或画面异常。

### 板级线序不可跨板复制

`AX_TX_VI_SetDataLine` 的 `data_line[]` 和 `AX_VO_SetDataPinMap` 的 `dataArray[]` 是板级参数，FPGA 与量产板不同。skill 只能引用仓库 sample 的既有值或你提供的原理图，不会自行推测线序。

### BTOUT 段制式芯片不支持

`ax_tx_common.h` 中 `VIDEO_OUT_FMT_E` 末尾的 `BT_*` 系列（BTOUT 段）芯片实际不支持，不要将其作为输出制式选用。

### 2880x1620 V20 制式有专用 VO timing

TX 输出 `HDCVI_2880x1620_*_V20` 时，VO 侧必须使用 vtotal=1728 的 vts1728 timing，不能用普通 vts1650 timing，否则 TX_VI 无法正确接收。2880x1620 非 V20 制式不支持反向音频。

---

## 相关 skill

| skill | 职责 |
|---|---|
| `sdk-vo-analyse` | VO 显示输出全链路（BT/LCD/sRGB 侧）分析与代码生成；TX 同轴侧问题转本 skill |
| `sdk-tx-analyse`（本 skill） | TX 芯片全链路分析与代码生成 |
