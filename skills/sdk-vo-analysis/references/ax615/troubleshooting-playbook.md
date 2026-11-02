# AX615 VO 问题排查剧本

> 本剧本只提供**排查方向与证据位置**，不充当行为事实。任何 API 语义、参数取值、
> 错误码含义的最终结论必须回到 [vo-constraints.md](vo-constraints.md)（内联约束速查）、
> 知识库文档（AX VO API 文档 / 开发指南 / 错误码文档）、公开头文件内化副本
> [vo-api-inline.md](vo-api-inline.md) / [sdk-inline/](sdk-inline/) 或
> [vo-sdk-behavior-notes.md](vo-sdk-behavior-notes.md)（版本化行为摘要）复核。
> 时序相关确定性计算（刷新率、PCLK 档位、表比对）一律用 `scripts/check_vo_timing.py`，
> 不要心算。下述"常见原因"是排查假设的候选排序，需用第 3、4 步的证据确认。
> 证据链分三段：文档/内化条目用于**事实确认**，与现场证据（返回值/日志/proc/复现规律）连成
> 因果链才构成**根因确认**，修复建议经客户实机复现才算**修复验证**；**文档条目不能单独
> 证明本次故障的因果**（详见 SKILL.md 第 5 步）。

## 0. 图像现象解读（照片/截图）

客户贴出现场照片/截图时，先提取**可辨识的客观特征**再归类，图像只用于现象定性，
**不能单独充当根因证据**（根因必须回到 proc/API 返回值/时序表/文档）。

| 图像特征 | 现象定性 | 候选方向 |
|---|---|---|
| 显示器显示"无信号 / No Signal / Out of Range" | 未收到有效同步信号 | 第 1、5 节（使能/时序/接口） |
| 黑屏但有背光（或 OSD 正常显示） | VO 链路可能已使能但无有效数据 | 第 1、4 节（SendFrame2Disp/buffer） |
| 雪花 / 彩条 / 满屏噪点 | 有信号但内容无效 | 第 2 节（buffer 复用、DataPinMap） |
| 整体偏色（偏红/偏绿/偏蓝/黑白颠倒） | 颜色空间转换或线序问题 | 第 3 节（CSC、线序、Clip） |
| 画面下半部分错位/滚动、垂直方向异常 | 垂直时序或隔行误配 | 第 2 节（bIop、vporch） |
| 横向撕裂位置固定 | 帧 buffer 被改写 | 第 2 节（buffer 提前复用） |
| 画面完整但持续抖动 | 时序/时钟边缘不稳定 | 第 2 节（pclk/dblclk 组合） |
| 四周有黑边/图像偏移 | LBA（AspectRatio）补边或 crop 参数 | 第 2 节（crop/LBA 参数） |

提取特征时只记录图像中客观可见的内容，不确定的特征（如照片过曝无法判断背光）如实
标注"无法从图像判断"。图像特征与 proc/日志证据矛盾时，以 proc/日志为准并说明。

## 1. 黑屏 / 无输出

**常见原因候选（按概率排序）**
1. 初始化/调用顺序错误（Init → SetPubAttr → SetDataPinMap → SetCSC → Enable → SendFrame2Disp；
   退出 UnReg → Disable → Deinit）
2. `AX_VO_SetPubAttr` 参数错误：分辨率/帧率/同步极性与显示屏不匹配
3. **PCLK 未精确命中离散档位表**（[vo-pclk-table.json](vo-pclk-table.json)，无容差）——
   此时公开 API 返回 `AX_ERR_VO_DEV_OP_FAIL`，内核日志出现 `unsupport clk`
4. 输出接口类型配置错误（BT656/BT1120/DPI/Coax 的 dblclk、格式、DataPinMap 差异）
5. `AX_VO_Enable` 返回错误（查错误码含义；注意 Enable 本身不校验时序）
6. 时序字段错误（bIop 与屏扫描方式不符、porch 与屏规格不符、u8DelaySel 未按条目取值）

**证据位置**
- 客户日志中各 API 返回值（重点：SetPubAttr/Enable/SendFrame2Disp）+ **dmesg**
- `/proc/ax_proc/vo/display_status`（ScanType/Refresh/Pclk/HTimings/VTimings/PinMap）
- 知识库：`AX VO 开发指南.docx` → "LCD 屏调试"章节；`AX VO API 文档.docx` → AX_VO_Enable/SetPubAttr 描述与注意事项
- 标准调用序列见 vo-constraints.md 第 1 节（源自官方 sample）

> 注意：`AX_VO_EnumMode` 在本实现返回不支持，**不能**用"枚举支持模式"的方式排查；
> 支持模式的排查入口以公开头文件的预设枚举与已验证时序表为准（预设名只由头文件确认，
> 是否可用仍须按当前 SDK 的离散 PCLK 与接口/芯片能力校验）。

