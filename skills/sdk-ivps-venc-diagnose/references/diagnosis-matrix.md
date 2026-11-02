# 故障矩阵

## 正常与卡死的区别

“正常”不是所有数字相等，而是同一条数据路径的阶段性计数持续向前。有两次 `cat` 时，将其视为 `S1`、`S2` 并结合 `S2-S1`；只有一次或部分信息时，也要先依据当前字段分析，并标明持续性尚未确认。HSK 同步位置还必须结合 `initVal` 和 `syncVal` 判断：三类同步值都是 16 位数，握手高度为 `(syncVal-initVal)&0xFFFF`，当前进度为 `(RegVal-initVal)&0xFFFF`。非 HSK 绑定（`SW_Offline` 等）没有同步寄存器，只按业务计数差值定位卡死段，下表「链路模式」列标 `HSK` 的行不适用于它们：

| 链路模式 | 观察 | 优先模块 | 初步原因 | 不能误判为 |
|---|---|---|---|---|
| HSK·Offline | IVPS `InCnt` 增长，指定 filter `OutCnt` 不变，`Fail1/Fail2` 增长 | IVPS | VPP/VGP 处理失败或输出队列阻塞 | VENC 硬件卡死 |
| HSK·Offline | IVPS filter 输出增长，目标编码 `FrmRecv` 不变 | link/syncagent 或编码输入侧 | link 映射错误、HSK wait 未满足、消费者未接收 | IVPS 卡死 |
| HSK | 已映射到同一帧/连接的 VPP `update` 已到目标区间，VENC `update/wait` 仍在 `initVal` 或更早位置，连续两次保持 | H26x 消费侧、VENC 输入接收或 HSK wait | 上游已完成本轮握手，H26x 未消费本轮同步数据 | 仅凭单次帧内差异判定硬件卡死 |
| HSK | 两侧都处于 `initVal` 与 `syncVal` 之间，连续两次不变 | 对应生产/消费链路 | 当前帧握手推进停滞，需结合业务计数定位 | 单次处于中间值 |
| HSK | `(RegVal-initVal)&0xFFFF` 大于握手高度 | 对应同步连接 | 寄存器不在本轮有效握手区间，可能是越界、旧值或同步状态异常 | 不核对区间就解释为正常溢出 |
| HSK | HSK `Session State != 2` | syncagent session | session 未处于正常工作态，后续 wait/update 不具备正常握手语义 | 直接判 VPP/VENC/JENC 卡死 |
| HSK | `SW_Low_Mem Line=128`，VPP 尚未写满前 128 行，前两次 `wait=initVal` | VPP/VENC 链路 | ring 初始窗口允许 VPP 先写入，暂不需要 VENC 消费 | VPP wait 未变化 |
| HSK | VPP 已写满前 128 行，但 `update` 未到 `initVal+128` | IVPS/VPP | VPP 生产节奏或 VPP HSK update 异常 | VENC 消费侧卡死 |
| HSK | 未进入帧尾 128 行时，`(vpp_update-vpp_wait)&0xFFFF < 128` | IVPS/VPP | VPP 未维持 ring 安全距离，可能无法继续完成当前任务 | VENC 消费侧异常 |
| HSK | VPP 已正常完成任务、尚未进入帧尾 128 行，且同一帧 `update-wait` 环形距离小于 128 | IVPS/VPP | VPP 未维持 ring 安全距离，生产侧或 HSK update 异常 | VENC 消费侧异常 |
| HSK | VPP 保持至少 128 行安全距离并按 64 行推进，但 VENC wait/update 未按 `minhskLin` 节奏推进 | VENC/HSK wait | 编码消费侧未及时消费同步数据 | VPP 本体卡死 |
| HSK·Offline | VENC `Send2EncCnt`/`SubMitCnt` 增长，`EncSucCnt` 不变 | VENC | 编码硬件未完成、固件异常或 HSK 等待 | 用户态取流问题 |
| HSK·Offline | VENC `EncSucCnt` 增长，stream `WriteCycle` 增长而 `ReadCycle` 不变 | 用户态取流/码流缓冲 | 未调用或未及时调用 get/release stream，最终反压 | 编码硬件卡死 |
| HSK·Offline | JENC `SubmitCnt` 增长，`SucCnt` 不变，`HwState` 非 IDLE 或 `TimeOutCnt` 增长 | JENC | JPEG 硬件/固件超时或 HSK wait | 仅因输出帧率低 |
| HSK·Offline | JENC `FrmRecv` 增长、`DiscardedNum`/`RatDrpCnt` 增长、`SucCnt` 仍增长 | JENC 配置/帧率控制 | 1 fps/定时输出等预期丢帧 | 卡死 |
| HSK | `HoldCnt` 与 `ReleaseCnt` 差值持续扩大 | syncagent 及对应 wait 对端 | hold 未释放，常由下游不消费或同步事件不匹配引起 | 单纯 VENC 错误 |
| HSK·Offline | 所有有效模块业务计数冻结 | 上游输入或公共同步/内存 | VIN 不供帧、公共调度/内存阻塞 | 任意单一编码模块 |
| HSK | 一对二中 VENC 分支增长，JENC 分支冻结 | JENC 分支、VPP->JENC wait/link | 双消费者同步关系或 JENC 输入/硬件异常 | 整个 IVPS 组 |
| HSK | 二对一中一个上游事件增长，另一个上游事件冻结 | 冻结的上游分支或 syncagent wait | 两个输入关系未同时满足，先核对 `opWaChn/opUpChn` 是否存在禁用 ack | 下游编码器本身 |
| Offline | IVPS `InCnt` 增长、末尾 filter `OutCnt` 冻结（`Fail1/Fail2` 有值） | IVPS | VPP/VGP 处理失败或该级输出阻塞 | 编码器卡死 |
| Offline | IVPS 末尾 filter `InCnt`/`OutCnt` 与编码 `FrmRecv` 两轮都不变（`OutFps=0`） | 上游输入 | VIN 未供帧或上级 filter 未出图 | 该链路卡死，应先看上游 |
| Offline | IVPS `OutCnt` 增长、目的 `FrmRecv` 不变、`chn_info.OutSts` 逼近 `OutDepth` | link 派发 | 同步回调派发被拒，查 syslog 的 `Chn %d busy!`/`Chn %d full!`（`venc.c` 的 `VencCalLinkNotify_SendLinkFrameWithHandling`） | IVPS 或编码器硬件卡死 |
| Offline | `FrmRecv` 增长、`SubMitCnt` 不变，`Send2EncFail`/`BufFullCnt`/`TimeOutCnt` 增长（JENC 看 `BusyCnt`、`frame_list.busyCnt`、`HwState`） | 编码器 | 编码输入接收后未送编码，硬件/固件异常或缓冲满 | 用户态取流问题 |
| Offline | `SubMitCnt` 增长、`stream_buf.ReadCycle` 不变、`AvalRSize` 增长或 `HwUsed=Y` | 用户态取流/码流缓冲 | 未及时 get/release stream，最终反压编码 | 编码硬件卡死 |

