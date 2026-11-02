# AX_SYS_Link_V2 判定规则

## 参数语义

`AX_MOD_LINK_ATTR_T` 包含：

- `eDataFlowMode`：`SW_LOW_MEM`、`SW_LOW_LATENCY`、`SW_OFFLINE` 或 `HW_ONLINE`。
- `nRingLineCnt`：仅 `SW_LOW_MEM` 使用。非零时必须在 `128..3840` 范围内，并且是 `64` 的整数倍。
- `eSrcEngine`、`eDstEngine`：HSK 两端 engine。`SW_OFFLINE` 时两者必须为 `AX_ENG_NONE`。

《53 - AX SDK典型场景使用说明》的模块间数据流转章节补充：

- LowMem 是 Ring Buffer/HSK 行同步模式，通常 IVPS→VENC 最小推荐 `128` 行。
- IVPS→VENC 的 H26x 典型配置为 `eSrcEngine=AX_ENG_VPP`、`eDstEngine=AX_ENG_VENC`。
- JENC 与 VENC 建立 SYS link 时统一使用 `AX_ID_VENC`；engine 可按实际编码类型区分 `AX_ENG_JENC`、`AX_ENG_VENC`。
- LowLatency 与 Offline 是整帧流转，`nRingLineCnt` 不生效。

《04 - AX SYS API 文档》的 `AX_SYS_Link_V2` 接口说明还约束：

- 一对多最多连接 6 路；多对一只支持二对一，同一目的端最多 2 个源。
- JENC 和 VENC 建链时模块 ID 均填写 `AX_ID_VENC`，不能使用 `AX_ID_JENC`；实际硬件路径由 `eDstEngine` 区分。

## HSK 硬件约束表

《53 - AX SDK典型场景使用说明》2.1 节给出 HSK 各段链路的参数建议与硬件约束，这张表是判断“配置合法但不工作”的主要依据：

| 链路 | 建议模式与参数 | 硬件约束 |
| --- | --- | --- |
| VIN(IFE-ITP) | 非此 link 接口配置 | 单摄 `AX_VIN_LATENCY_MODE_SLICE`（partition=512）；双摄 `AX_VIN_LATENCY_MODE_FRAME` |
| VIN → IVPS(GDC) | `SW_LOW_MEM`，`nRingLineCnt=256` | **LowMem 不支持 90/270 旋转，不支持 Ezoom/LDC；文档建议改用 SW_OFFLINE** |
| IVPS(VPP/VGP) → VENC(VENC/JENC) | `SW_LOW_MEM`，`nRingLineCnt=128` | **VENC 不支持裁剪 / 重编码 / 帧率放大** |

两条约束都不在代码校验范围内，见下节「约束的执行边界」。

旋转流程本身还有一条时序要求：AX615 使用 `AX_IVPS_StopGrp`/`AX_IVPS_StartGrp`，且**由于 HSK 功能硬件约束，必须先停止 IVPS 及 VENC 模块后调用 VIN 旋转**（`AX_VIN_SetChnRotation`）；文档建议非 HSK 流程也保持一致。

## 合法 engine 绑定矩阵

《04 - AX SYS API 文档》5.6 链路管理给出 `SW_LOW_MEM` 与 `SW_LOW_LATENCY` 允许的源/目的 engine 组合，两者矩阵相同：

| 数据源 | 源 engine | 数据接收者 | 接收者 engine |
| --- | --- | --- | --- |
| VIN | — | IVPS | `AX_ENG_GDC` |
| IVPS | `AX_ENG_VPP` | VENC | `AX_ENG_JENC`、`AX_ENG_VENC` |
| IVPS | `AX_ENG_VPP_VGP` | VENC | `AX_ENG_JENC`、`AX_ENG_VENC` |

补充约束：

