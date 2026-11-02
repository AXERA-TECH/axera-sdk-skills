# VENC HSK STATUS proc 判读

`/proc/ax_proc/venc` 是判断 HSK 握手实际停在哪一步的主要证据源。AX615 在该节点下增加了 H26X 的 STREAM BUF STATUS 与 HSK STATUS 两组表。

```sh
cat /proc/ax_proc/venc
```

## 表头以代码为准

《53 - AX SDK典型场景使用说明》5.3 节的截图表头与当前 trunk 代码**不一致**，写 Case 证据签名或匹配日志时一律以代码为准：

| 代码实际表头 | 文档截图表头 |
| --- | --- |
| `bHsk` | `enType` |
| `srcNum` | `dstNum` |
| `fMode` | `flowMode` |
| `syncVal`、`bFrmDrop` | 无 |
| 无 | `modId0`、`modId1` |
| `errDropCnt` | `hskErrDropCnt` |

遇到与本表都不符的表头时，以目标运行包的 `ax_venc_proc.c` 为准并记录 SDK revision，不要照抄文档截图。

## HSK STATUS 字段语义

第一组（`ax_venc_proc.c:207`，结构体字段见 `VENC_SYNC_AGENT_CTX_T`）：

| 字段 | 来源 | 含义 |
| --- | --- | --- |
| `VeChn` | — | 编码通道号 |
| `bHsk` | `bSyncAgentChnInit` | 该通道 sync agent 是否已初始化，`Y` 表示处于 HSK |
| `maxH` | `u32MaxPicHeight` | 最大图像高度 |
| `EncH` | `u32EncPicHeight` | 当前编码高度 |
| `EncHPre` | `u32PreEncPicHeight` | 上一次编码高度 |
| `srcNum` | `link->src_num` | 该 link 的源数量 |
| `fMode` | `link->astDestModAttr.eDataFlowMode` | 数据流模式 |
| `ringLCnt` | `link->astDestModAttr.nRingLineCnt` | Ring Buffer 行数 |
| `sliceNum` | `sliceNum` | slice 数 |
| `minhskLin` | `minHslLine` | 最小握手行数 |
| `saSize` | `syncCodeSize` | sync code 大小 |
| `conId` | `consumerId` | consumer id |
| `waitId` | `s32WaitHskChnId` | 等待握手的通道 id |
| `upId` | `s32UpdateHskChnId` | 更新握手的通道 id |
| `initVal` | `initVal` | 同步寄存器初始值 |
| `syncVal` | `syncRegValue` | 同步寄存器当前值 |
| `bFrmDrop` | `bFrmDrop` | 当前是否处于丢帧状态 |
| `hskCnt` | `hskCnt` | 累计握手次数 |
| `errDropCnt` | `hskErrDropCnt` | 握手异常导致的丢帧次数 |

第二组（`ax_venc_proc.c:218`）记录握手配对关系，排查时序与 session 错配时使用：

| 字段 | 来源 | 含义 |
| --- | --- | --- |
| `cntWa` | `bSessionConWait` | session 连续等待标志 |
| `douWa` | `bDoubleWait` | 双等待标志 |
| `waChn0`/`waChn1` | `syncAgentInitParam.wait_chn[]` | 本端等待通道 |
| `opWaChn0`/`opWaChn1` | `opposite_wait_chn[]` | 对端等待通道 |
| `opUpChn0`/`opUpChn1` | `opposite_update_chn[]` | 对端更新通道 |
| `waWaPhy0` | `u64SyncCodeWaitPhyAddr` | sync code 等待物理地址 |
| `waUpPhy0` | `u64SyncCodeUpdatePhyAddr` | sync code 更新物理地址 |
| `waReInfo0`/`waReInfo1` | `u8WaitSyncRegAddr[]:wait_reg[]` | 等待同步寄存器地址与实际值 |
| `upReInfo` | `u8UpdateSyncRegAddr:update_reg` | 更新同步寄存器地址与实际值 |
| `se_id` | `u8SessionId` | session id |

未配对的通道整行为 0，属于正常状态，不要当成异常。

## 判读要点

