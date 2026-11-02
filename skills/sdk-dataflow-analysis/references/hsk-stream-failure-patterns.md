# HSK 断流 / 不出流：现象 → 机制候选

建链已成功、运行期无码流或断流时，先按本表选机制类，再按类去核对 [ax-sys-link-v2.md](ax-sys-link-v2.md) 或 [venc-hsk-proc.md](venc-hsk-proc.md)。同一失败点只保留一个主根因。

已有机制只留一行交叉索引，不在此复述完整根因：

- LowMem `nRingLineCnt` 非法 → 见 ax-sys-link-v2「非法 nRingLineCnt」
- Offline engine 非零 → 见 ax-sys-link-v2「Offline engine 非零」
- 同一硬件两路 JENC HSK 同时工作 → 见 ax-sys-link-v2「二对二同时占用两路 JENC HSK」
- HSK 下改分辨率未协同 VENC → 见 ax-sys-link-v2「参数切换时序违规」

## M1 部分通道 HSK enable/disable（merged trigger 漏扫）

- **触发条件**：同一 IVPS group 内，部分 channel 关 HSK、部分 channel 开 HSK；对照两路同开或同关正常。
- **可见签名**：`ivps.proc` 中 Grp `InFps>0` 且 `OutFps=0`、CHN `OutFps` 全 0、FILTER `OutCnt` 全 0；串口/配置侧可见主流关 HSK、JPEG 路仍开 HSK。缺 `link_table` / 各通道 HSK enable 配置时不能区分机制。
- **判读**：参数层面 `AX_SYS_Link_V2` 可建链成功，失败点在 IVPS scheduler 对 merged filter 的 HSK trigger 扫描；当前 task ctx 自身不是 `hsk_src` 时，旧逻辑会跳过仍为 `hsk_src` 的 sibling filter。
- **INCONCLUSIVE**：只有残缺 `ivps.proc`、无 serial/syslog/link/venc、或无法确认「部分通道关 / 部分通道开」与对照结果时，输出 `INCONCLUSIVE` 并补采，不得仅凭 `OutFps=0` 断定为该内核路径。
- **背景修复**：osdrv 已有针对 merged filter HSK trigger 扫描的修复先例；仅作机制背景，分析阶段不得当作已确认根因。
- **交叉引用**：ax-sys-link-v2「部分通道 HSK / merged trigger」。

## M2 VENC abort 三中断竞争

- **触发条件**：HSK 编码过程中硬件 abort；任务已完成时同时上报 END/SUCC/ABORT，idle 态再执行 abort → 编码 hang。
- **可见签名**：VENC 通道 hang；syslog/内核侧可见 abort 相关中断或等价记录；常伴随 VB 分配频繁失败（abort 频率升高后的传播）。
- **判读**：见 [venc-hsk-proc.md](venc-hsk-proc.md)「abort 三中断竞争」。
- **INCONCLUSIVE / forbidden_default**：缺 END/SUCC/ABORT 同时上报或等价内核证据时，不得下确定结论；不得把单独的 `hskCnt` 停滞或 `Get block fail` 当成 abort 根因；不得默认归因到 Link 参数非法或双 JENC。
## M3 HSK 运行期旋转

- **触发条件**：VIN→IVPS 已建 HSK（含 mode=1 / LowMem 双向 HSK）后，运行期开 90/270 旋转。
- **可见签名**：旋转 API / ioctl 失败或驱动拒绝；随后断流。mode=1 双向 HSK（src NONE dst GDC、`line_cnt>0`）下 SetRotation 会被驱动报错，断流符合预期。
- **判读**：与 LowMem VIN→IVPS 运行期旋转同一机制族；应用侧应保持 `rotation_enable: false`，或改用不支持约束的路径。详见 ax-sys-link-v2 旋转约束节。
- **INCONCLUSIVE**：看不到旋转动作、link mode 或驱动返回时，不要猜成别的 HSK 断流类。
## M4 sync agent dispatch / ITP update 丢失

- **触发条件**：长压测或 GDC/VPP stop 场景下，sync agent 行同步中 ITP→VPP update 丢失或超时，dispatch 阻塞。
- **可见签名**：`ax_link` dispatch 卡住；VPP 等不到 ITP update；`syncagent` / `syncagent_trace` 显示 update 丢失。
- **判读**：见 [venc-hsk-proc.md](venc-hsk-proc.md)「ITP update 丢失 / dispatch 卡住」。
- **INCONCLUSIVE / forbidden_default**：缺 syncagent/ITP update 直接证据时必须 `INCONCLUSIVE`；不得默认归因到 Link 参数非法或双 JENC。
## M5 HSK 下 VGP 首 slice 被 skip（OSD + JENC）

- **触发条件**：VPP_VGP→JENC HSK 下移动 OSD（如移到右下角）后 IVPS 卡死、占 VB、无码流。
- **可见签名**：`[ivps_osd_cfg_info_get_v2:...] RGN... nX[...] >= ... || nY[...] >= ...`；随后 IVPS/VB 卡住。机制是 HSK 下 VGP 首 slice 被 skip，不是部分通道 enable，也不是双 JENC。
- **判读**：优先按 OSD 几何越界 + HSK VGP slice 路径排查；分析仍以本现场日志为准。
- **INCONCLUSIVE**：只有无码流、无 OSD 越界签名、也无 VGP/JENC HSK 拓扑时，不要归到本类。
- **机制背景**：osdrv 修复方向为「HSK 模式下 VGP 首 slice 不应被 skip」；仅作机制背景，不构成本现场根因结论。

## M6 HDR / 分辨率 / 双摄 HSK 切换

- **触发条件**：HSK 下自动切分辨率/编码格式、切 HDR/SDR、双摄同时切换。
- **可见签名**：切换动作后断流或两路不出流；先核切换序列是否漏步（停模块、UnLink/Link、IVPS/VENC 协同）。
- **判读**：有漏步证据 → 归到已有「切分辨率未协同 VENC」时序类，不要当新根因。无漏步、仍指向 SDK 内部 HSK 重建缺陷时，才能作为独立候选，且需完整 serial/link/venc。
- **INCONCLUSIVE**：缺切换前后时间线或 link/venc 几何对照时保持 `INCONCLUSIVE`。
## 余下签名（不单独成类主根因）

| 现象 | 判读要点 |
| --- | --- |
| LOW_LATENCY get 不到帧 | HSK LowLatency VPP→VENC 发帧后 get 失败；先核链路是否真在 LowLatency 且对端在收 |
| StartGrp 失败（VPP→VGP→VENC） | 初始化/启组失败，先看返回码与依赖模块是否已起 |
| 先非 HSK 再切 HSK，start recv frame fail | 怀疑非 HSK→HSK 残留状态；见 ax-sys-link-v2 交叉引用 |
| 只 stop venc0，其他 IVPS chn 帧率异常 | 单路 stop 破坏 HSK/sync 配对；与 M5 邻近，不是双 JENC |
| 5M FBC 下 VIN-IVPS HSK 异常 | 先核 FBC/压缩与 HSK 组合是否在支持范围 |
| 出 1 帧后 VPP timeout | 小内存/超时类；timeout 单独不足以下双 JENC 或参数非法 |
| COMMON_CAM_Init 顺序导致 HSK 挂死 | 模块初始化顺序约束 |
| AOV + HSK 断流 | AOV 与 HSK 交互；缺 AOV 切换证据时不要硬套 M1–M6 |
| vin-ivps 开 HSK 后无码流 | 仅作 VIN-IVPS HSK 无流候选；**不要默认并进 M1**，除非有「部分通道关/开 HSK」证据 |