- `SW_LOW_MEM`、`SW_LOW_LATENCY`、`HW_ONLINE` 是前后级同步工作模式，必须显式指定 engine（`AX_ENGINE_LOWLATENCY_E`）。
- **AX615 项目当前不支持 `HW_ONLINE` 交互模式。**
- `SW_OFFLINE` 模式下表外还有 VIN→VO/VENC/IVPS/AVS、IVPS→VO/VENC/IVPS/VIN、VDEC→VO/VENC/IVPS 等组合，且要求 engine 置 `AX_ENG_NONE`。
- 内核只按上表校验模块对与 engine（`ax_sys_link.c:499-529`），越界组合在建链时返错，属于可自证的失败。

## 修改已有 Link 关系的顺序

《04 - AX SYS API 文档》明确：**修改 Link 关系时必须先停止前后级模块，再 `AX_SYS_UnLink` 解除当前关系，最后重新启动前后级模块。**

这条与「HSK 模式下的参数切换时序」是同一约束的两个视角：前者约束 unlink 动作本身的前置条件，后者约束分辨率/编码类型变更时的完整调用序列。只 unlink 而不停模块，或停了模块却漏掉 unlink 直接重新 link，都属于偏离。

## 约束的执行边界

上述硬件约束在代码里的校验情况并不一致，判断时先分清哪一类：

| 约束 | 代码行为 | 诊断方式 |
| --- | --- | --- |
| `nRingLineCnt` 非法 | `AX_SYS_Link_V2` 直接返错（`msp/component/sys/ax_sys_api.c:313`） | 日志签名唯一，建链即失败 |
| Offline 模式 engine 非零 | 同上 `:318-323` 返错 | 同上 |
| 模块对/engine 方向非法 | 内核 `ax_sys_link.c:499-529` 返错 | 同上 |
| **LowMem 下 VIN→IVPS 开 90/270 旋转** | **建链不拦**；运行期 `AX_VIN_SetChnRotation` 可能返 `0x80110114`，应用仍可能继续改 IVPS 几何 | 组合证据：LowMem VIN→IVPS/GDC、旋转动作、VIN ioctl 失败、VIN 几何未变、IVPS 几何已变 |
| **LowMem 下 VIN→IVPS 开 LDC** | **建链不拦**；本包 `AX_ISP_IQ_SetLdcParam` 可成功，VIN WARP `LDC=1`，IVPS GDC `DewarpType=LDC` 且继续出流 | 不要仅凭文档“不支持 LDC”判失败；看 SetLdcParam 是否失败、GDC Fail1、OutFps |
| **LowMem 下 VIN→IVPS 开 Ezoom** | **建链不拦**；尚无 golden 实测 | 缺 proc 时保持 `INCONCLUSIVE` |
| **IVPS→VENC LowMem 帧率放大（H264/HEVC）** | H26x 打开 `bAllowFrameEnlarge`，sync_agent 放行 `DstFrameRate>SrcFrameRate` | venc.proc 可见 SrcFr 小于 DstFr 且 OutFps 接近目标；不是失败 |
| **IVPS→VENC LowMem 帧率放大（JPEG/JENC）** | JPEG 传 `bAllowFrameEnlarge=FALSE`，sync_agent 打 `illegal parameters in eDataFlowMode` | 直接日志 |
| **IVPS→VENC LowMem 下 VENC 裁剪/重编码** | `VencCalCheckCropAttr`（`venc_param_check.c:1532`）不含 HSK 判断 | 尚无 golden；缺证据时 `INCONCLUSIVE` |
| 未停模块即改 Link / 切换时序漏步 | 各接口独立返回 `0x0` | 静默失败，需组合证据 |

`AX_VIN_SetChnRotation` 的调用链同样不含 HSK 判断：`ax_vin_chn_api_impl.c:237` → `ax_hal_channel_set_rotation`（`sys_hal_chn_impl.c:205`）只做 pipe/chn 号检查后直接下发 ioctl，旋转与 link 模式是否相容不在检查范围。

