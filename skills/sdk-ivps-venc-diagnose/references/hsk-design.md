# HSK 设计约束

本页将 HSK 诊断所需的工作模式、拓扑关系、状态变化和异常恢复规则固化为现场判断步骤。无需查阅其他资料，只需结合 `link_table`、`syncagent`、`venc`、`jenc`、`ivps` 的现场输出进行判断。

## 工作模式

先看 `link_table` 的 `Mode`，再看 `Line`、`Src/Dst Engine` 和编码器 HSK 状态。模式不是三种 HSK 形态的同义词：形态描述连接关系，模式描述数据搬运和同步方式。

| link mode | 含义 | 重点核对 |
|---|---|---|
| `SW_LOW_MEM` | DDR 中按 ring buffer/行数进行软件低内存握手；常见 VPP->VENC/JENC HSK | `Line` 是 VPP/VENC ring 高度；`Line=128` 时按 VPP 64 行输出节奏判断初始窗口和后续 wait/update |
| `SW_LOW_LATENCY` | DDR 中按编码高度/低延迟节奏握手 | 不要把 `Line=0` 自动判成无 HSK；需看 `bHsk`、`srcNum`、`hskCnt` 和 syncagent |
| `HW_ONLINE` | 前后级硬件在线传输，通常不走软件 ring HSK | 若 `bHsk=Y` 与模式矛盾，优先报告 link 配置或 proc 快照不一致 |
| `SW_OFFLINE` | 帧级离线传输，不应按 HSK ring 卡死分析 | 只分析普通输入、输出和编码计数，不用 `HoldCnt` 单独归因 |

## 三种管线的设计期望

- 一对一：`VPP -> VENC` 或 `VPP -> JENC`，一个生产者只对应一个消费者。
- 一对二：`VPP -> VENC + JENC`，同一帧由两个消费者共同推进；任一消费者不消费都可能反压生产者。
- 二对一：`VPP + VGP -> JENC`，JENC 的输入关系为两个上游，但实际 ack 方向由同步代理配置决定；代码对 VPP+VGP->JENC 会关闭 VGP 的反向 ack，因此不能要求两个上游 wait/update 以完全对称的寄存器序列推进。

对一对二和二对一，不要把“一个分支计数停住”扩大成整个 IVPS 组卡死。先通过 `conId/waitId/upId` 回查具体 wait 分支，再比较该分支的 `FrmRecv/SubmitCnt/SucCnt`。同一个 IVPS/VPP 输出连接两个编码消费者时，以 `link_table` 判为一对二，不因缺少某个消费者的 proc 而改判。

一对一或一对二链路还要以同一帧、同一连接的 `initVal/syncVal` 基准比较两侧 `update` 位置。映射 `syncagent` 行到编码通道时用 `ConId`、`waitId/upId` 和物理寄存器地址共同确认：`waWaPhy0/waUpPhy0` 应与该连接的 `SyncAddr` 指向同一物理寄存器，对不上说明映射错了，不要继续比较数值；数值不同量纲或无法映射时报告「同步字段无法交叉映射」。三类同步值均按 16 位无符号数处理：握手高度为 `(syncVal-initVal)&0xFFFF`，当前进度为 `(RegVal-initVal)&0xFFFF`。`SW_Low_Mem Line=128` 时，VPP ring 高度为 128 行，VPP 固定每次输出 64 行：前两次 VPP wait 可保持 `initVal`，但 VPP 写满前 128 行后，update 必须至少到 `initVal+128`；后续 wait/update 按 64 行输出步长推进。前 128 行是无需等待编码消费的初始窗口，`wait` 不变不代表 VPP 卡死；但写满该窗口后 update 未到 `initVal+128`，属于 VPP 生产侧/HSK update 异常。若 VPP 已正常完成任务且尚未进入帧尾 128 行，`(vpp_update-vpp_wait)&0xFFFF` 必须至少为 128；帧尾窗口内允许距离收缩，需结合 `syncVal` 和帧完成计数。H26x/JENC 编码侧的 wait/update 第一值以 `initVal` 为起点，后续按对应 `minhskLin` 递增，最后的编码 update 可能按 64 行对齐到 `syncVal`；二对一的 JENC 里 VPP/VGP 两个来源不产生对称 ack，按 `DoubleWait`、`opWaChn/opUpChn` 和 `waitId/upId` 的实际值判断，不能要求两个 wait 行的寄存器同步增长。只有 VPP 保持安全距离而消费侧连续两次未按对应步长推进，才优先判消费侧异常；若 VPP 自身 `InCnt/OutCnt` 也不推进，才优先判 VPP。`Line`、`minhskLin`、编码高度与 `syncVal-initVal` 不一致时，先报告 HSK 参数或版本配置不一致，不要直接判硬件异常。

## HSK 启动和运行检查

编码器启动或重新绑定时，正常顺序是：建立 link/同步关系，配置编码器 HSK 参数，启动接收，再由上游持续产生同步码。现场诊断只需验证结果：

