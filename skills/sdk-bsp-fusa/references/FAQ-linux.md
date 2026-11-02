# M57H Linux FuSa FAQ

> 面向客户、AE、FAE、AI 检索与现场排障。

## 标签分类&高频速查表

### 性质标签

| 标签                   | 含义                                                 | 对客户怎么说                                               |
| ---------------------- | ---------------------------------------------------- | ---------------------------------------------------------- |
| **【设计预期】**       | Linux FuSa 框架、协议、调度或安全策略的正常行为      | 「这是当前 Linux FuSa 的工作机制，并非故障」               |
| **【配置·使用·方法】** | 需要核对配置、启动顺序、构建生成、测试方法或适用条件 | 「先按本文核对实际配置和运行状态，再判断是否存在软件故障」 |
| **【已修故障】**       | 旧软件实现存在缺陷，较新版本已经修正                 | 「先按本文的代码特征或运行特征确认版本是否包含修复」       |

---------

### 高频 Top 问题速查

| 常见问题                                           | 一句话答案                                                   | 性质标签           | 详见                 |
| -------------------------------------------------- | ------------------------------------------------------------ | ------------------ | -------------------- |
| `heartbeat time:N`、`heartbeat timeout.`           | `time:N` 是连续等待超时计数；出现 `heartbeat timeout.` 才正式上报心跳故障 | 【设计预期】       | FAQ-7                |
| 节点存在但周期 STL 不运行                          | 同时检查 domain/module 两级 `cycle_enable`、周期回调和 `ax_diag_service` | 【配置·使用·方法】 | FAQ-2、FAQ-8         |
| `error_mask=0x...`                                 | 按 domain/module/event 解码，不能根据相邻日志猜模块          | 【设计预期】       | FAQ-3                |
| 改 Excel/JSON 不生效                               | 对照源 Excel、生成结果、板端 JSON 和最终 sysfs 值            | 【配置·使用·方法】 | FAQ-5、FAQ-6、FAQ-26 |
| `cyclework overdue`、ACK timeout、CPU loading 增长 | 找时间线上最早的原始故障，后续调度和心跳异常通常是连锁结果   | 【配置·使用·方法】 | FAQ-9～FAQ-11        |
| `E2E P04 Check ... failed`                         | 分别检查并发序列、两端初始化状态和故障注入                   | 【配置·使用·方法】 | FAQ-12               |
| `FCU_HANDLER_TIMEOUT`                              | 表示处理过程超时，不等同于 FCU 寄存器损坏                    | 【配置·使用·方法】 | FAQ-13               |
| NPU 上下电出现 ECM                                 | 硬件状态切换期间必须暂停 monitor，资源恢复完成后再开启       | 【已修故障】       | FAQ-14               |
| NPU Verify 失败但无诊断码                          | 确认代码调用 `AX_DIAG_ReportEvent()`，并确认诊断服务已启动   | 【配置·使用·方法】 | FAQ-15               |
| DDR inline ECC、高低温刷屏                         | 分开核对物料温度范围、refresh、ECC 地址和非法 DMA/内存写入   | 【配置·使用·方法】 | FAQ-16～FAQ-18       |
| eMMC cycle mismatch 后出现 heartbeat               | 可能是正常 I/O 与 STL 保存值并发；heartbeat 可能是后续负载效应 | 【配置·使用·方法】 | FAQ-19               |
| lockstep 下 CPU/GIC STL 不执行                     | lockstep 模式会跳过不适用的周期测试，Basic STL 仍保留        | 【设计预期】       | FAQ-20               |
| `main_ext_X` 日志很多                              | mask 只停止该来源的报告，不会清除底层信号                    | 【配置·使用·方法】 | FAQ-22               |
| `diagnose.dbc` 缺失、FuSa 编译失败                 | 先查 `PLAT`、生成链、rootfs 空间、Python 环境和工具链 ABI    | 【配置·使用·方法】 | FAQ-24～FAQ-25       |

---------

## 第一类 · 框架、标识与配置

### FAQ-1：Linux FuSa 数据到底怎么走？为什么没有独立 diag DTS 节点也有 sysfs？

**其他问法**：`/sys/class/fusa`｜`axdiag`｜kernel 报错但应用或 SafetyIsland 没收到｜Netlink 与 RPMsg

**一句话结论**：**【设计预期】** Linux diagcore 由代码动态创建 `axdiag` platform device；同一个故障再按 `handle_config` 分别上报用户态、转发 SafetyIsland 或触发复位。

**① 现象/场景**

- `/sys/class/fusa/{ecm,fcu,diag}` 已存在，但 DTS 中找不到单独的 diag compatible。
- kernel 已检测并打印故障，应用或 SafetyIsland 却没有收到事件。

**② 简答**

diagcore 的 platform device 和 class 链接由驱动初始化代码创建，不要求 DTS 提供独立节点。kernel 检测到故障只是数据入口；能否到达用户态或 SafetyIsland，还由事件的反应位和各自通信链路决定。

**③ 机制解析**

```text
driver / STL
    └─ diagnosis_error_send()
         ├─ debounce：判断是否达到 happen/resume 上报条件
         └─ error node 入队，由诊断线程处理
              ├─ report 位有效  ─ Netlink ─ AxDiagCore ─ 客户应用
              ├─ forward 位有效 ─ RPMsg + E2E P04 ─ SafetyIsland
              └─ reset 位有效   ─ panic/reset
```

`fusa_sys.c` 的 `register_axdiag()` 动态注册名为 `axdiag` 的 platform device；`fusa_init()` 创建 `fusa` class，并把 diag device 链接到 class 下，所以 sysfs 可以在没有独立 diag DTS 节点时出现。`diag_core.c` 的 `diag_check_handle_config()` 先验证反应位，再由 `DIAG_REPORT_APP_FLAG`、`DIAG_FORWARD_FLAG`、`DIAG_RESET_FLAG` 分别执行三类动作。三条动作链相互独立：例如 report 成功并不能证明 RPMsg 转发也成功。

**④ 怎么判断 / 怎么处理**

- 用户态未收到：先不启动`ax_diag_service`、检查：`diag-netlink: err ID: N module ID: N domain ID: N `, diagcore→netlink。有这条说明内核侧没问题，是用户态没收。 
- SafetyIsland 未收到：检查 forward 位、RPMsg endpoint、handshake 和 E2E 日志。
- 两边都未收到：先检查事件是否达到 debounce 条件，以及 `handle_config` 是否已写入正确节点。



**⑤ 要不要升级**

不需要。动态创建设备及三条反应链是设计行为；只有节点缺失、动作位正确但对应链路仍不工作时，才需要结合后续 FAQ 判断版本问题。

---------

### FAQ-2：如何确认 FuSa 不是“只有节点，功能没启动”？

**其他问法**：diag 节点存在但没上报｜服务是否必须启动｜`cycle_enable=0`

**一句话结论**：**【配置·使用·方法】** 节点存在只说明 kernel diagcore 已注册；周期检测默认关闭，AxDiagCore 完成配置后才开启 domain0。

**① 现象/场景**