LowMem 旋转不是建链参数校验：`AX_SYS_Link_V2` 和 `AX_VIN_SetChnRotation` 用户态都不根据 link 模式拒绝 90/270。实测运行期 ioctl 可能返回 `0x80110114`（VIN 模块），VIN 通道 Rotation 仍为 0；但 FRTDemo 的 `CIPCBuilder::UpdateRotation` 在 `CBaseSensor::UpdateRotation` 失败后仍继续改 IVPS/VENC 几何。因此不要把该错误码写成“建链拒绝旋转”，也不要因为没有“不支持旋转”字样就判成静默失败。

LDC 同样建链不拦。FRTDemo TestSuite 走 `UpdateLDC` → `AX_ISP_IQ_SetLdcParam`；AXDF-006 在 VIN→IVPS LowMem（line_cnt=0、dst GDC、distor_ratio=2000、x/y_ratio=50）下 SetLdcParam 成功，VIN WARP `LDC=1`，IVPS GDC `DewarpType=LDC` 且 Fail1=0、主码流约 30fps。不要把文档旧句“LowMem 不支持 LDC”单独写成根因。Ezoom 尚无 golden。

H264/HEVC LowMem 允许帧率放大：`h26x_enc_cal.c` 置 `bAllowFrameEnlarge=TRUE`，`ax_venc_sync_agent.c` 因此不拒绝 `DstFrameRate>SrcFrameRate`。AXDF-007 把 encoder `frame_rate` 改成 60 后，venc.proc 为 SrcFr 30 / DstFr 60，OutFps 约 60。JPEG/JENC 才传 `NI_FALSE` 并打 `illegal parameters in eDataFlowMode`。缺少 proc 时保持 `INCONCLUSIVE`。

## IVPS 二对二 HSK 与编码类型约束

《53 - AX SDK典型场景使用说明》的 N8 二对二示例同时输出两路：

- 主码流：`IVPS(0,0) -> VENC(0,0)`，LowMem 128 行，`VPP -> VENC`，支持 H264/H265。
- JPEG：`IVPS(0,1) -> VENC(0,1)`，LowMem 128 行，`VPP_VGP -> JENC`。

这两路属于 IVPS 分流的同时输出，不是可错峰复用同一硬件的两条配置。同一个硬件不能支持两路 JENC HSK 同时工作，因此 chn1 已使用 HSK JPEG 时，主码流 chn0 不能再配置为 MJPEG/JENC HSK。N8 文档明确标注 `venc0` 不支持从 H26x 切换到 MJPEG；相关一对二/二对二流程也标注硬件不支持用 unlink 完成这种切换。

一对一 HSK 场景的动态 H26x/MJPEG 切换不能类推到 N8：一对一切换时必须停止通道、unlink、按编码类型修改 `eDstEngine` 为 `VENC` 或 `JENC` 后重新 link，并重建编码通道。分流场景仍必须保证任一时刻只有一路占用 JENC HSK，或将其中一路改为 Offline 等非 HSK 方案。

## HSK 模式下的参数切换时序

《53 - AX SDK典型场景使用说明》2.4 节「IVPS与VENC切换」：HSK 模式下 IVPS 与 VENC 之间有严格时序约束，切换分辨率、编码类型等参数会涉及通道的销毁重建，**VENC 通道停流时 IVPS 必须 disable 对应通道**。

标准切换序列：

```text
AX_IVPS_DisableChn
  -> AX_VENC_StopRecvFrame
  -> AX_VENC_DestroyChn
  -> AX_SYS_UnLink
  -> AX_SYS_Link_V2
  -> AX_IVPS_GetPipelineAttr / AX_IVPS_SetPipelineAttr
  -> AX_VENC_CreateChn
  -> AX_VENC_StartRecvFrame
  -> AX_IVPS_EnableChn
```

不同拓扑的编码格式变化流程不同，判断违规前先确认拓扑：

