# RC 模式矩阵

## 能力全集

以 `ax_venc_rc.h` 的枚举为全集：H.264/H.265 各有 `CBR`、`VBR`、`AVBR`、`QVBR`、`CVBR`、`FIXQP`、`QPMAP`；MJPEG 有 `CBR`、`VBR`、`FIXQP`。proc 的 `VENC CHN RC ATTR 1` 只为 CBR/VBR/AVBR/CVBR/FIXQP 打印专属字段，QVBR 各专属列为 `-`，QPMAP 通过独立 USER QPMAP 表打印；JPEG 使用独立 `JENC CHN RC ATTR`。因此“覆盖全部模式”必须同时解析这些表，不能只按 RC ATTR 1 的 `RcMode` 判断。

QPMAP 和智能编码（SVC）不占用 `RcMode`，而是叠加在当前模式之上的 QP 干预，各自有独立 proc 表；审查时要先确认底层 `RcMode`，再叠加这两层的影响。

## 公共规则

- 帧级 QP 合法范围为 0..51；最小值不得大于最大值。智能编码在 `AbsQp=N` 时是相对 deltaQp，范围 `[-51,51]`，不能套用 0..51。
- `SrcFr/DstFr`、分辨率、GOP 和码率字段为正值；缺失或 `-` 是未知。
- H.264/H.265 的 GOP 和 I/P 规则适用；MJPEG 是帧内编码，GOP、I/P 比例标记为不适用。
- `SliceIQp/SlicePQp`、CU/CTB QP 限制是另一层约束，不能与帧级 QP 范围混为一谈。

## 模式专属检查

| 模式 | 重点字段 | 典型风险 |
|---|---|---|
| CBR | `TargetBitRate`、QP 边界、`Iprop`、`IntraQpDelta`、GOP、缓冲区 | `MaxQP/MaxIQp` 太低时压缩能力不足；I 帧分配过高可能呼吸或瞬时超码率 |
| VBR | `MaxBitRate`、`enVQ`/质量等级、`ChangePos`、QP 边界 | 质量优先时部分用户 QP 字段不生效；I QP 过低会使 I 帧过大 |
| AVBR | `MinStillPercent`、`MaxStillQp`、`Alpha`、`Beta`、`WeightSum` | 静态场景判断或最大静态 I QP 不合理，码率和画质平衡失控 |
| CVBR | 短期/长期统计时间、长期最小/最大码率、额外码率比例 | 长期约束方向反了或窗口过短，导致码率抖动/超限 |
| FIXQP | `IQp/PQp/BQp`、GOP | 目标码率字段不提供保证；固定 QP 可能随场景产生很大码率变化 |
| QVBR | 版本特定质量/码率字段 | 必须先确认 SDK 结构和实际支持状态，不能直接套 VBR 规则 |
| QPMAP | map 类型、粒度、每帧 map、QP 边界 | 外部 map 缺失/失效；全局 QP 范围不能代表区域实际 QP |
| 智能编码（SVC） | `AbsQp`、`BgIQp/BgPQp`、`TypeNum`、各 `TYPE` 的 `IQp/PQp`、区域数与坐标 | 相对/绝对 QP 用反导致整体偏亮偏暗；背景 QP 抬得过高导致背景糊；区域数或类型越界使部分区域不生效 |
| MJPEG | 质量/QP、单帧大小、目标码率 | 无 I/P/GOP；应分析帧大小和码率，不报告 GOP 异常 |

## QPMAP 与智能编码的可判定阈值

这两项都不是独立的 `RcMode`，而是叠加在当前模式之上的 QP 干预，必须靠独立 proc 表确认。

### QPMAP（`VENC CHN USER QPMAP1/2/LocalMap INFO`）

打印条件：通道已创建、为 H.264/H.265、调用过 `AX_VENC_SetQpMap` 且对应的 `bUseMap` 为真。三张表相互独立，可能只出现其中一张。

- `MbWidth`、`MapSize` 必须为正；`QpMapPhyAddr` 为 0 表示 map 未真正挂上。
- `UseMbuf=Y` 时 `BlkId` 是 mbuf 块号；`UseMbuf=N` 时 `BlkId` 常为 `-1`，不是错误。
- `Finely` 只出现在 QPMAP1/QPMAP2，`LocalMap` 没有该列，按列名取值，不要按列序号。

以下取值域来自 `ax_venc_rc.h`，但 **proc 不打印**，只能从 API 侧确认，不能凭 proc 断言：

| 枚举 | 取值 |
|---|---|
| `AX_VENC_QPMAP_BLOCK_UNIT_E` | NONE=-1、64x64=0、32x32=1、16x16=2 |
| `AX_VENC_RC_QPMAP_MODE_E` | MEANQP=0、MINQP=1、MAXQP=2 |
| `AX_VENC_QPMAP_QP_TYPE_E` | DISABLE=0；DELTA=1，取值 `[-31,32]`；ABS=2，取值 `[0,51]` |