- `/sys/devices/platform/axdiag` 存在，但周期自检没有运行。
- 修改 pattern output 或执行周期注入后没有诊断事件。
- 手工写 `cycle_enable=1` 后现象消失。

**② 简答**

确认 `ax_diag_service` 已在业务前启动，并回读 domain 和 module 两级开关。不能把“有 sysfs 节点”等同于“周期任务已经运行”。

**③ 机制解析**

`diag_core.c` 初始化 BSP domain 时将 `cycle_enable` 置为 0，避免配置尚未下发便启动全部周期检测。用户态 `AxDiagCore` 读取 JSON、连接 Netlink、逐项写入策略后，才通过 `AxDiagCore::SetDomainCycleEnable()` 开启 domain。随后 `diag_stl.c` 的 `diag_stl_cycle_check()` 还会同时检查 module 开关和周期回调；任一条件不满足都不会执行该模块的周期 STL。

**④ 怎么判断 / 怎么处理**

```sh
cat /sys/class/fusa/diag/diag/domain0/cycle_enable
cat /sys/class/fusa/diag/diag/domain0/module<MID>/cycle_enable
ps -ef | grep '[a]x_diag_service'
```

若手工开启后恢复，说明检测能力存在而初始化链未闭环。量产系统应调整服务启动顺序或配置下发，不应依赖开机后人工 `echo`。



**⑤ 要不要升级**

通常不需要。先修正服务编排和两级开关；若服务已成功初始化但 domain 仍未开启，再升级到能正确完成配置下发并报告失败原因的版本。

---------

### FAQ-3：`error_mask` 怎么解码？

**其他问法**：`0x80000011`｜`0x08000005`｜domain/module/event 是多少

**一句话结论**：**【设计预期】** `error_mask` 由 domain、module、event 三段组成；必须先解码，再查询本机实际使用的故障表。

**① 现象/场景**

日志只给出 `error_mask=0x........`，或者日志名称与手头的故障表不一致。

**② 简答**

```text
domain = error_mask >> 27
module = (error_mask & 0x07ffffff) >> 16
event  = error_mask & 0xffff
```

| error_mask   | domain | module | event |
| ------------ | -----: | -----: | ----: |
| `0x80000011` |     16 |      0 |    17 |
| `0x08000005` |      1 |      0 |     5 |
| `0x800A0010` |     16 |     10 |    16 |
| `0x002D001D` |      0 |     45 |    29 |

**③ 机制解析**

编码公式与 `diag.h` 中的 mask 组合、拆分宏一致：高 5 bit 表示 domain，中间 11 bit 表示 module，低 16 bit 表示 event。跨端传输结构中的 `mid` 是 `uint8_t`，因此参与跨端通信的 module ID 还必须落入 0～255；不能仅因为 mask 中预留了 11 bit 就使用更大的跨端 ID。

**④ 怎么判断 / 怎么处理**

用解出的三元组匹配板端同一软件包生成的 fault list、JSON 或 DBC；同时核对 `status`、时间戳以及 first/last payload。相邻日志只能帮助还原时间线，不能替代 ID 解码。



**⑤ 要不要升级**

不需要。编码方式属于协议定义；若名称不一致，应先确保故障表和运行镜像来自同一套平台配置。

---------

### FAQ-4：`handle_config` 为什么不是三个普通 bit？

**其他问法**：配置为 1 为什么报 bit flip｜kernel 有事件但应用或 SafetyIsland 没收到｜`handle_config=15`

**一句话结论**：**【设计预期】** report、forward、reset 各使用一对冗余 bit；每对只能是 `00` 或 `11`，`01/10` 会被判为配置损坏并抑制该动作。

**① 现象/场景**

- 写入 1、4、16 等单 bit 值后出现 `handle_config error`。
- 上报、转发、复位只有部分生效。

**② 简答**

|     值 | 动作                     |
| -----: | ------------------------ |
| `0x03` | report 到用户态          |
| `0x0c` | forward 到 SafetyIsland  |
| `0x0f` | report + forward         |
| `0x30` | reset                    |
| `0x3f` | report + forward + reset |

**③ 机制解析**

`diag.h` 使用两份一致位表示每个动作，目的是检测单 bit 翻转。`diag_core.c` 的 `diag_check_handle_config()` 比较每一对 bit：`00` 表示关闭，`11` 表示开启，`01/10` 表示两份配置不一致。只有校验通过，后续代码才读取 `DIAG_REPORT_APP_FLAG`、`DIAG_FORWARD_FLAG` 和 `DIAG_RESET_FLAG` 执行动作。因此把它当普通三 bit 开关写入会直接触发保护逻辑。

**④ 怎么判断 / 怎么处理**

从事件 sysfs 回读完整十六进制值。若日志出现 `handle_config error`，先把目标动作修正为成对 bit；不要把这个配置保护事件归因于源模块硬件损坏。



**⑤ 要不要升级**

不需要。这是安全冗余设计；升级不会把它改成普通 bit。

---------

### FAQ-5：Excel、JSON、kernel 和 Safety 配置是什么关系？

**其他问法**：改 Excel 后头文件没变｜`make fusa_config`｜哪个文件是源配置

**一句话结论**：**【配置·使用·方法】** 平台 `Fault_diagnosis_event_list.xlsx` 是生成源；一次生成会同步产生 SafetyIsland、kernel 和 MSP 使用的配置，不能只改单个生成文件。

**① 现象/场景**

修改了 Excel 或 JSON，但源码枚举、板端节点或上报策略没有变化。

**② 简答**

```text
build/platforms/axera/<PLAT>/Fault_diagnosis_event_list.xlsx
     └─ make PLAT=<PLAT> fusa_config
          ├─ SafetyIsland：Diag_Cfg.c / Diag_CfgOn.h
          ├─ kernel：diag_enum.h / <PLAT>_fusa.config
          └─ MSP：JSON / header / DBC / fault list
```

**③ 机制解析**

`generated_diag_config.py` 读取指定平台 Excel 的固定 sheet，将同一个事件的 domain、module、event、开关、周期和反应策略分别转换为各端格式。编译期的枚举和模块开关来自生成的源码/config，运行期 AxDiagCore 下发的策略来自生成的 JSON。只修改某个输出文件会造成各端 ID 或策略不一致，并会在下一次生成时被覆盖。

**④ 怎么判断 / 怎么处理**

记录 `PLAT`，执行项目既有的 `fusa_config` 入口；检查生成过程无错误，再比对目标文件更新时间和内容。烧录后还要回读 sysfs，确认运行值与生成策略一致。



**⑤ 要不要升级**

通常不需要。生成失败先按 FAQ-24、FAQ-25 排查环境和输入；只有生成脚本本身不支持目标字段时才需要更新 SDK。

---------

### FAQ-6：为什么“配置成功”但 happen 最大间隔没生效？

**其他问法**：JSON 已改但 sysfs 不变｜`resume_happen_max_snd_ms` 不存在｜service 没报错

**一句话结论**：**【配置·使用·方法】** 部分版本把 happen 最大间隔写到了错误的属性名；必须以板端 `happen_max_snd_ms` 回读值判断配置是否真正生效。

**① 现象/场景**