| 拓扑 | 流程 | 关键差异 |
| --- | --- | --- |
| 一对一 `VPP -> VENC`（场景一主码流） | 1. stop venc & disable ivps chn；2. destroy venc / unlink→link；3. start venc & enable ivps chn | 允许用 unlink→link 完成切换 |
| 一对二 `VPP -> VENC/JENC`（场景二主码流） | 1. stop venc & stop JENC & disable ivps chn；2. destroy venc chn；3. start venc & start JENC & enable ivps chn | 硬件不支持 unlink 切换，必须 destroy 重建 |
| 二对二 `VPP_VGP -> JENC`（场景三主码流） | 1. stop jenc & disable ivps chn；2. destroy jenc chn；3. start jenc & enable ivps chn | unlink 实际使用没有意义 |

### 校验边界

这条时序在代码里没有任何校验。`AX_IVPS_SetPipelineAttr`、`AX_IVPS_DisableChn`、`AX_VENC_DestroyChn`、`AX_SYS_UnLink` 各自独立返回成功，漏步或顺序颠倒都不会返错，问题只在数据流阶段暴露为断流、卡死或花屏。因此这类问题必须靠组合证据判断，不存在唯一的错误返回码。

### 当前 SDK 中偏离该时序的路径

camera-kit 的三个入口在 HSK link 存在时修改 pipeline attr，均未与 VENC 侧协同：

- `IVPS_SetChnAttr`（`camera-kit/service/mid/axck_ivps/ivps.c:1275`）：直接调用 `AX_IVPS_SetPipelineAttr`，既无 `AX_IVPS_DisableChn`/`EnableChn`，也无 VENC 停流重建。
- `IVPS_SetGrpAttr`（同文件 `:1258`）：同样直接下发 `AX_IVPS_SetPipelineAttr`。
- `IVPS_FPSControl`（同文件 `:1305`，对外入口 `AXCK_IVPS_FPSControl`）：有 `AX_IVPS_DisableChn` → `AX_IVPS_SetPipelineAttr` → `AX_IVPS_EnableChn`，但缺少 `AX_VENC_StopRecvFrame`/`DestroyChn`/`UnLink`/`Link_V2`/`CreateChn`/`StartRecvFrame`。

是否实际触发问题取决于被修改的参数是否影响 HSK 行同步几何（`maxH`、`EncH`、`ringLCnt`、`minhskLin`）：仅改 FRC 目标帧率时几何不变，改分辨率则直接改变几何。**上述路径尚未在板端验证过失败表现，分析时只能作为可疑点提出，不能直接当作已确认根因。**

## 高置信度日志签名

### 非法 nRingLineCnt

直接证据：

```text
Link failed!Invalid nRingLineCnt ,nRingLineCnt=<value>
```

结论：`AX_SYS_Link_V2` 的 LowMem `nRingLineCnt` 非法。若值非零，检查 `<128`、`>3840` 或不能被 `64` 整除。返回码通常为 `AX_ERR_LINK_ILLEGAL_PARAM`（`0x800B030A`）。

上层常见传播链：

```text
Linkage setup: (<src>) => (<dst>)
Linkage failed (<src>) => (<dst>)
PPL build failed.
```

`PPL build failed` 只说明构建失败；必须结合前面的 SYS 错误判断根因。

部分 FRTDemo 版本只记录 `Linkage failed` 并继续启动，后续可能出现对应 VENC channel 的 `AX_VENC_StartRecvFrame failed`。这些是 Link 建立失败的传播结果，不能据此改判为 VENC 初始化或码控错误。

### AXDF-001 运行包 token

SDK V3.12.0 golden case AXDF-001 中，非法 `nRingLineCnt` 的 SYS 错误被压缩为：

```text
@AXLOG2,5e3f7a29,00000001,6ce072bd,0
```

该 token 与紧随其后的 `IVPS(0,0) -> VENC(0,0)` `Linkage failed` 同时出现时，可判定该 Link 的 LowMem `nRingLineCnt` 参数非法。token 未携带实际参数，必须将实际值写为“未知”，除非输入还提供了配置或可匹配的 AXLOG 字典。此映射仅适用于 AXDF-001 对应的 SDK V3.12.0 运行包，不得泛化到其他 revision。

### Offline engine 非零

直接证据：

```text
DstEngine and Srcengine should be zero when flowmode is sw_offline
```