注意绝对/相对 QP 实际是 `stQpMap1` 里**每个块自带的标志位**，同一帧内可混用，通道级枚举不能代表全帧行为；Map 格式、大小计算和下发限制见码控手册第 8 章。另外通道级 `stQpmapInfoV1` 只在 CBR/VBR/AVBR/CVBR 生效，`RcMode` 为 `H264QPMAP/H265QPMAP`、FIXQP、QVBR 时被静默忽略——proc 出现 USER QPMAP 表但 `RcMode` 属于后者时，按「高风险」报告并要求确认是否走了帧级 `AX_VENC_SendFrameEx`。

### 智能编码（`VENC CHN SVC PARAM INFO` / `SVC REGION INFO`）

这里的 SVC 指**智能编码**，即按区域类型和背景分配 QP，与 SVC-T 时域分层编码（码控手册第 10 章）无关，两者不可混用规则。使用约束、参数含义和调参方向见码控手册第 9 章，本节只列 proc 侧的可判定阈值，不重复展开。

打印条件：通道已创建、为 H.264/H.265、且 `bSvcEn` 为真（调用过 `AX_VENC_SetSvcParam` 后置位）；`SVC REGION INFO` 还要求已下发过有效区域。`RC ATTR 1` 的 `SvcEn` 列与该标志同源，两者应一致。

取值域来自 `ax_venc_comm.h`：

- `AbsQp=Y`（`bAbsQp` 为真）时所有 QP 是**绝对值**，范围 `[0,51]`；`AbsQp=N` 时是**相对 deltaQp**，范围 `[-51,51]`。判断前必须先读 `AbsQp`，否则会把合法的负 delta 误判成越界。
- `TypeNum`（`u32RectTypeNum`）范围 `[1,5]`，对应 `AX_VENC_SVC_RECT_TYPE0..TYPE4`；`SVC PARAM INFO` 中 `TypeId` 续行数应等于 `TypeNum`。
- `RectNum`（`u32RectNum`）上限 32（`AX_VENC_SVC_MAX_RECT_NUM`）；`SVC REGION INFO` 中 `RectIdx` 续行数应等于 `RectNum`。
- `BgPQp`（`stBgQpCfg`）建议取非负值：背景 QP 给负 delta 等于给背景加码率，与智能编码省码率的目的相反。
- `RIdx/WIdx/IsFull` 是区域信息缓存的读写指针，只保留最近下发的两组；`ResIdx` 是该条区域记录所在的槽位，不是通道号或帧号。
- `Pts` 是该批区域生效的时间戳，用于和码流帧对齐；proc 以十六进制打印。注意区域 QP 滞后一帧生效，区域略微落后于目标位置属正常现象（见码控手册 9.4）。
- AX615 上 `stBgQpCfg.iQp`（proc 的 `BgIQp`）和 `bBgQpAdapt` 均不生效：背景 I/P 帧统一使用 `BgPQp`。看到 `BgIQp` 配置异常时先说明该字段无效，不要按它推断背景 I 帧质量。
- 智能编码与用户 QPMAP、FIXQP、SkipBias 互斥；同时看到 `USER QPMAP` 表和 `SVC PARAM INFO` 表时按「错误」级报告。

**多行记录**：`SVC PARAM INFO` 每多一个 `TypeId`、`SVC REGION INFO` 每多一个 `RectIdx`，都会多打印一行，且该行前面的列全部留空。按空白切分会把这些续行错认成新记录并整列错位，必须按列宽把续行并回上一条记录。

## `QpDltRng` 列的两种形态

`VENC CHN RC ATTR 1` 中「CU 级 QP 相对 slice/帧级 QP 的差值范围」这一项，在不同 SDK 版本上打印成**两种形态**，两者取自不同字段，不能按同一字段跨版本比较：

| 形态 | 表头 | 含义 | 合法域 |
|---|---|---|---|
| 两列 | `QpDltRngMin` / `QpDltRngMax` | CU QP 相对 slice/帧级 QP 差值的下界与上界 | Min `[-16,0]`、Max `[0,16]` |
| 单列 | `QpDltRng` | 只给一个边界（上界） | `[0,16]`（对外字段注释为 `[2,16]`） |

判定纪律：

- 单列**不代表** `QpDltRngMin=0`，单列形态下 Min 记为「未知」；
- 两种形态不互相换算，结论须结合 proc 头部的 SDK 版本说明；
- 含义：限制块级（CU）QP 的局部调节幅度；范围越窄，平坦区域越难通过下压 CU QP 改善块效应，与「局部发糊/块效应」相关，可结合 `u32IdrQpDeltaRange`、`s32CtuBitsRefQpDeltaRange` 一起看（见码控手册 3.2/3.3）。

## 状态和吞吐字段

- `SrcFr` 是输入/源帧率配置，`DstFr` 是编码输出帧率配置。
- `RecvFps` 是实际收到的帧率，`OutFps` 是实际编码输出/中断帧率；两者不能互换。
- `BitRate(kbps)` 是 proc 当前统计的码率，用于和当前模式的目标/上限做比较。

参数范围和模式校验以实际 SDK 行为为准；当文档、头文件和 proc 输出冲突时，报告冲突并注明版本。