服务正常启动，其他事件参数有效，只有 happen 最大间隔仍保持默认值或旧值。

**② 简答**

不要只看 JSON 和服务初始化返回值。直接读取目标事件目录中的 `happen_max_snd_ms`；JSON 值与 sysfs 值不同即表示下发没有成功。

**③ 机制解析**

kernel 的 `diag_sysfs.c` 通过 `DEVICE_ATTR_RW(happen_max_snd_ms)` 导出属性。部分用户态实现的 `NetlinkMonitor::SendDiagConfigToKernel()` 却拼接为 `resume_happen_max_snd_ms`。该文件不存在时，代码跳过写入但仍继续初始化，因而产生“服务成功、单项未生效”的假象。正确实现必须写 `happen_max_snd_ms`，并把 `fopen()` 或写入失败反馈到日志和返回值。

**④ 怎么判断 / 怎么处理**

保存 JSON 期望值与 sysfs 实际值。若两者不一致，临时手工写入只能用于验证，量产方案应修正属性名并增加失败日志。

**⑤ 要不要升级**

需要在命中上述特征时升级或修正用户态组件。升级后的可验证特征是：写入 `happen_max_snd_ms`，且路径打开或写入失败会被明确报告。

---------

## 第二类 · 心跳、周期调度与错误风暴

### FAQ-7：`heartbeat time:N` 是正常计数还是故障？

**其他问法**：`heartbeat time:1`｜为什么没有立即上报码｜Linux heartbeat 的门限

**一句话结论**：**【设计预期】** `heartbeat time:N` 是心跳连续 N 轮未收到应答的计数。检查周期为 `CYCLE_CHK_PERIOD`（20 ms），每轮内的等待窗口为 `SERVER_HEARTBEAT_TIMEOUT`（5 ms）；计数超过 5 并打印 `heartbeat timeout` 后，才正式上报心跳故障。

**① 现象/场景**

偶发 `heartbeat time:1` 后恢复，或连续出现 1～6 并伴随 `heartbeat timeout`。

**② 简答**

- 出现 `heartbeat timeout.`：已达到正式上报条件，应检查服务、Netlink 和系统负载。
- 同期已有大量其他错误：heartbeat 常是资源拥塞后的二次故障。

**③ 机制解析**

心跳检查位于 `diag_stl_cycle_check()`，它是 `diag_stl` 模块的周期回调，由 delayed work 按 `CYCLE_CHK_PERIOD` 驱动，即**每 20 ms 执行一轮**，因此 `heartbeat_time` 每 20 ms 最多递增 1。

每一轮的动作是：仅当计数为 0 时才重新初始化 completion 并通过 Netlink 发起心跳；随后以 `SERVER_HEARTBEAT_TIMEOUT`（5 ms）为上限等待应答。等待成功把计数清零；等待超时则打印并递增 `heartbeat_time`，本轮回调随即返回，剩余时间用于等待下一次 work 调度，期间不做心跳判断。所以 5 ms 是**单轮的等待窗口**，不是计数递增的间隔。计数大于 5 时打印 `heartbeat timeout.`、发送诊断事件并清零。

两个容易算错的细节：

- 因为只有计数为 0 时才重发请求，从第 2 轮起各轮都是在等首轮那次请求的迟到应答，计数与独立超时事件数相差 1。源码注释亦说明「计数为 5 时实际超时 4 轮」，这也是门限写作 `> 5` 而非 `>= 5` 的原因。
- `msecs_to_jiffies(5)` 在 `CONFIG_HZ=250`（1 jiffy = 4 ms）下向上取整为 2 jiffies，单轮实际等待约 8 ms。5 ms 是标称值。

因此 `heartbeat time:N` 不是“已收到 N 次心跳”，而是“已连续 N 轮未收到应答”。用户态 `NetlinkHeartBeatHandle()` 收到请求后返回约定响应，用于完成这次等待。

**④ 怎么判断 / 怎么处理**

先看计数是否连续增长，再查 `heartbeat timeout.` 是否出现；随后检查 `ax_diag_service` 存活状态、CPU/IRQ/日志负载、Netlink handshake，以及在它之前是否已有 I/O、总线或错误风暴。



**⑤ 要不要升级**

零星计数不需要升级，可以作为预警的信号：

- 计数密度随 CPU 负载、日志输出量或落盘操作同步升高：说明处理线程正被普通优先级任务抢占;
- 计数与密集故障上报同期出现（内核侧 pending 长时间不回零，或服务日志中 rcv event: 密集）：说明上报链路已在积压，安全故障的端到端时延正在恶化;

只有服务正常、系统无明显阻塞却稳定达到超时门限时，才需要进一步确认通信实现或版本缺陷。

---------

### FAQ-8：写了 module `cycle_enable=1`，为什么周期 STL 仍没运行？

**其他问法**：domain/module 两级开关｜`cycle_ms` 不准｜有节点但 callback 没调用

**一句话结论**：**【设计预期】** module 开关不是总开关；domain 也必须开启，且模块必须注册非空的周期回调。

**① 现象/场景**

module 的 `cycle_enable` 为 1，但 `last_time` 不更新；或者配置周期与观测周期相差几毫秒。

**② 简答**

同时检查 domain 开关、module 开关、回调注册和服务初始化。Linux 定时还受 jiffy 粒度约束。

**③ 机制解析**

`diag_stl_cycle_check()` 先检查 domain 的 `cycle_enable`，再遍历 module；只有 module 的 `cycle_enable` 非 0 且 `cycle_handle` 非空，才调用周期检查。M57H Linux 使用 `HZ=250` 时一个 jiffy 为 4 ms，毫秒配置转换为 jiffy 后会量化，因此 5 ms、10 ms 等配置不一定按任意毫秒精度触发。

**④ 怎么判断 / 怎么处理**

回读两级开关，确认目标模块注册日志和回调指针有效；记录 `cycle_ms`、`last_time`、实际间隔及 CPU load。不要通过缩短周期来掩盖回调未注册或服务未初始化的问题。



**⑤ 要不要升级**

不需要。两级开关和 jiffy 量化属于设计行为；若回调已注册且两级开关均为 1 仍从不执行，再进行版本定位。

---------

### FAQ-9：`cyclework overdue` / `cycle_schedule` 是否说明 FuSa 调度器坏了？

**其他问法**：PeriodicCaller 超时｜STL callback 没按时调用｜CPU 高负载后重启

**一句话结论**：**【配置·使用·方法】** 该日志只证明周期回调超过时间预算；总线阻塞、长临界区、错误风暴或 CPU 饥饿都可能是首因。

**① 现象/场景**

周期调度故障之后又出现 heartbeat、FCU timeout 或复位。

**② 简答**

从日志最后一条 schedule fault 不能反推 diagcore 是根因。必须按时间找它之前最早出现的 driver timeout、总线异常或错误风暴。

**③ 机制解析**

每个模块的 delayed work 执行时会更新 `last_time`、重新排队并调用周期回调；实际执行间隔比配置周期多出容差时，工作线程打印 `cyclework overdue`。全局 `diag_stl_cycle_check()` 还会检查当前时间是否超过 `last_time + 5 ms + 2 × cycle_jiffies`，超过后上报 `cycle_schedule`。这两项监控的是“回调有没有按预算获得执行机会”，无法单独区分 CPU 饥饿、workqueue 堵塞、回调内部阻塞还是硬件总线访问卡住。