Offline 链路还有两条固定边界：`bHsk=N` 与 HSK STATUS 段缺失是正常现象，不是数据缺失；`WaitEncFail` 在 offline 路径不会增长（`venc.c` 的 `VencCalLinkNotify_ProcessLinkFrameData` 不置 `VENC_ENRICH_WAIT_ENC_DONE`），一旦增长即按异常升级处理。

## 形态核对样本

- 一对一：`IVPS 0 0 -> VENC 0 0`、`IVPS 0 2 -> VENC 0 1` 这样的每源单消费者连接；单个编码通道的 HSK `srcNum=1`。
- 一对二：同一源例如 `IVPS 0 0` 同时到 VENC ch0 和 JENC ch1；`syncagent` 同一会话出现 VENC/JENC 两个下游关系。
- 二对一：同一个下游例如 JENC 同时等待 `MM_VPP` 和 `MM_VGP`；`syncagent` 会表现为一个编码消费者配两个 wait 上游。

样本中的 `hskCnt`、`SeqNum`、`TotalCnt` 都是运行计数，数值大小受采样时刻影响，不应作为形态的固定阈值。形态看连接关系，卡死看跨采样差值。

`SW_Offline`/`HW_Online`/`Mode_Unset` 绑定的链路没有 HSK 会话，不参与形态核对，只看「正常与卡死的区别」表里标 `Offline` 的行。

## 补采样命令

若现场只给了一次输出，可以先依据当前状态和计数关系给出初步判断；如需确认是否持续卡死，再执行：

```sh
echo 'priv on' > /proc/ax_proc/syncagent
for n in 1 2 3; do
    date
    cat /proc/ax_proc/link_table
    cat /proc/ax_proc/link_table_kernel
    cat /proc/ax_proc/syncagent
    cat /proc/ax_proc/venc
    cat /proc/ax_proc/jenc
    cat /proc/ax_proc/ivps
    sleep 5
done
```

第二轮用于确认计数是否持续不变，第三轮用于排除偶发采样。若不能执行循环，只补充当前疑点涉及的模块和字段即可，例如判断 JENC 时优先补 `jenc` 两次状态及其对应 `syncagent` wait 信息，不要求无关模块重复提供。不要只依据一次静态计数直接下“持续卡死”结论。