- `bFrmDrop` 由 `0` 变为 `1` 并保持：VENC 处于持续丢帧。这是 HSK 几何不匹配最直接的指标，配合 `EncH` 判断是哪一侧的几何过期。
- `EncH`/`maxH` 与上游 IVPS 当前输出分辨率不一致：VENC 仍持旧几何。运行期改过 IVPS 分辨率却出现这种不一致时，说明切换没有协同 VENC，见 [ax-sys-link-v2.md](ax-sys-link-v2.md) 的「参数切换时序违规」。
- `bHsk=Y` 但 `hskCnt` 长期不变：握手未推进。需要先区分是上游停止送帧，还是本端等待对端更新，不能直接下结论。
- **`hskCnt` 持续增长不等于数据流正常**。几何不匹配时握手线程照常运行、`hskCnt` 照常累加，但每帧都被丢弃，此时 `errDropCnt` 也可能一直为 `0`。判断是否出流要看 VENC 的帧率与 `recv` 计数，不能只看 `hskCnt`。
- `errDropCnt` 增长：握手异常丢帧。内核同时打印 `Chn:<n> hskCnt:<a>,hskErrDropCnt:<b>`（`ax_venc_sync_agent.c:735`，`VLOG_WARN`），该行可在 syslog 中作为签名匹配。注意该计数只统计特定的握手异常，不覆盖全部丢帧场景。
- `waitId`/`upId`/`conId`/`se_id`：握手配对关系。实测中运行期分辨率切换**不会**改变这些字段，因此它们保持不变不能作为"时序正常"的证据；只有在通道确实被销毁重建的场景才用它们核对配对是否指向已失效的通道。
- `ringLCnt`、`minhskLin` 与建链参数不符：link 属性与 sync agent 实际生效值不一致，优先怀疑 link 未按新参数重建。

未配对的通道整行为 0，属于正常状态，不要当成异常。

## STREAM BUF STATUS

同一节点还输出 H26X STREAM BUF STATUS（`ChnId`、`BufMod`、`BuffSize`、`ReadPtr`、`WritePtr`、`ReadCycle`、`WriteCycle`、`AvalRSize`、`AvalWSize`、`HwUsed` 等）。该表头来自文档截图，尚未与当前代码逐字段核对，引用前先对照目标运行包的实际输出。

`HwUsed=Y` 表示该通道 buffer 正被硬件占用；`ReadCycle` 与 `WriteCycle` 长期相等且不增长，说明码流侧没有新数据产生，与 HSK STATUS 的 `hskCnt` 停滞互为印证。

## abort 三中断竞争（M2）

HSK 编码 hang、疑似硬件 abort 时：只有 syslog/内核出现 END/SUCC/ABORT 同时上报或等价证据，才能判为 abort 三中断竞争。缺该直接证据 → `INCONCLUSIVE`。不要把单独的 `hskCnt` 停滞或 `VB Get block fail` 当成 abort 根因，也不要默认归因到 Link 参数非法或双 JENC。现象分流见 [hsk-stream-failure-patterns.md](hsk-stream-failure-patterns.md) M2。

## ITP update 丢失 / dispatch 卡住（M4）

VPP 等不到 ITP update、`ax_link` dispatch 卡住时：需要 syncagent / ITP update 丢失的直接证据。缺该证据 → `INCONCLUSIVE`。不要默认归因到 Link 参数非法或双 JENC。见 [hsk-stream-failure-patterns.md](hsk-stream-failure-patterns.md) M4。

## 证据来源

- `kernel/osdrv/private_drv/vcodec/venc/debug/proc/ax_venc_proc.c`：表头与字段映射。
- `kernel/osdrv/private_drv/vcodec/venc/enc_comm/ax_venc_sync_agent.h`：`VENC_SYNC_AGENT_CTX_T` 定义。
- `kernel/osdrv/private_drv/vcodec/venc/enc_comm/ax_venc_sync_agent.c`：`hskErrDropCnt` 的累加点与告警日志。
- `53 - AX SDK典型场景使用说明.docx` 5.3 节：proc 截图，表头与当前代码存在差异。