**④ 怎么判断 / 怎么处理**

构造时间线：首个驱动/总线异常 → 第一次 callback overdue → heartbeat/FCU → reset。同步采集 CPU/IRQ、workqueue、串口日志速率和相关硬件访问耗时，先消除最早的阻塞源。



**⑤ 要不要升级**

不要仅凭该日志升级。消除负载或原始故障后仍稳定超时，且时间预算与产品配置匹配时，再评估调度实现。

---------

### FAQ-10：持续报错为什么让 CPU loading 越来越高？

**其他问法**：diag 刷屏｜错误节点越积越多｜ACK timeout 又产生新故障

**一句话结论**：**【已修故障】** 旧实现超时节点不会删除，等到回复才会删除，极端情况导致一个故障出现好几个超时故障，一个超时故障再触发几个超时故障，恶性循环。

**① 现象/场景**

某个错误持续上报后 CPU load 单调增长，接着出现 heartbeat 或 FCU timeout。

**② 简答**

先止住最早的故障源，同时确认错误处理线程能够排空 rbtree、ACK 能返回、全局周期任务已启动。只做日志限流不能解决队列堆积。

**③ 机制解析**

`diagnosis_error_send()` 将满足 debounce 条件的 error node 放入 report rbtree，并唤醒 `diag_error_handle_thread()`。若线程每次唤醒只取一个节点，而产生速度高于消费速度，rbtree 会不断增长；每个未确认节点又进入 ACK timeout list，周期扫描会继续处理超时，从而形成“积压 → 更多扫描和日志 → CPU 更忙 → 心跳更慢”的正反馈。修正后的处理线程包含内部循环，持续从 rbtree 取节点直到为空；ACK timeout 路径会从 list 移除已结束节点并延迟释放。

**④ 怎么判断 / 怎么处理**

检查最早错误的上报速率、用户态 ACK 是否正常、domain 周期是否开启，以及 CPU load 是否随 pending 节点持续增长。源码可核对 `diag_error_handle_thread()` 是否有排空 rbtree 的循环。



**⑤ 要不要升级**

如果版本仍是“一次唤醒只处理一个节点”，需要升级到具备队列排空和 timeout 节点回收的版本。若这些特征已存在，应优先修复原始错误风暴或 ACK 链路。

---------

### FAQ-11：为什么查询或密集报错时会出现 Call trace / RCU stall？

**其他问法**：`diagnosis_error_send` panic｜timeout list 随机地址｜`rcu stall`

**一句话结论**：**【已修故障】** 同一 error node 同时参与 report 和 ACK timeout 管理；旧实现若过早移除或释放，会产生 UAF、链表损坏或 RCU stall。

**① 现象/场景**

错误密集时出现 Call trace，或者查询状态触发崩溃，栈落在 list、rbtree 或诊断发送路径。

**② 简答**

增加 timeout 不能修复生命周期竞态。应确认版本使用完成标志协调 report/ACK，并通过 `call_rcu()` 延迟释放节点。

**③ 机制解析**

error node 入队后，一侧由上报线程从 rbtree 处理，另一侧由 ACK timeout list 跟踪。当前设计用 `report_flag` 表示两个独立完成条件：上报处理完成加 1，收到 ACK 加 2，值为 `0x3` 才表示两侧都结束。timeout 路径先用删除标志避免重复处理，再从链表摘除节点，通过 `call_rcu()` 等待已有读者退出，最后归还 mempool。旧实现若在另一侧仍持有指针时直接释放，下一次遍历就可能访问无效地址。

**④ 怎么判断 / 怎么处理**

保存完整 Call trace、最早 error、错误速率和用户态 ACK。源码核对 `report_flag` 的原子更新、timeout 删除标志以及 `call_rcu()` 回收是否同时存在；若均存在仍复现，继续检查重复 ACK 或未注册事件等新并发路径。



**⑤ 要不要升级**

缺少上述生命周期保护时需要升级。已经具备这些代码特征时，不要重复套用旧结论，应基于新栈重新定位。

---------

### FAQ-12：`E2E P04 Check ... failed` 怎么分型？

**其他问法**：wrong sequence｜CRC 不匹配｜故障注入后 E2E/IPC timeout

**一句话结论**：**【配置·使用·方法】** 同一 E2E 日志至少可能来自并发发送、两端初始化不同步或故障注入；必须结合触发时机和 P04 检查结果分型。

**① 现象/场景**

- 多线程或高压发送时偶发 sequence failure。
- 两端启动后的首包或首次握手失败。
- CRC 注入后连续出现 E2E 和 IPC timeout。

**② 简答**

| 场景           | 优先检查                                                     |
| -------------- | ------------------------------------------------------------ |
| 多个发送者并发 | `E2E_P04Protect()` 与 `rpmsg_send()` 是否由同一把锁完整串行化 |
| 启动首包失败   | A/R 两端 counter、初始化完成状态和 handshake 顺序            |
| CRC 注入后失败 | 是否为保护链丢弃被故意污染报文的预期结果                     |

**③ 机制解析**

E2E P04 会对 source ID、长度、counter 和 CRC 做一致性检查。发送端 `E2E_P04Protect()` 不仅计算 CRC，还会推进 counter；如果两个线程共享状态却分别执行 protect/send，报文发送顺序可能与 counter 顺序不一致。正确的 `diag_virt_send()` 用 `rpmsg_mutex` 覆盖“加保护 + 发送”整个区间。启动阶段若一端沿用旧 counter、另一端已经清零，也会在首包产生 sequence error。故障注入主动破坏 CRC 时，接收端拒绝坏报文是保护机制正常工作，随后等待该报文的业务可能继续报 timeout。

**④ 怎么判断 / 怎么处理**

记录 message type、P04 result、首次还是持续、是否执行过注入以及两端启动时间。并发场景核对临界区范围；启动场景重新检查 handshake；注入场景先停止注入并确认后续正常报文能够恢复。



**⑤ 要不要升级**

若 protect 和 send 没有被同一锁覆盖，或两端缺少初始化同步，需要升级。仅在 CRC 注入期间出现且停止注入后恢复，不需要升级。

---------

### FAQ-13：`FCU_HANDLER_TIMEOUT` 一定是 FCU 寄存器坏了吗？

**其他问法**：ISP 报错后 FCU timeout｜R 核注入 timeout 无结果｜SafetyIsland 刷屏

**一句话结论**：**【配置·使用·方法】** `FCU_HANDLER_TIMEOUT` 表示 FCU 相关处理没有在预算内完成，不等同于 FCU 寄存器回读错误。

**① 现象/场景**

ISP、ECM 等原始错误持续出现，之后才出现 FCU handler timeout；或者在 SafetyIsland 阻塞式测试中看不到预期结果。

**② 简答**

先找 timeout 之前的首个故障。FCU 硬件寄存器异常与 handler 软件超时是两类事件，必须分别验证。

**③ 机制解析**

