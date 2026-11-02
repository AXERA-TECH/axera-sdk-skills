# sdk-vo-analysis — AX615 VO 诊断与配置生成 Skill

此 skill 覆盖 AX615（AX615D/AX615Q）视频输出模块（VO）的两类需求：**问题诊断** 和 **配置生成**。全流程只依赖 skill 内化知识（公开头文件副本、54 组已验证时序表、官方 sample 19 组时序、PCLK 离散档位表、版本化行为摘要），不依赖任何外部本地源码目录。

---

## 功能概览

### §A 诊断模式（只读）

适用于：

- VO 黑屏、无输出、显示器 `No Signal`
- 花屏、撕裂、抖动、偏色、帧率不对
- `AX_VO_Init` / `SetPubAttr` / `Enable` / `SendFrame2Disp` 等 API 返回错误码
- 送帧队列积压、超时、帧率不匹配、buffer 生命周期问题
- CSC、DataPinMap、Clip、AspectRatio、输出格式导致的画面/颜色异常
- 通过客户代码、时序参数、`dmesg`、`/proc/ax_proc/vo/display_status` 做证据化排查
- 判断接口组合是否超出 AX615 能力边界

**结论只允许四种终态**：有证据的原因与修复建议 / 信息不足继续追问 / 原因未知 / 场景超出能力无法实现（附替代方案）。**此模式不产出代码改动。**

### §B 配置生成模式

适用于：

- 已知场景（芯片型号、接口、分辨率/帧率、屏规格、源色域）下生成 VO 初始化全流程配置
- 时序求解：SDK 预设模式 → 已验证表查表命中 → 近邻推导/屏规格书校验（三级策略）
- 生成 `AX_VO_PUB_ATTR_T` / `AX_VO_CSC_T` / DataPinMap 参数取值，逐字段标注证据等级
- C 代码骨架（`Init→SetPubAttr→SetDataPinMap→SetCSC→Enable→SendFrame2Disp`，每步返回值检查）
- Python（MicroPython RPC）等价写法
- 送帧与 buffer 建议（池内存/物理地址/VSYNC 节拍/s32MS/InFifoDepth）
- 验证步骤（proc 预期值 + VSYNC 实测帧率 + 回归手段）

**生成终态只有两种**：不可生成（能力/版本闸门未通过，附原因与替代方案，不输出配置）或生成（参数来源分级：已验证表条目 > SDK 预设模式 > 推导值，推导值必须标注"须实机验证"）。

---

## 知识库

skill 内置 `references/ax615/` 内化知识，诊断与生成的首要依据，无需另查外部源码：

- `sdk-inline/ax_vo_api.h`、`ax_global_type.h`：公开 SDK 头文件完整内化副本（字段/枚举/错误码/预设名的权威来源）
- `vo-timing-table.json`：54 组已验证时序表；`sample-vo-timings.json`：官方 sample 19 组时序及冲突说明
- `vo-pclk-table.json`：PCLK 5×16 离散档位表（62 可达值，必须精确命中）
- `vo-sdk-behavior-notes.md`：已授权源码核验的版本化行为摘要（每条带固定版本标注）
- `vo-constraints.md` / `vo-config-reference.md`：诊断与生成约束速查
- `version-manifest.json` / `version-routing.md`：SDK 版本探测、匹配与证据降级规则
- `troubleshooting-playbook.md`：现象分类与取证流程；`grading.md`：Golden Case 判定规则
- `scripts/`：check_vo_timing.py（时序校验）、gen_vo_timing.py（时序求解）、detect_sdk_version.py（版本探测）、kb_query.py（可选 MCP 知识库检索）

---

## 评测与运行资源

[evals/suite.yaml](evals/suite.yaml) 登记 11 个行为用例，输入在 `evals/cases/<case-id>/fixtures/`，独立断言在对应 `assert.sh`。评测时只向分析器提供当前输入和运行知识；原始 Golden Case 的答案由评测方持有。本交付包不提供原内部自动评测工作流，用例与断言不构成实际评测通过的证明。