结论：`eDataFlowMode=AX_MOD_DATA_FLOW_SW_OFFLINE`，但 `eSrcEngine` 或 `eDstEngine` 未设为 `AX_ENG_NONE`。

### 二对二同时占用两路 JENC HSK

高置信度需要组合证据，不能只凭一条 timeout：

1. 应用日志确认主码流为 MJPEG，例如 `VENC attr: chn:0, encoder:1002`，同时存在 `JENC attr: chn:1`。
2. `link_table_kernel` 同时出现 `VPP -> JENC` 和 `VPPVGP -> JENC` 两路 `SW_Low_Mem`，且来自同一 IVPS group 的两个分流 channel。
3. 随后串口出现 `VPP[2] timeout`，IVPS proc 显示相关 channel 无输出或 online task 卡住。

满足以上组合时，结论为 IVPS 二对二分流同时占用两路 JENC HSK，违反硬件约束。后续常见传播包括 VIN/CMM `Get block fail`、IVPS stop/disable 超时以及整条 pipeline 无输出；这些是上游堵塞后的结果，不能倒因为 pool 配置不足。

若只有 `VPP timeout` 而缺少编码类型或 `link_table_kernel`，必须保持 `INCONCLUSIVE`，补齐完整 input 后再判断。若主码流是 MJPEG 但其 link 仍为 `VPP -> VENC`，还存在编码类型与 `eDstEngine` 不匹配的问题，不能只归因为双 JENC HSK。

### 参数切换时序违规

没有唯一的错误返回码，必须靠组合证据；缺任意一项都保持 `INCONCLUSIVE`：

1. 日志中存在运行期参数切换动作，且切换发生在 HSK link 建立并已正常出流之后。应用侧看分辨率或编码类型变更记录，例如 `ChnFilter reset resolution for ivps (Grp: n, Chn: n)`；camera-kit 路径的可见签名例如 `Change dest framerate to <value> successfully.`。
2. 切换动作附近**只有 IVPS 侧调用**（`AX_IVPS_DisableChn` / `AX_IVPS_SetPipelineAttr` / `AX_IVPS_EnableChn`），没有任何 VENC 侧的停流、通道重建或重新起流记录。这些 IVPS 调用全部返回 `0x0`。
3. `link_table_kernel` 中该 link 在切换后依然存在（如 `Engine (1:VPP --> 4:VENC)` 的 `SW_Low_Mem`），说明没有走 `AX_SYS_UnLink`/`AX_SYS_Link_V2` 重建。
4. `venc.proc` 的 HSK STATUS 里 `maxH`/`EncH`/`EncHPre` 仍是切换前的旧高度，VENC 通道属性中的宽高也仍是旧分辨率；`bFrmDrop` 由 `0` 变为 `1` 并保持。字段判读见 [venc-hsk-proc.md](venc-hsk-proc.md)。
5. VENC 帧率归零、`recv` 计数停滞，但进程仍存活。

AX615 实测（SDK 2026-09 运行包，FRTDemo scenario 1，`IVPS(0,0) -> VENC(0,0)` LowMem 128 行）的典型时间线：

```text
VENC: [0] fps 30.60, recv 306      <- 切换前正常出流
ChnFilter reset resolution for ivps (Grp: 0, Chn: 0): 2688x1520 -> 1280x720
AX_IVPS_DisableChn(0, 0) ret=0x0
AX_IVPS_SetPipelineAttr(0) ret=0x0
AX_IVPS_EnableChn(0, 0) ret=0x0
VENC: [0] fps  1.10, recv 317      <- 切换后骤降
VENC: [0] fps  0.00, recv 317      <- 随后持续为 0
```

**注意 `hskCnt` 在这类故障中仍会持续增长，`errDropCnt` 可能一直为 `0`**：握手线程本身没有停，只是因为几何不匹配而丢弃每一帧。因此不能用 `hskCnt` 停滞作为本类问题的判据，真正的判据是 `bFrmDrop=1` 加上 `EncH` 与 IVPS 新分辨率不一致。