handler timeout 监视的是一段处理流程的完成时间。原始故障高频出现时，A/R 通信队列、日志输出或同一任务中的错误处理可能被占满，FCU handler 即使没有寄存器故障也可能错过完成期限。SafetyIsland 为无 OS 或单主任务调度时，如果故障注入代码在被检测任务中永久阻塞，负责检查 handler 超时的代码也可能得不到执行；此时应由独立的 A 核路径、定时器或外部 watchdog 观察，而不能期待同一个被阻塞任务自报超时。

**④ 怎么判断 / 怎么处理**

同时采集 A/R 两侧日志，记录 FCU handler 进入、退出时间、RPMsg 队列状态和原始错误速率。先消除最早的错误风暴，再单独执行 FCU 硬件故障测试和 handler 超时测试。



**⑤ 要不要升级**

不能仅凭日志决定升级。若排除阻塞和错误风暴后 handler 仍稳定超时，再核对处理逻辑是否能在独立执行上下文中完成监控。

---------

## 第三类 · NPU、DDR、eMMC 与 CPU/GIC

### FAQ-14：NPU 上下电为什么出现 ECM fault，甚至串口卡住？

**其他问法**：NPU power-cycle｜clock/reset 时 ECM｜硬重启后 NPU fault

**一句话结论**：**【已修故障】** NPU clock/reset/power 切换期间不能继续读取 ECM/STL 监控寄存器；正确实现会在切换前关闭 monitor，资源稳定后再开启。

**① 现象/场景**

反复执行 NPU init/deinit、suspend/resume 或整机上下电时出现 NPU ECM，严重时控制台长时间无响应。

**② 简答**

确认 NPU monitor 的关闭和开启包住了完整的电源、时钟、复位及资源恢复窗口。只屏蔽错误码不能避免非法寄存器访问。

**③ 机制解析**

NPU ECM/STL monitor 会周期读取 NPU 寄存器并与期望状态比较。在 clock 已关、reset 正在拉动或 power domain 尚未稳定时，寄存器可能不可访问、返回复位值或处于变化中，导致误报，某些总线访问还可能长时间等待。当前 `npu_drv.c` 在 init 前先调用 `npu_stl_monitor_enable(false)`，待中断、ECM channel、CRC/IRQ 自检等初始化完成后再开启；deinit、suspend、硬资源重建和软资源释放同样在破坏硬件状态前关闭，resume 恢复完成后再开启。

**④ 怎么判断 / 怎么处理**

记录 NPU power state、clock/reset 调用、monitor enable 时刻和第一个 ECM channel。若第一个 ECM 恰好落在关闭时钟到恢复资源之间，检查是否漏掉某条关闭路径或过早重开 monitor。



**⑤ 要不要升级**

若目标版本没有用 `npu_stl_monitor_enable(false/true)` 完整包围 init、deinit、suspend、resume 和资源重建，需要升级；代码特征已具备时应检查项目新增的电源路径。

---------

### FAQ-15：改坏 NPU output，为什么 Verify 失败却没有诊断码？

**其他问法**：NPU pattern test 不上报｜应用说校验失败但 diag 无事件｜output 没有刷新

**一句话结论**：**【配置·使用·方法】** Verify 失败只有显式调用 `AX_DIAG_ReportEvent()` 才会进入诊断链；同时必须启动 `ax_diag_service`，并在每轮推理前清除旧 output。

**① 现象/场景**

应用打印 verify error，但诊断服务没有收到 NPU pattern event；或者 NPU 未真正更新输出却被旧数据误判为通过。

**② 简答**

确认三件事：运行前清空 output、Verify 失败分支调用上报 API、诊断服务已完成初始化。

**③ 机制解析**

`npu_fusa.cc` 的 `engine_do()` 先执行 `ClearOutputTensor()`，再 `RunModel()` 和 `Verify()`。清零的作用是避免本轮 NPU 未写输出时继续使用上一轮正确结果。`Verify()` 返回 false 后，代码用 `AX_DIAG_ReportEvent(AX_MAIN_BSP_NPU_NPU_PATTERN_TEST_ERROR, attr)` 报告事件。`npu_module.cpp` 的 sample 路径也需要在校验失败分支执行同一上报。该 API 的用户态事件还需要 `ax_diag_service` 运行，才能接收、维护状态并按策略发布。

**④ 怎么判断 / 怎么处理**

分别记录 `RunModel()`、`Verify()` 和 `AX_DIAG_ReportEvent()` 返回值；确认调用顺序包含 `ClearOutputTensor()`，并查看服务启动日志。不能只改 output 文件后观察 kernel dmesg。



**⑤ 要不要升级**

缺少清 output 或 Verify 失败上报调用时需要升级 sample/MSP；仅因服务未启动导致无事件时，修正启动顺序即可。

---------

### FAQ-16：DDR inline ECC 在高温或低温报错，怎么判断是软件、物料还是内存踩踏？

**其他问法**：高温刷 ECC｜低温重启刷屏｜uncorrectable 后 Call trace

**一句话结论**：**【配置·使用·方法】** 相同 ECC 事件可能来自高温 refresh 不足、器件超出温度规格或非法内存写入；必须结合温度、地址、综合征和调用栈判断。

**① 现象/场景**

同样出现 `ddr_sys_uncor_inline_ecc`，但触发温度、DDR 料号、错误地址和后续栈各不相同。

**② 简答**

- 错误随高温上升而增加：先查 refresh、temperature derating 和 DDR 规格。
- 测试温度低于物料下限：先更换满足该温度等级的物料做对照。
- 常温持续 uncorrectable，PC/LR 或代码页内容异常：检查越界写和非法 DMA。

**③ 机制解析**

inline ECC 在受保护的内存访问中校验数据：可纠正错误可被修复并计数，不可纠正错误意味着数据已无法可靠恢复。高温会缩短 DRAM 电荷保持时间，refresh 频率不足会增加 bit error；超出器件额定温度则不属于软件能够保证的工作条件。ECC 只说明“读取时数据与校验信息不一致”，不能指出是谁写坏了内存。若损坏落在代码、栈或页表，随后看到的随机 PC/LR 和 Call trace 是数据破坏结果，不是写入者证据。

**④ 怎么判断 / 怎么处理**

记录温度曲线、DDR 完整料号、refresh 配置、ECC 地址/综合征、correctable/uncorrectable 次数、最近 DMA/WDMA 操作和完整 Call trace。用温度合规物料、标准 refresh 和最小业务负载做交叉对照。



**⑤ 要不要升级**

先按证据分类。refresh 配置不满足目标温区时更新配置/版本；物料超规格应更换物料；内存踩踏需要定位写入源，升级 FuSa 本身不能消除越界写。

---------

### FAQ-17：4 GB DDR inline ECC 是否已经支持？

**其他问法**：ECC 只能覆盖部分 4 GB｜4 GB 地址怎么划分｜能否直接用于量产

**一句话结论**：**【配置·使用·方法】** 4 GB inline ECC 是启动链端到端能力，只有 boot 各阶段对容量和 ECC 区域理解一致并完成验证，才能认定支持。

**① 现象/场景**