## 2. 花屏 / 撕裂 / 抖动

**常见原因候选**
1. 时序参数与屏规格不符（Hact/Vact/Hfp/Hbp/Hsync 等）→ 对照两张时序表（54 组已验证 + 19 组 sample）
2. 帧 buffer 生命周期问题：`AX_VO_SendFrame2Disp` 后客户释放/复用 buffer 过早；
   **区分 SDK 池内存的 block 释放与直接覆写物理 buffer**（后者绕过引用计数，必现撕裂）
3. 隔行/逐行模式（bIop）配置错误
4. 双沿时钟（dblclk）场景像素时钟算错；`u8DelaySel` 未按条目取值
5. 帧 stride 未按 16 字节（非压缩）或 128 字节（FBC）对齐；crop/LBA 参数越界
6. 源尺寸小于输出尺寸且未开 LBA（见第 4 节与 vo-constraints.md 第 6 节）

**证据位置**
- 两张时序表：与客户时序逐字段对比（含 bDlbClk；u8DelaySel 缺失或表未记录按 unknown，不得默认）
- `AX VO API 文档.docx` → `AX_VO_SendFrame2Disp`（buffer 生命周期要求）、`AX_VO_PUB_ATTR_T` 字段说明
- 客户侧可验证：更换到表中已知时序（如 1920x1080@30 bt656 / bt1120）看现象是否消失

## 3. 颜色异常（偏色 / 反色 / 黑白颠倒）

**常见原因候选**
1. CSC 配置错误或未设置 → `AX_VO_SetCSC`/`AX_VO_GetCSC`（默认 BT601_TO_BT601；
   SetCSC 合法状态为「已配置/已使能/已 Disable」，Enable 前后均可调用）
2. 数据位宽/顺序配置与屏不匹配（DataPinMap、YUV 格式、DPI 并行/串行格式）
3. Clip 参数（默认输出范围 Y 16-235、Cb/Cr 16-240）与屏要求不符
4. 帧结构体色域字段（`stColorGamut`/`stDynamicRange`）与实际源不一致
5. BT656/BT1120 内嵌同步模式 vs LCD(DPI) 分离同步差异

**证据位置**
- `AX VO API 文档.docx` → CSC 相关 API 与 `AX_VO_CSC_T`
- 官方 sample 的 CSC 使用方式（SetPubAttr 之后调用）

## 4. 帧率不对 / 卡顿

**常见原因候选**
1. 时序表中帧率字段与目标不符；**刷新率按配置公式值核对，并以 proc `Refresh`/`OutFps` 实测为准**
2. VSYNC 回调计数与预期不一致 → `AX_VO_VSYNC_RegCallbackFunc` 实测帧率
3. SendFrame2Disp 失败导致丢帧：**公开 API 该失败可能被包装为 `AX_ERR_VO_DEV_OP_FAIL`**，
   须结合 dmesg 与 proc（`InFifoSize`/`DiscFrames`/`InFps`/`OutFps`）判断真实原因
4. 送帧率 > 显示刷新率导致 FIFO 积压（默认深度 3）
5. 带宽/DDR 不足（结合 `/proc/ax_proc/bw_limit`）

**证据位置**
- `AX VO API 文档.docx` → VSYNC 回调、proc display_status 字段说明
- 官方 sample 的 VSYNC 节拍送帧方式

> 注意：`AX_VO_QueryChnStatus` 在本实现返回不支持，**不能**用它判断待显示图像数/积压；
> 改看 proc 的 `InFifoSize`/`DiscFrames`/`InFps`/`OutFps`。

## 5. 初始化/使能失败（返回非 0）

**排查顺序**
1. 查返回值对应错误码 → `AX VO API 文档.docx` 错误码章节 / `ax_vo_api.h` 枚举
2. **查 dmesg 驱动日志**（`unsupport clk`、vsync 未注销提示等关键字）
3. 确认调用状态机：Enable 后改配置须先 Disable；Deinit 前须 Disable；未 Init 时的返回码见
   vo-sdk-behavior-notes.md 第 2 节
4. 确认是否重复 Init / 未 Deinit 后重新 Init / VSYNC 回调未注销

## 6. 分辨率不支持 / 无法枚举

**排查方向**
1. **不要用 `AX_VO_EnumMode`**（本实现返回 `AX_ERR_VO_NOT_SUPPORT`）
2. 芯片 VO 支持能力上限 → `AX VO API 文档.docx` 的显示能力表；AX615D/Q 差异见 vo-constraints.md 第 2 节
3. 自定义时序：目标 PCLK 是否精确命中 [vo-pclk-table.json](vo-pclk-table.json)；
   帧宽高是否满足 [16,3840]/[4,8190] 且 2 对齐