1. 目标 HSK 的 `syncagent SESSION State=2`；否则先判 session 未正常工作。
2. `link_table` 有目标连接，且 `Mode/Line/Engine` 与预期一致；判断 JPEG 分支优先看 `Engine(...->JENC)`，不要只看目的 `ModId`。
3. 编码器 HSK `bHsk=Y`，`srcNum`、`conId/waitId/upId` 能在 `syncagent` 找到对应关系。
4. 以 HSK `initVal` 为本轮起点、`syncVal` 为本轮完成位置；正常完成一帧时，相关有效 update/wait 应按各自节奏推进到目标区间，不要求多 wait 分支的寄存器在帧内始终相等。所有值按 16 位处理，`(syncVal-initVal)&0xFFFF` 是本轮握手高度，应与编码高度按 64 行对齐后的关系核对。
5. 对 `SW_Low_Mem Line=128`，核对前 128 行初始窗口、`update` 是否到 `initVal+128`、后续 VPP 64 行步长、帧尾 128 行例外以及编码侧 `minhskLin` 步长；前提是先确认当前采样对应的帧阶段。
6. `hskCnt`、输入帧计数和编码完成计数在两次采样间向前推进。
7. `syncagent` 的 `HoldCnt` 与 `ReleaseCnt` 长期差值不扩大。

若第 1 步成立但第 2 步不成立，优先判 HSK 配置/启动顺序；若第 2 步成立但第 3 步不成立，按 [SKILL.md](../SKILL.md) 的数据流决策树继续定位。

## Abort、Drop 和 Overflow

HSK 设计中的异常恢复不是简单停止线程，而是要让当前编码任务退出并消费掉对应同步码，避免下一个任务永久等待旧 sync code。诊断时不执行恢复动作，只识别恢复是否完成。

### 编码器主动 Abort

典型触发：码流 buffer full、编码器停止、用户态 `stopChn`，或前级在编码器尚未完成当前帧时发起 abort。

期望状态序列：

```text
停止/Abort 请求
  -> abort 中断
  -> 关闭 HSK
  -> hskDropTrigger 消费当前 sync code
  -> 清理当前 frame/stream/硬件节点
  -> 编码器回到 idle，可重新 start
```

proc 判定：

- Abort 发生后，允许本轮 `hskCnt` 和业务计数停止；必须结合下一轮看 `bHsk`、`HwState`、busy/toHw 等状态是否清理。
- `bHsk` 仍为 `Y`、`HwState` 长期为 busy，且 `hskCnt`/`SucCnt` 两轮不变：优先判 VENC/JENC abort 或 HSK drop 未完成。
- `bHsk` 已为 `N`、编码器回 idle、下游计数停止：更像正常停流结果，不能报告“卡死”。
- `HoldCnt` 持续增长而 `ReleaseCnt` 不跟随：sync code/hold 没有被消费，优先报告 syncagent 与对应编码器清理路径。

### 前级 Abort 和输入 Overflow

在 `VIN -> VPP -> VENC` 路径，前级 overflow 可能通过自定义中断通知编码器，由编码器执行 abort 处理。此类问题不要只看 VENC：

- IVPS/VIN 输入计数停止或 FIFO/overflow 先出现，VENC 随后停止：初步模块是 VIN/IVPS 前级，VENC 是被动响应方。
- VENC 收到 overflow/abort 后 `bHsk` 未关闭或硬件不回 idle：初步模块是 VENC abort/HSK 清理。
- 只有 VENC/JENC 分支停住，IVPS 输入和其他分支继续增长：优先检查该编码器的 wait、buffer full、abort 和 sync code 消费。

### Buffer Full

VENC/JENC 码流环形 buffer 满时，重点看两轮的：

- `WriteCycle` 是否继续增长；
- `ReadCycle` 是否停止；
- `AvalRSize` 是否接近 `BuffSize`；
- `BufFullCnt/BufOver/NoFree` 是否增长；
- Abort 后 `HwState`、`BusyCnt`、`bHsk` 是否回到可重新启动状态。

`WriteCycle` 增长而 `ReadCycle` 不增长，首先是用户态没有及时 get/release stream；只有在 buffer 未满、消费正常而 `SubmitCnt/EncSucCnt` 仍停止时，才升级为编码器/HSK 故障。

## 现场输出时序

如果卡死发生前后，建议按事件采样，而不是只保留卡死时刻：

1. 正常运行：完整采样 `syncagent/venc/jenc/ivps` 一轮。
2. 发现停滞：间隔 3--10 秒再采样完整一轮。
3. 执行或观察到 stop/abort/overflow：立即采样一轮，再间隔 3--10 秒采样一轮。

输出必须标记采样属于“运行中、异常中、Abort后”哪一阶段。Abort 后的静态 `bHsk=N` 和计数不增长不能与运行中的卡死混为一谈。