系统能够识别 4 GB，但 ECC 只覆盖部分空间，或者边界地址注入/访问异常。

**② 简答**

不能以“Linux 显示 4 GB”或单处地址计算改动作为支持结论。必须验证 SafetyIsland、U-Boot 和 Linux 使用相同的 total size、ECC block 边界及可用容量。

**③ 机制解析**

inline ECC 会占用部分物理存储保存校验信息，所以“物理容量”与“客户可用容量”并不相同。启动早期代码通过 `ddr_ecc_info` 传递 64 bit `total_size`、两个 ECC block 的 offset、physical size 和 valid size；后续阶段据此配置保护窗口、初始化或 scrub 内存，再把可用区域交给 Linux。任一阶段仍按较小容量、32 bit 边界或不同 block 公式计算，都会形成未覆盖区域、重叠区域或边界越界。

**④ 怎么判断 / 怎么处理**

核对启动日志和内存映射中的总容量、两个 ECC block 的起止地址、physical/valid size；分别在每个 block 的首尾做读写和注入验证，并完成冷启动、热启动、压力和性能测试。



**⑤ 要不要升级**

只有当前发布包明确声明并验证 4 GB inline ECC 时才能直接使用。否则应升级到具备端到端 4 GB 支持的正式版本，不能只替换某一个启动阶段的组件。

---------

### FAQ-18：DDR cycle/bus-lock 报错可以直接屏蔽吗？

**其他问法**：perf monitor 一加载就刷 DDR｜DDR retraining 触发 bus lock｜能否 bypass 寄存器

**一句话结论**：**【配置·使用·方法】** mask 或 bypass 只减少检测覆盖，不会修复真实硬件故障；仅在证明共享寄存器产生误报并完成安全评估后使用。

**① 现象/场景**

- 加载性能监控后 DDR cycle check 开始刷屏。
- DDR retraining 期间出现 Safety bus-lock 周期错误。

**② 简答**

先确认是否有另一个合法模块同时写同一寄存器。能通过协调访问或更新期望值解决时，不应直接关闭检测。

**③ 机制解析**

cycle check 保存寄存器期望值，并在周期回调中读取硬件比较。正常驱动通过 STL 包装写寄存器时，会同时更新硬件值和保存值；性能监控或 retraining 若绕过包装直接改同一寄存器，周期检查可能比较“新硬件值”和“旧期望值”而误报。bypass 某个 offset 或关闭某个 monitor 只是让比较不再发生，真实总线错误也将不再被该机制发现。

**④ 怎么判断 / 怎么处理**

记录错误 offset、read/saved value 和所有写入者；确认错误是否只发生在 perf monitor/retraining 窗口，窗口结束后能否恢复。优先让合法写入者同步更新期望值，无法避免时才做最小范围 bypass，并记录安全覆盖变化。



**⑤ 要不要升级**

共享寄存器所有权已经明确且当前版本没有协调机制时，应使用包含相应访问协调或精确 bypass 的正式版本；不要通过全局 mask 代替升级和安全评估。

---------

### FAQ-19：eMMC cycle mismatch 后又报 heartbeat，是不是已修？

**其他问法**：高负载 eMMC 周期检测｜正常 I/O 和 STL 冲突｜加锁是否有效

**一句话结论**：**【配置·使用·方法】** eMMC 正常 I/O 与 STL 周期读取若未同步，可能比较到不同代的硬件值和保存值；其后的 heartbeat 可能是 I/O/错误处理压力造成的连锁现象。

**① 现象/场景**

业务高负载时偶发 eMMC cycle mismatch，下一周期自行恢复，随后可能出现 heartbeat 计数或 timeout。

**② 简答**

debounce 能过滤部分瞬态，但不是并发修复。应确认正常写路径与周期读路径共用同一同步机制。

**③ 机制解析**

正常 I/O 路径先写 eMMC 控制器或 PHY 寄存器，再更新 STL 保存的期望值；周期线程则读取硬件值并读取保存值。两条路径无锁交错时，周期线程可能在“硬件已更新、保存值尚未更新”或相反窗口内比较，产生瞬态 mismatch。正确实现对 SRS/HRS 等可在原子上下文访问的数据使用适合该上下文的自旋锁，对可能睡眠的 PHY 路径使用 mutex，并让正常写和周期读都持有对应锁。大量 mismatch 上报和 I/O 阻塞还会增加诊断线程负载，从而拖慢 heartbeat。

**④ 怎么判断 / 怎么处理**

记录寄存器 offset、read/saved value、I/O 压力、下一周期是否恢复以及 heartbeat 的先后顺序。检查 `sdhci-axera-stl.c/.h` 中是否存在同时覆盖写端和检查端的 `reg_data_lock`、`phy_reg_data_lock` 或等价同步。



**⑤ 要不要升级**

缺少双端同步且问题能在 I/O 压力下复现时，需要升级到包含等价并发保护的正式版本；升级后还要验证吞吐、时延和 IRQ 上下文合法性。

---------

### FAQ-20：lockstep 模式下 CPU/GIC 周期指令 STL 为什么不执行？

**其他问法**：lockstep 开启后 CPU STL 少了｜是否丢失安全机制｜AON bit16

**一句话结论**：**【设计预期】** lockstep 模式会跳过只适用于 split mode 的 CPU instruction 和 GIC 周期 STL，但 Basic STL 仍会注册。

**① 现象/场景**

与 split mode 对比，lockstep 下部分 CPU/GIC periodic case 不运行。

**② 简答**

这是按 CPU 工作模式选择测试项，不是整个 CPU FuSa 被关闭。

**③ 机制解析**

`Cpu_Stl_Init()` 读取 AON bond 的 bit16 判断 split/lockstep。仅在 split mode 下初始化 R5_STL、执行 boot instruction/GIC 检查并注册 `Cpu_Stl_Cycle()`；无论哪种模式都会调用 `Cpu_Stl_Basic_Register()`。lockstep 的 Basic 注册项包含 lockstep compare、GIC compare，以及 OCM/IRAM、TCM、cache 等 ECC 事件，因此只是测试矩阵不同，并非没有 CPU/GIC 保护。

**④ 怎么判断 / 怎么处理**

先读取实际模式位，再按该模式的测试矩阵验收。不要用 split mode 的周期 case 数量判断 lockstep 是否正常。



**⑤ 要不要升级**

不需要。只要 Basic STL 正常注册且 lockstep 比较/ECC 事件可验证，就是设计行为。

---------

### FAQ-21：RAS 注入为什么只看到 FCU main error，没有 CPU/RAS 诊断码？

**其他问法**：`ras inject error`｜RAS 注入无专用码｜SDEI 与 DIAG 的关系

**一句话结论**：**【已修故障】** 旧注入路径可能只触发通用 FCU 反应；正确实现会在 RAS 注入成功后显式发送 CPU/RAS 诊断事件。

**① 现象/场景**

RAS 注入返回成功，但用户态只能看到通用 FCU main error，没有专用 CPU/RAS 事件。

**② 简答**

检查注入成功分支是否调用 `diagnosis_error_send(&de_ras)`；不能依赖 FCU 通用事件反推出 RAS 专用事件。