4. 特殊时序（隔行、dblclk、BT656 8bit、DPI 串行 sRGB）的格式与压缩限制见 vo-constraints.md 第 6 节
5. **求解失败不是能力证明**：脚本的无解/差异提示只说明给定参数或当前搜索空间的问题；
   "分辨率不支持/场景无法实现"必须回到能力表、约束条目与时序表（见 vo-config-reference.md 第 4/8 节）

## 7. 客户代码审查（调用 SDK 接口的代码）

客户贴出调用 SDK 接口的代码时，逐项核对以下清单；代码能**直接证明用法/配置错误**，
但修复建议与"场景可实现"结论仍须引用约束表/文档条目。

1. **调用顺序**：`Init → SetPubAttr → (SetDataPinMap) → (SetCSC) → Enable → SendFrame2Disp`；
   退出 `UnReg → Disable → Deinit`（对照 vo-constraints.md 第 1 节，源自官方 sample）
2. **参数字面值**：时序字面值提取后跑 `check_vo_timing.py`（PCLK 精确命中、bDlbClk 参与比对）；
   错误码 hex 对照 `ax_vo_api.h` 与错误码文档；CSC 矩阵取值对照 `ax_vo_api.h:280-295`
3. **返回值处理**：每个 `AX_VO_*` 返回值是否检查/打印；**任何非 0 返回值都是首要线索**；
   注意公开 API 的包装语义（队列满/超时表现为 `AX_ERR_VO_DEV_OP_FAIL`，须配 dmesg 判断）
4. **buffer 管理**：来源（SDK 池内存 / `AX_SYS_MemAlloc` vs 裸 malloc）、`u64PhyAddr` 是否
   物理地址、`SendFrame2Disp` 后是否立即复用/释放；池 block 释放与直接覆写物理 buffer 要区分
   （对照 vo-constraints.md 第 5 节）
5. **s32MS 取值**：-1 阻塞 / 0 非阻塞 / 正值超时等待，与客户代码注释声称的语义是否一致
6. **帧结构体**：宽高/stride 对齐、格式白名单、plane 地址与 block id、crop 参数（vo-constraints.md 第 6 节）
7. **生命周期**：重复 Init、未 Deinit 后重新 Init、多通道混用
8. **线程/并发**：多线程同时 `SendFrame2Disp`、VSYNC 回调与送帧线程的竞态
9. **芯片能力边界**：代码中的接口/格式组合是否超出 AX615D/Q 能力（如 AX615D 代码里配
   BT1120/并行 DPI（串行 sRGB 超 640x480@30 同属越界）、调用 Layer 级接口、使用 DSI/LVDS）→ 命中即终态 4（场景无法实现），引用
   vo-constraints.md 对应条目（**不以脚本求解无解为证据**）
10. **客户断言/前提校验**：客户对错误码含义（尤其"超时码/队列满码"）、API 参数语义（如 s32MS）、
    "芯片出厂缺陷/SDK bug"类断言，必须先对照内化副本（vo-api-inline.md / vo-constraints.md /
    vo-sdk-behavior-notes.md）核实，才能作为推理前提。十进制错误码先还原 hex 再查表；
    客户代码注释与官方文档语义冲突时，以官方文档为准，并在结论中明确指出客户前提的错误之处

## 8. 给客户的验证手段（速查）

| 手段 | 命令/方式 | 作用 |
|---|---|---|
| VO 状态 | `cat /proc/ax_proc/vo/display_status` | 显示状态权威信息（ScanType/Refresh/Pclk/FIFO/丢帧/PinMap） |
| 驱动日志 | `dmesg` | PCLK 不命中（`unsupport clk`）、vsync 未注销等 |
| 帧率实测 | VSYNC 回调计数 | 确认实际输出帧率 |
| 标准时序回归 | 换成已验证表中的已知时序（如 1920x1080@30 bt656） | 隔离时序问题 |
| 官方 sample 序列 | 对照 vo-constraints.md 第 1 节标准调用序列（源自官方 sample） | 隔离客户应用用法问题 |
| PCLK 档位 | `python3 scripts/check_vo_timing.py --json '<时序>' --intf bt656\|bt1120\|dpi --fmt <格式>`（**`--intf dpi` 必填 `--fmt`**，如 srgb565） | 精确命中判定 + 表比对（求解/校验无解不构成能力证明） |

> 不要使用 `AX_VO_EnumMode` / `AX_VO_QueryChnStatus` 作为验证手段（本实现返回不支持）。

## 9. 偶发问题（概率性、与温度/时长相关）

- 要求客户记录出现时的 `/proc/ax_proc/vo/display_status` 与 dmesg
- 关注 buffer 复用竞态、送帧节拍（VSYNC 回调）、时钟抖动
- 若会话中有代码评审系统查询工具，查 ax615 分支近期合并，确认是否已知问题及修复版本；工具不可用时按 SKILL.md 的 Gerrit 降级规则处理