与「二对二同时占用两路 JENC HSK」的区分：后者从建链起就错，首帧之前即卡住；时序违规则表现为**切换前数据流正常、切换后才断**，时间线上的这个分界是主要判据。

仅凭帧率归零不能定论 —— 上游断流同样会让帧率归零。必须确认切换动作发生在帧率下降之前，且切换后 link 仍在、VENC 几何仍是旧值。

### 正确实现的参考

`app/component/builder/ipc/IPCBuilder.cpp` 的 web 分辨率切换分支是合规实现，可作为对照：依次执行 IVPS `EnableChannel(false)` → VENC `StopRecv` → VENC `ResetChn` → IVPS `UpdateChnResolution` → VENC `UpdateChnResolution` → VENC `StartRecv` → HSK 场景下的 `UpdateHSKJenc` → IVPS `EnableChannel(true)`。分析客户问题时，如果对方走的是自有控制层而非该路径，优先怀疑漏步。

另外，`AX_IVPS_SetPipelineAttr` 对**正在运行**的 group 修改分辨率会被静默忽略（返回 `0x0` 但几何不变），必须先 `AX_IVPS_DisableChn` 才会真正下发。这既是时序要求，也是变更生效的前提；只改 `nDstPicWidth`/`nDstPicHeight` 而不同步 `nDstPicStride`、或只改两个 filter 中的一个，同样不会生效。

## 部分通道 HSK / merged trigger

参数层面 `AX_SYS_Link_V2` 仍可建链成功；失败点在 IVPS scheduler 对 merged filter 的 HSK trigger 扫描。同一 IVPS group 内部分通道关 HSK、部分通道开 HSK 时，旧逻辑可能因当前 ctx 不是 `hsk_src` 而漏扫仍为 `hsk_src` 的 sibling。现象与判读见 [hsk-stream-failure-patterns.md](hsk-stream-failure-patterns.md) M1，不要在缺 link/通道 enable 证据时写成已确认内核根因。

## mode=1 双向 HSK 运行期旋转

mode=1 双向 HSK（VIN→IVPS，src NONE dst GDC）运行期开 90/270 旋转会被驱动拒绝，与上文 LowMem VIN→IVPS 不支持 90/270 一致。详见已有旋转约束节与 [hsk-stream-failure-patterns.md](hsk-stream-failure-patterns.md) M3。

## 先非 HSK 再切 HSK / 只 stop 一路 VENC

先跑非 HSK 再切 HSK 出现 start recv frame fail，或 HSK 下只 stop 一路 VENC 导致其他 IVPS chn 帧率异常：见 [hsk-stream-failure-patterns.md](hsk-stream-failure-patterns.md) 余下签名。不要默认并进双 JENC 或 nRingLineCnt 非法。

## 证据来源

- `53 - AX SDK典型场景使用说明.docx`，第 2 章“模块间数据流转模式”；2.4 节“IVPS与VENC切换”给出切换时序与三种拓扑的流程差异。
- `04 - AX SYS API 文档.docx`，`AX_SYS_Link_V2` 和 `AX_MOD_LINK_ATTR_T` 接口说明。
- `msp/component/sys/ax_sys_api.c`：`AX_SYS_Link_V2` 用户态参数检查。
- `header/external/ax_sys_api.h`：公开类型和错误码。
- `kernel/osdrv/private_drv/sys/syslink/src/ax_sys_link.c`：VPP/VGP 到 VENC/JENC 的内核 Link 展开方式。
- `camera-kit/service/mid/axck_ivps/ivps.c`：`IVPS_SetChnAttr`、`IVPS_SetGrpAttr`、`IVPS_FPSControl` 的运行期属性下发路径。
- `kernel/osdrv/private_drv/vcodec/venc/debug/proc/ax_venc_proc.c`：`/proc/ax_proc/venc` 的 HSK STATUS 表头与字段来源。

文档与当前代码不一致时，明确记录 SDK revision，并以对应运行包的代码或符号为准。