原来的设计预期是不上报故障，如果出现了UE的情况，主域挂死，依旧是收不到诊断码。

目前增加了故障码上报，当发生了CE的时候，能看到故障码上报。

**③ 机制解析**

`ras_inject()` 通过 ARM RAS 系统寄存器选择错误记录、配置错误类型并触发 pseudo fault。硬件异常可通过 SDEI event 进入 `ca55_ras_sdei_handler()`，该 handler 会发送 `de_ras`。但软件注入工作 `ras_inject_work_func()` 是另一条路径：如果注入成功后只设置硬件状态而不显式调用诊断上报，用户态可能只看到 FCU 对异常的通用反应。修正后的成功分支设置 `de_ras.status/stage` 并调用 `diagnosis_error_send()`，从而直接产生 CPU/RAS 专用事件。

**④ 怎么判断 / 怎么处理**

同时保存注入返回值、`Injected single error`、SDEI/RAS 日志、专用 DIAG ID 和 FCU 日志。源码核对 `ras_inject_work_func()` 的成功分支是否显式发送 `de_ras`。



**⑤ 要不要升级**

成功分支没有专用事件上报时需要升级；已经显式调用 `diagnosis_error_send(&de_ras)` 时，应继续检查事件开关、report 位和用户态服务。

---------

### FAQ-22：`main_ext_X` 日志很多，mask 掉是否等于问题解决？

**其他问法**：`ISP_SENSOR_FAULT_MAIN_EXT`｜`fault_main_ext_mask=0x00`｜客户不需要这些日志

**一句话结论**：**【配置·使用·方法】** `fault_main_ext_mask` 只决定哪些 FCU main_ext source 可以进入报告链，不会清除底层 source。

**① 现象/场景**

业务功能看似正常，但持续出现 `main_ext_X`，项目考虑通过 DTS mask 停止日志。

**② 简答**

可以按产品安全分析调整 mask，但对外结论应是“关闭该 source 的诊断报告”，不能写成“底层故障已经修复”。

**③ 机制解析**

FCU 驱动从 DTS 读取 `fault_main_ext_mask`，用每个 bit 允许或阻止对应 main_ext source 进入后续状态判断和报告。mask 为 0 后，软件不再把这些输入转换为诊断事件；硬件引脚、传感器或上游模块的状态并没有被复位或修复。该设置还会降低对应故障的可观测性和系统反应能力。

**④ 怎么判断 / 怎么处理**

先确认 source 的电气/业务含义及误报原因，再决定 mask。变更后同步更新 fault list、安全分析和验证用例，并保留能够直接读取底层 source 状态的调试方法。



**⑤ 要不要升级**

通常不需要，属于项目配置。若目标 DTS 不支持逐 source mask，才需要使用支持该属性的正式版本。

---------

### FAQ-23：为什么关闭 Extend 会导致 A 核起不来，或 `diag-extend` 节点消失？

**其他问法**：Extend 不使用能否裁掉｜DFC 共用配置宏｜没有 `diag-extend` 目录

**一句话结论**：**【配置·使用·方法】** 当前 Extend 与诊断核心编译在同一个 `CONFIG_AXERA_DIAG_CORE` 组件中；直接关闭共享宏会把核心 API 和服务一起裁掉。

**① 现象/场景**

为裁剪 Extend 关闭配置后系统启动失败，或者保留核心却看不到 `diag-extend` sysfs。

**② 简答**

不要把“不使用 Extend”直接转换为关闭 `CONFIG_AXERA_DIAG_CORE`。核心是否存在与 Extend platform device 是否 probe 是两个不同问题。

**③ 机制解析**

FuSa `Makefile` 在 `CONFIG_AXERA_DIAG_CORE` 打开时构建 `diag-core`，其对象列表同时包含 `diag_core.o`、`diag_sysfs.o`、`diag_extend.o` 等。关闭该宏后，`diag.h` 中的诊断 API 会退化为空操作或不再提供核心实现，依赖诊断注册和状态管理的模块也随之改变。另一方面，`diag_extend.c` 仍是 platform driver，只有 DTS 中存在匹配 `compatible = "axera,diag-extend"` 的设备且 probe 成功，才会出现对应节点；节点缺失不能直接说明整个 diagcore 未编译。

**④ 怎么判断 / 怎么处理**

先检查 kernel config 中 `CONFIG_AXERA_DIAG_CORE`，再查 `diag-core` 加载日志、`axera,diag-extend` DTS 节点和 `diag_extend_probe()` 结果。若确需裁剪 Extend，应先拆分构建依赖并完成 boot、核心上报、sysfs 和注入回归。



**⑤ 要不要升级**

保持完整诊断功能时不需要升级，也不要关闭共享宏。只有产品明确要求独立裁剪 Extend 时，才需要使用已拆分配置依赖的版本。

---------

## 第四类 · 构建、服务与 sample

### FAQ-24：FuSa Excel 为 0 字节，或 `make fusa_config` 失败，怎么查？

**其他问法**：fault Excel size 0｜Python/pandas 错误｜生成枚举后编译失败

**一句话结论**：**【配置·使用·方法】** 先区分输入文件损坏、主机 Python 依赖和平台配置不同步；三类问题的修复路径不同。

**① 现象/场景**

- 平台 Excel 文件大小为 0；
- 生成器报 Python 或 pandas import/open 错误；
- 新增模块后枚举未生成，后续 C/C++ 编译失败。

**② 简答**

| 现象                    | 首查                                                        |
| ----------------------- | ----------------------------------------------------------- |
| Excel 为 0 字节         | 软件包完整性、文件大小和校验值                              |
| Python import/open 失败 | 构建机 Python、pandas、Excel 读取依赖                       |
| 枚举或模块缺失          | 公共 Kconfig、目标 `PLAT` Excel、生成输出是否来自同一批配置 |

**③ 机制解析**

`generated_diag_config.py` 首先用 pandas 打开二进制 Excel；空文件或依赖缺失会在解析阶段失败，后续所有配置都不会生成。解析成功后，脚本根据平台表中的事件和模块开关生成各端枚举/config；如果公共 Kconfig 开启了一个 STL，但目标平台 Excel 没有对应定义，编译期代码会引用不存在的枚举。应以生成过程最早的错误为根因，不能只处理最后的编译报错。

**④ 怎么判断 / 怎么处理**

保存完整生成日志、Python/pandas 版本、`PLAT`、Excel 文件大小与校验值，以及生成前后的差异。确认输入非空且来源正确后，再安装项目规定的 Python 依赖并重新生成。



**⑤ 要不要升级**

文件损坏或环境缺依赖不需要升级 SDK；平台表与公共配置缺项时，应使用彼此配套的平台配置包，不能拿其他平台 Excel 覆盖。

---------

### FAQ-25：“FuSa 编译失败”有哪些高频非源码原因？

**其他问法**：rootfs overflow｜`diagnose.dbc` 不生成｜ARMCLANG 链接失败｜clean 后缺文件

**一句话结论**：**【配置·使用·方法】** 高频原因是 `PLAT` 选错、rootfs 空间不足、工具链 ABI 不匹配或打包清理掉必需预编译件；应从第一条错误开始定位。