[scripts/install.py](scripts/install.py) 生成仅含运行资源的安装投影；仓库根目录统一安装入口复制整个所选技能目录。进行盲测时需额外隔离评测材料与运行资源。

知识库检索是可选能力。运行 `scripts/kb_query.py` 前配置 `XIAOZHI_MCP_URL` 和 `XIAOZHI_MCP_AUTH_TOKEN`；缺少配置时退出码为 2，脚本不回显 Token。

---

## 使用方式

在 Claude Code 中输入：

```
/sdk-vo-analysis
```

然后描述你的需求，skill 会根据意图自动选择诊断模式或生成模式。

**示例提问：**

```
# 诊断模式
AX615Q 通过 BT656 输出 1920x1080@30，API 都返回 0，但显示器无信号，请结合时序参数和 proc 分析。

# 生成模式
AX615Q + BT656 输出 1920x1080@30 到显示器，源为 VI 采集的 BT601 YUV420，请生成 VO 初始化全流程配置。

# 诊断+生成
先帮我分析 BT1120 输出 1080p30 偶发卡顿是不是送帧过快，确认后给出修正配置。
```

---

## 注意事项

### 证据链分级，不凭记忆下结论

诊断结论必须分级标注：**已确认（根因）/ 事实确认 / 推测**。文档、知识库与内化副本只能支持"事实确认"，不能单独证明本次故障的因果——把事实连成"本次根因"必须回到客户现场证据（返回值/日志/proc/现象）。修复建议须客户实机改前/改后复现后才可表述为"已验证"。配置参数逐字段标注来源等级，推导值必须附"须实机验证"。

### SDK 版本未知时必须先征得同意

未提供 `display_status` 版本行时，须先询问："SDK 版本未知，当前内化资料基于 V3.14.0。是否同意先按 V3.14.0 作为临时基线继续？" 未获同意前不引用 D/E 级资料下结论。凡引用时序表/PCLK 表/行为摘要，一律带固定版本标注「SDK V3.14.0 实现行为，需按版本核验」。

### PCLK 必须精确命中离散档位表

`u32Pclk` 只能取 5 源 ×16 分频产生的 62 个可达值，**无容差、无就近取整**；非整除档位按源频率截断取整（如 36000÷14 → 2571，不是 2571.43 或 2572）。不命中时 `SetPubAttr` 返回 `AX_ERR_VO_DEV_OP_FAIL`（0x80038A80）并伴 dmesg `unsupport clk`。脚本搜索无解**不构成能力证明**。

### bDlbClk 与 u8DelaySel 不得默认

BT656/601 单沿（SDR）下 `u32Pclk` = 像素时钟×2，双沿（DDR，bDlbClk=1）下 = 像素时钟；两者混配是最常见的黑屏原因。`u8DelaySel` 按所选表条目取值，不得简化为"DDR=3、非 DDR=0"；表条目未记录或客户未提供时记 unknown，不得默认取值。

### 能力边界不妥协

AX615D 不支持 BT1120 与并行 DPI（串行 sRGB 上限 640x480@30）；BT 系接口仅 `YUV422`；RGB 源 + YUV422 输出不能配 IDENTITY CSC；DSI/LVDS/CSI/CVBS 无通路。命中任一能力闸门即输出"场景无法实现"+ 替代方案，不生成无效配置。预设模式名由公开头文件确认，但**不豁免** PCLK 与能力校验。

### 来源隔离

skill 内不出现实现侧源码路径/文件名/内部符号名/源码行号；实现行为只引用 `vo-sdk-behavior-notes.md` 的行为约束并带版本标注。不访问 skill 目录以外的路径与外部源码树；用户显式提供的文件（日志/proc/代码/屏规格书）允许读取。

---

## 相关 skill

| skill | 职责 |
|---|---|
| `sdk-vo-analysis`（本 skill） | VO 显示输出全链路（BT/LCD/sRGB 侧）诊断与配置生成 |
| `sdk-tx-analyse` | AX_TX 同轴发送芯片分析与代码生成；VO BT 输出对接 TX 芯片的通路问题转该 skill |