**① 现象/场景**

- sample 增大后最终镜像打包失败；
- 找不到 `diagnose.dbc`；
- SafetyIsland 链接时出现 ABI/浮点符号错误；
- 清理或重新打包后缺少闭源中间件。

**② 简答**

| 第一类错误               | 机制与检查项                                                 |
| ------------------------ | ------------------------------------------------------------ |
| image/partition overflow | rootfs payload 已超过分区或镜像上限，检查实际占用和配置容量  |
| `diagnose.dbc` 缺失      | `PLAT` 决定 Excel 与生成目标，先确认平台选择及 `fusa_config` 是否执行 |
| float/ABI/link 错误      | ARMCLANG、`arm-linux-gnueabi` 与 aarch64 GCC 的目标和 ABI 不能混用 |
| clean 后缺 `.a/.so`      | 清理规则删除了没有源码可重建的预编译件，需要恢复交付包或修正规则 |

**③ 机制解析**

主 Linux 系统使用 aarch64 GCC/glibc，SafetyIsland 使用另一套 ARM 工具链和 ABI；对象文件只在架构、浮点 ABI 和运行库匹配时才能链接。`PLAT` 又决定所选平台的 Excel、DBC、分区和 rootfs 内容。编译、生成、链接、打包是连续但独立的阶段，最后一条 `make: Error` 只是上游失败的传播结果。

**④ 怎么判断 / 怎么处理**

保存第一条 error，而不是只截末尾；同时记录 `PLAT`、compiler/version/flags、rootfs payload/limit 和缺失产物的来源。按“生成 → 编译 → 链接 → 打包”确定最先失败的阶段。



**⑤ 要不要升级**

通常不需要。平台、空间和工具链修正后即可；只有正式构建规则会误删必需交付件时才需要更新构建包。

---------

### FAQ-26：改了 Excel G 列或 fault switch，为什么仍然上报？

**其他问法**：关闭 ISP 不生效｜fault list 被覆盖｜服务启动顺序｜预编译 ko 仍有节点

**一句话结论**：**【配置·使用·方法】** Excel/JSON 定义策略，用户态服务负责运行时下发；节点是否存在、检测是否开启和事件是否上报是三个不同层次。

**① 现象/场景**

源 Excel 已关闭某项，但板上仍能看到节点，或业务启动后仍收到该事件。

**② 简答**

按四个位置逐项对照：源 Excel → 生成 JSON → rootfs 实际 JSON → sysfs 实际值。只看其中一处不能证明配置已生效。

**③ 机制解析**

编译期配置决定驱动和模块是否进入镜像，模块注册后会创建 sysfs 节点；因此“节点存在”不等于事件 enable 为 1。运行时 `ax_diag_service` 读取 rootfs 中的 JSON，通过 `SendDiagConfigToKernel()` 写事件 `enable`、debounce、周期和 `handle_config`，最后开启 domain 周期任务。若服务晚于业务启动、加载了另一份 JSON、写节点失败或使用预编译 ko，源 Excel 的修改都不会自动改变当前运行状态。

Safety的节点是静态配置的，及时是关闭了Excel G列，依旧会显示出来，但是故障注入通路是断开的，这是设计预期。

**④ 怎么判断 / 怎么处理**

回读 event `enable`、module/domain `cycle_enable` 和 `handle_config`；检查服务是否在业务前启动，以及 rootfs JSON 是否就是本次生成结果。对预编译 ko，还要确认其模块/事件表与本次 JSON 匹配。



**⑤ 要不要升级**

配置或启动顺序问题不需要升级。若服务写入失败却仍报告成功，应升级到能检查每项写入并输出明确错误的版本。

---------

### FAQ-27：输入文件不存在却不报 pattern fault，是漏检吗？

**其他问法**：IVPS missing input｜golden data 在哪里｜启动自检与周期自检

**一句话结论**：**【设计预期】** 部分 pattern 的 input/golden 已编译进程序，外部文件不参与当前校验；删除无关文件自然不会触发 pattern fault。

**① 现象/场景**

删除输入文件或传空路径后，测试仍运行，且没有得到预期 pattern error。

**② 简答**

先确认实际数据来源和测试入口。外部文件、启动自检、周期自检和 sample 参数校验可能是四条不同路径。

**③ 机制解析**

pattern test 的基本过程是准备 input、执行硬件处理、把 output 与 golden 比较，再在 mismatch 时调用诊断上报。若 input/golden 以数组形式编译进 binary，运行时不会打开外部文件，删除文件只会影响仍使用路径参数的 sample 解析逻辑。启动自检通常在模块初始化阶段执行一次，周期自检则由 `AX_DIAG_StartPeriodicCheck()` 或已注册的 cycle callback 驱动；触发一个入口不能证明另一个入口已运行。

**④ 怎么判断 / 怎么处理**

查看实际测试函数的数据指针来自内嵌数组还是文件读取，确认执行的是 startup 还是 periodic 路径。选择真正参与比较的可控 corruption 点，并验证代码最终执行到 `AX_DIAG_ReportEvent()` 或 `diagnosis_error_send()`。



**⑤ 要不要升级**

内嵌 golden 属于设计，不需要升级。若 sample 文档仍要求一个实际未使用的文件，应更新测试说明；若 mismatch 分支没有上报调用，再升级相关 sample。

---------

### FAQ-28：版本名称带 “fusa” 时，UVC、KASAN 或媒体崩溃都算 FuSa 问题吗？

**其他问法**：UVC 卡帧｜VPP 越界｜kmemleak｜退出应用后 Call trace

**一句话结论**：**【配置·使用·方法】** FuSa 镜像名称不是故障归属证据；FuSa 可能只是检测或报告了其他模块已经发生的故障。

**① 现象/场景**

系统运行的是 FuSa 镜像，随后在 UVC、VPP、VENC、JENC、AXDMA 或应用栈中发生 WARN/Oops，之后又出现 heartbeat/FCU。

**② 简答**

以时间线上第一个异常和 PC/LR 所属模块归因。只有栈、状态机或数据损坏首先落在 diag、STL、E2E/IPC、配置下发链时，才优先归诊断框架。

**③ 机制解析**

FuSa 的职责是周期检查、错误收集、跨核转发和系统反应。媒体越界、USB 传输异常、资源释放竞态或非法 DMA 可能先破坏内存或阻塞 CPU；诊断框架随后检测到 cycle overdue、ECC、heartbeat 或 FCU timeout。这些后续事件描述的是系统已受影响的状态，不能反向证明诊断框架制造了最初故障。KASAN 的首个 invalid access 栈、硬件 timeout 前的驱动日志和最早异常地址比最后的复位原因更接近根因。

**④ 怎么判断 / 怎么处理**

保留第一个 WARN/Oops 之前的日志、完整 Call trace、PC/LR、故障地址和当时业务操作；按代码 owner 定位原始模块。把后续 heartbeat/FCU 作为同一时间线的连锁现象，而不是另起一个根因。



**⑤ 要不要升级**

不能因为镜像名称或后续 FuSa 日志决定升级。应先修复首个异常所属模块；只有首个异常明确落在诊断框架时才评估 FuSa 版本。