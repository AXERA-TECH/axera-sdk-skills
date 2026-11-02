# 快起 4星与 5星高质量缺陷全景知识库与排查检索指南

本指南基于真实异构双核快起工程实践，对经过严格技术清洗、评定为 **5星（38条，深度架构/致命缺陷/经典先例）** 与 **4星（75条，高频并发/边界死锁/模块级联）** 的共计 **113条** 高质量典型缺陷案例进行系统化分类归纳、底层机制解剖与排查指引总结。

旨在为工程团队提供一份覆盖异构双核交接、CMM跨核内存、图像流水线、智能模型、系统启动性能与外设环境的**快起疑难问题全景速查诊断字典**。

---

## 双核交接与跨核通信 (共 30 条：5星 10 条，4星 20 条)

### 1. 核心技术机理与故障规律总结
- **交接状态机单点脆弱性**：Linux TakeOver 过去采用死等机制，任一子模块（如 ModID 11 VENC/IVPS）未响应或 HandOverCB 回调挂起，全系统即永久阻塞。
- **底层通信通道崩溃**：RPMSG 队列溢出、Poll 线程未退避死循环或底层中断丢包，直接阻断双核握手消息传递。
- **双核生命周期管理错位**：交接未完成时突发收到 reboot 指令、或者交接完成释放小核 CPU 时未妥善下电导致 rt_hw_cpu_shutdown 内核断言。
- **外设 Claim 互斥冲突**：RTOS 启动初期对多组 I2C/SPI 全量强占，阻断 Linux 端提前通信（4G模组/PMIC/RTC）。

### 2. 5星与4星核心工单检索与机制清单

| 推荐指数 | 案例编号 | 影响阶段 | 故障特征与分类 | 故障机理与技术分析要点 |
|---|---|---|---|---|
| **5星 (强烈推荐)** | Case-001 | Pre-Handover | 硬件资源互斥与Claim机制 | **【行业客户】【打猎相机】多组i2c 全部被小核占用，导致交接前无法使用**<br>↳ *核心机制*：打猎相机外设I2C通道被小核硬编码占满导致4G模组挂死，双核资源竞争典型 |
| **5星 (强烈推荐)** | Case-002 | In-Handover | 交接超时/时钟状态不一致 | **开启AUTO-ISP，运行14058轮，RTOS到Linux的handover失败**<br>↳ *核心机制*：高负载压测下长周期稳定性，NPU/ISP在Handover时主从核时钟状态不一致导致挂死 |
| **5星 (强烈推荐)** | Case-003 | In-Handover | VIN快启握手超时等待 | **运行1027轮后，syslog打印大量vin_fastboot.c(931) id[0x80] mod_id[0x83] not ready, wati_time_ms[14800]**<br>↳ *核心机制*：vin_fastboot模块级联依赖未就绪，握手长达14.8s最终超时的典型时序缺陷 |
| **5星 (强烈推荐)** | Case-004 | In-Handover | RTOS关核/停机断言崩溃 | **64M快启运行1213轮后交接失败，rtos侧提示：assertion failed at function:rt_hw_cpu_shutdown**<br>↳ *核心机制*：交接完成释放小核CPU时断言失败，揭示RTOS Shutdown生命周期管理缺陷 |
| **5星 (强烈推荐)** | Case-005 | In-Handover | 交接并发重启死锁 | **从核运行出流或主从交接过程中，向主核发送reboot命令后系统卡死**<br>↳ *核心机制*：在主从交接的临界窗口收到reboot命令，两核状态不一致死锁 |
| **5星 (强烈推荐)** | Case-006 | In-Handover | 互斥锁Owner为空断言 | **983轮交接失败，mutex owner 为空引发assert**<br>↳ *核心机制*：跨核通信或多线程在释放锁时owner已被清空，多核并发时序竞态经典 |
| **5星 (强烈推荐)** | Case-007 | In-Handover | RPMSG底层请求通道失败 | **运行269轮后断流，RTOS调用ax_rpmsg_request失败，Linux等待交接完成，RTOS打印sys模块交接失败**<br>↳ *核心机制*：底层RPMSG通道无响应，导致上层SYS交接状态机全面阻塞 |
| **5星 (强烈推荐)** | Case-008 | In-Handover | 心跳轰炸导致接管延迟拖长 | **rtos启动过程一直刷屏send heart msg to linux for start takeover at mode 0，Linux开始交接拖长至11s**<br>↳ *核心机制*：RTOS心跳消息风暴，Linux端卡在等待或处理不过来，导致启动劣化至11s |
| **5星 (强烈推荐)** | Case-009 | In-Handover | 无超时保护的死等机制 | **快启TakeOver使用无限等待且缺少可查询的RTOS资源释放状态**<br>↳ *核心机制*：系统设计缺陷：Linux TakeOver采用无限死等，且无状态查询接口，单点异常全盘卡死 |
| **5星 (强烈推荐)** | Case-010 | In-Handover | 特定模块HandOver回调卡死 | **4388轮断流，SYS接管函数卡在ModID[11].HandOverCB start to run**<br>↳ *核心机制*：ModID[11]（VENC/IVPS）HandOverCB回调函数卡死，展示模块化交接的单点阻塞 |
| 4星 | Case-011 | In-Handover | 交接中模型提早失败引发断流 | **运行1450轮，vin断流**<br>↳ *核心机制*：双摄快启交接期模型解析失败导致VIN级联断流 |
| 4星 | Case-012 | In-Handover | 双摄从核状态异常未触发交接 | **双摄拼接，重启出现断流，rtos侧未交接**<br>↳ *核心机制*：双摄拼接场景RTOS未完成初始化或未发送交接请求导致Linux侧无限等待 |
| 4星 | Case-013 | In-Handover | 模型交接与Pipe启动时序 | **2571轮RTOS交接失败，AX_VIN_StartPipe失败，打不开模型**<br>↳ *核心机制*：模型句柄交接异常导致Linux接管后VIN StartPipe失败 |
| 4星 | Case-014 | Post-Handover | 交接失败后Reboot挂死 | **2721轮交接失败，reboot失败，MonitorSDCardStop计数异常**<br>↳ *核心机制*：Handover失败后系统清理不彻底，引发二次重启锁死 |
| 4星 | Case-015 | In-Handover | RTOS交接卡死 | **RTOS在交接中卡住，vin报错**<br>↳ *核心机制*：RTOS主循环在释放外设时发生死锁 |
| 4星 | Case-016 | In-Handover | SKEL跨核握手失败 | **运行1414轮后断流，VIN卡住，SKEL交接失败**<br>↳ *核心机制*：智能算法模块在交接阶段未响应，阻塞全链路 |
| 4星 | Case-017 | In-Handover | ISP子系统交接超时 | **isp交接超时导致断流**<br>↳ *核心机制*：ISP状态机在主从核切换时未能按时同步 |
| 4星 | Case-018 | In-Handover | 从核断流导致交接失联 | **156轮交接失败，Linux等待交接中，rtos侧yuv和venc均断流，未触发skel回调**<br>↳ *核心机制*：RTOS流水线中断，无法到达交接点触发SKEL回调 |
| 4星 | Case-019 | In-Handover | HDR宽动态模式交接失败 | **HDR交接失败**<br>↳ *核心机制*：HDR双曝光交接时参数与时钟切换异常 |
| 4星 | Case-020 | In-Handover | 外设释放接口返回错误码 | **交接失败：AX_VIN_DisableDev failed, devId=0, ret=0x8011011**<br>↳ *核心机制*：DisableDev返回0x8011011，设备处于不可注销状态 |
| 4星 | Case-021 | In-Handover | 双摄小核交接执行错误 | **双摄快启4+2m，从核报handover run error**<br>↳ *核心机制*：双Sensor在RTOS端的解耦与分步释放错误 |
| 4星 | Case-022 | In-Handover | RPMSG同步返回超时 | **19轮交接失败，ax_sys_rpmsg_send_data_and_return, get result fail**<br>↳ *核心机制*：消息已发送但Linux侧未能及时处理并回包 |
| 4星 | Case-023 | In-Handover | RPMSG缓存满或队列异常 | **快启5-6轮次后交接失败，打印rpmsg send failed**<br>↳ *核心机制*：RPMSG通道在启动初期突发大包丢弃 |
| 4星 | Case-024 | In-Handover | 首次启动即发生停机断言 | **128M快启首次交接，rtos侧在skel中触发rt_hw_cpu_shutdown断言**<br>↳ *核心机制*：128M配置下首次交接触发小核停机断言崩溃 |
| 4星 | Case-025 | In-Handover | 小核无视交接指令持续跑帧 | **128m单2m偶现rtos侧一直以15fps出帧，未与linux侧正常交接**<br>↳ *核心机制*：RTOS未收到或未响应接管信号，形成僵尸工作状态 |
| 4星 | Case-026 | In-Handover | 帧流转正常但握手失联 | **128M快启运行1469轮次后交接失败，rtos侧帧正常流转但无法交接**<br>↳ *核心机制*：小核VIN/VENC流水线正常，跨核事件通知机制失效 |
| 4星 | Case-027 | Post-Handover | 交接失败后内存越界崩溃 | **快启起流交接失败后，串口过段时间会刷屏segmentation fault**<br>↳ *核心机制*：交接失败后未释放的悬空指针被后续任务访问触发段错误 |
| 4星 | Case-028 | In-Handover | 外置DDR模式心跳通信阻断 | **外置DDR设置aiisp_mode 1重启快启失败，串口反复提示recv submsg: heart**<br>↳ *核心机制*：AIISP模式下外置DDR共享内存访问配置错误，双核心跳握手停滞 |
| 4星 | Case-029 | In-Handover | NPU模型句柄跨核共享失败 | **NPU模型handle交接未就绪**<br>↳ *核心机制*：NPU权重和上下文句柄无法平滑移交给Linux |
| 4星 | Case-030 | In-Handover | RPMSG Poll线程死循环 | **【MIS20S1】qsdemo初始化过程异常，报错wait fail id: 2, timeout: 1000，syslog刷屏打印AX_RpmsgPollThread][ 142]: poll failed, -1**<br>↳ *核心机制*：RPMSG poll失败后未合理退避，日志刷屏并超时 |

---

## 内存管理与资源泄漏 (共 25 条：5星 10 条，4星 15 条)

### 1. 核心技术机理与故障规律总结
- **跨核物理地址与虚拟地址失步**：Linux 在未交接或异常退出时释放 CMM，向 RTOS 反查 kvirt 时因未初始化脏数据导致传给 __vunmap 触发致命空指针 Oops。
- **接管位图与地址池混乱**：Linux 接管 RTOS 预分配的 CMM 池后，物理地址位图未同步导致新申请拿到重叠物理地址，产生严重踩内存。
- **极限受限内存（64M DDR）OOM**：快启双核过渡期系统同时驻留小核缓冲帧与 Linux 缓冲帧，造成内存峰值翻倍触发 OOM Killer。
- **跨核 DMA 越界践踏**：硬件外设 DMA 地址未在交接时复位或配置错误，直接将图像数据写入 Linux Kernel 代码段导致卡死。

### 2. 5星与4星核心工单检索与机制清单

| 推荐指数 | 案例编号 | 影响阶段 | 故障特征与分类 | 故障机理与技术分析要点 |
|---|---|---|---|---|
| **5星 (强烈推荐)** | Case-031 | In-Handover | CMM跨核内存池交接失败 | **快启4+2m压测2台均出现cmm交接失败**<br>↳ *核心机制*：双摄高负载场景CMM连续物理内存交接给Linux失败，大内存块碎片化典型 |
| **5星 (强烈推荐)** | Case-032 | All-Stages | 快启与常电CMM不一致 | **[快启][内存] CMM 内存理论上都要交接，对于CMM 消耗和常电一致**<br>↳ *核心机制*：架构设计单：快启小核预分配的CMM必须无缝并入Linux CMM池，不能凭空多出开销 |
| **5星 (强烈推荐)** | Case-033 | Post-Handover | 接管Agent动态切换内存泄漏 | **快启从rtos接管的 mem agent 在SDR/HDR切换后内存泄露**<br>↳ *核心机制*：RTOS交接给Linux的mem agent在动态SDR/HDR重配时未释放旧buffer引发泄漏 |
| **5星 (强烈推荐)** | Case-034 | Post-Handover | 64M极限内存OOM | **64M快启单摄2m稳定性压测出现OOM**<br>↳ *核心机制*：64M DDR极度受限环境，快启交接后系统留存双份中间buffer触发Linux OOM Killer |
| **5星 (强烈推荐)** | Case-035 | In-Handover | 模型权重mmap映射耗尽 | **7345轮交接失败，权重交接失败，mmap失败**<br>↳ *核心机制*：长跑数千轮后虚拟内存或CMM物理地址映射mmap失败，揭示资源未解绑泄漏 |
| **5星 (强烈推荐)** | Case-036 | Post-Handover | CMM vunmap非法释放Panic | **reboot后偶现panic，CMM内存释放向__vunmap传入无效/已释放虚拟地址**<br>↳ *核心机制*：交接解绑时Linux内核CMM驱动向__vunmap传递野指针/重复释放，内核Oops |
| **5星 (强烈推荐)** | Case-037 | Post-Handover | 物理地址池重叠分配(踩内存) | **快启接管完成后在Linux申请CMM内存出现物理地址重复**<br>↳ *核心机制*：CMM接管后位图(bitmap)管理混乱，导致两个不同模块拿到相同物理地址互相踩踏 |
| **5星 (强烈推荐)** | Case-038 | Post-Handover | DMA越界大面积踩内核代码段 | **2567轮重启卡死，Linux侧内核代码段大面积被踩**<br>↳ *核心机制*：硬件DMA外设在交接期间地址寄存器配置错误，将数据写到了Linux Kernel代码段导致卡死 |
| **5星 (强烈推荐)** | Case-039 | In-Handover | Sync Code关键同步内存被踩 | **4957轮vppstop，sync code内存被踩**<br>↳ *核心机制*：同步代码缓冲区被异常写入，破坏了后续多核同步原语 |
| **5星 (强烈推荐)** | Case-040 | Post-Handover | CMM统计计数下溢(越界释放) | **cat proc/ax_proc/mem_cmm_info打印remain数据为负数**<br>↳ *核心机制*：内存计数出现负数，绝对证明存在Double Free或跨核未对齐释放 |
| 4星 | Case-041 | All-Stages | CMM内存归一化管理 | **[快启][内存] CMM 内存理论上都要交接，对于CMM 消耗和常电一致**<br>↳ *核心机制*：多方案CMM内存回收与重映射机制设计 |
| 4星 | Case-042 | All-Stages | CMM常电与快启差异消除 | **[快启][内存] CMM 内存理论上都要交接，对于CMM 消耗和常电一致**<br>↳ *核心机制*：CMM池元数据接管机制 |
| 4星 | Case-043 | Pre-Handover | 小核启动期CMM物理内存耗尽 | **Manual TISP模式下RTOS打印cmm内存不足，rtos与Linux交接失败**<br>↳ *核心机制*：TISP模式在RTOS侧预分配过多算子内存，未到交接即内存耗尽 |
| 4星 | Case-044 | Pre-Handover | 暗光大规格Buffer分配失败 | **暗光下重启未交接，RTOS侧：AX_SYS_MemAlloc failed**<br>↳ *核心机制*：暗光下算法自动扩展降噪Buffer大小，导致RTOS端CMM分配失败 |
| 4星 | Case-045 | In-Handover | 物理内存不足导致链路崩溃 | **运行1588轮，AX_VIN_StartPipe失败，CMM内存不足，刷屏heart msg**<br>↳ *核心机制*：CMM不足引发StartPipe报错，小核随后陷入心跳刷屏 |
| 4星 | Case-046 | In-Handover | 双端内存联动耗尽 | **极暗环境下快启失败，rtos侧AX_SYS_MemAlloc failed，linux串口AX_VENC_CreateChn failed**<br>↳ *核心机制*：小核内存分配失败连锁反应导致Linux端VENC创建通道失败 |
| 4星 | Case-047 | Pre-Handover | 双摄拼接AIISP内存超额 | **双摄拼接AIISP CMM内存不够，RTOS侧报错刷屏**<br>↳ *核心机制*：拼接双摄叠加AIISP的CMM物理内存规划超标 |
| 4星 | Case-048 | Pre-Handover | VB视频缓存块泄漏 | **双摄4+2m偶现245轮后rtos一直丢帧不交接，报错拿不到VB**<br>↳ *核心机制*：小核视频缓存池(VB)耗尽，帧流水线停滞无法出帧 |
| 4星 | Case-049 | In-Handover | CMM配额失衡卡死后置模块 | **RTOS上CMM用完导致Linux侧AI Node初始化失败**<br>↳ *核心机制*：RTOS未能精简CMM预分配，留给Linux的余量不足以使能AI |
| 4星 | Case-050 | Pre-Handover | 物理地址为0未校验 | **isp_cmm_alloc获取的phyaddr为0导致VIN断流**<br>↳ *核心机制*：CMM物理内存耗尽返回0，上层驱动未判空直接写寄存器引发硬件故障 |
| 4星 | Case-051 | Pre-Handover | TISP双摄VB池不足 | **快启OS04D10+MIS20S1 TISP模式vb不够**<br>↳ *核心机制*：双摄TISP模式下视频缓存块参数配置偏小 |
| 4星 | Case-052 | Post-Handover | TISP+HSK长跑内存缓慢泄漏 | **快启TISP+HSK 8478轮OOM**<br>↳ *核心机制*：低速硬件同步模式下每轮交接微量泄漏，8000轮后耗尽 |
| 4星 | Case-053 | Post-Handover | 元数据块(Meta Blk)缓慢泄漏 | **2383轮断流，yuv meta blk申请不到（泄漏）**<br>↳ *核心机制*：YUV Meta Blk在交接帧未归还给池子，长测必现断流 |
| 4星 | Case-054 | In-Handover | IVPS中间帧Buffer未归还 | **43轮断流，ivps申请buffer失败**<br>↳ *核心机制*：小核向IVPS派发帧，交接后生命周期管理脱节导致buffer泄漏 |
| 4星 | Case-055 | In-Handover | 静态模型分区动态重回收 | **[快启][内存] 模型分区释放，rtos使用完后Linux app启动前需释放模型分区**<br>↳ *核心机制*：RTOS利用Flash或RAM载入模型后，在Handover时必须解绑还给系统 |

---

## 图像管线稳定性与驱动故障 (共 27 条：5星 9 条，4星 18 条)

### 1. 核心技术机理与故障规律总结
- **硬件 FIFO 溢出与反锁**：小核处理节拍落后或暗光曝光时间拉长，导致 VIN/IVPS 硬件 FIFO Overflow，阻塞后续 Handover 触发。
- **并发竞态与 Use-After-Free**：双摄或 AIISP 快速接管瞬间，中断已开启但软件 Node 结构体未就绪，或者销毁流程与调度线程并发触发 Panic。
- **跨模块复位污染**：NPU 复位操作连带冲掉 Sync Manager 同步寄存器，导致 ISP/VIN 流水线瞬间脱节挂死。
- **环境边界突变脆弱性**：冷启动遮挡摄像头或极暗环境导致出帧严重超时，突破快启握手时间窗口。

### 2. 5星与4星核心工单检索与机制清单

| 推荐指数 | 案例编号 | 影响阶段 | 故障特征与分类 | 故障机理与技术分析要点 |
|---|---|---|---|---|
| **5星 (强烈推荐)** | Case-056 | Post-Handover | AIISP推理任务VNPU超时 | **双摄fastnor交接到linux后，AIISP推理task提交到vnpu1后timeout断流**<br>↳ *核心机制*：双摄AIISP快启交接后NPU算力分配与调度超时导致全局断流 |
| **5星 (强烈推荐)** | Case-057 | Pre-Handover | 硬件FIFO Overflow卡死交接 | **RTOS侧一直在overflow，Linux侧没有成功交接**<br>↳ *核心机制*：小核端处理变慢引发VIN硬件FIFO Overflow，硬件卡住导致握手彻底终止 |
| **5星 (强烈推荐)** | Case-058 | In-Handover | IVPS输入FIFO满刷屏 | **双摄AIISP 867轮takeover失败，RTOS侧IVPS ififo full持续刷屏**<br>↳ *核心机制*：双摄AIISP负载高，小核IVPS消费速度跟不上VIN产生速度导致FIFO爆满 |
| **5星 (强烈推荐)** | Case-059 | Post-Handover | AINR降噪Node触发空指针Panic | **双摄AIISP偶现panic: vin_ainr_node_trigger+0x13c/0x2de**<br>↳ *核心机制*：双摄AIISP接管瞬间AINR节点指针尚未初始化即被中断触发回调引发Kernel Panic |
| **5星 (强烈推荐)** | Case-060 | Post-Handover | AINR线程与销毁并发UAF Panic | **暗光下切换到SDR偶现panic：AINR调度线程与ISP/VIN销毁流程并发**<br>↳ *核心机制*：典型的多线程并发Use-After-Free，销毁ISP/VIN时AINR调度线程未完全退出 |
| **5星 (强烈推荐)** | Case-061 | Post-Handover | 接管后ISP中断未注册Panic | **快启接管后isp irq panic**<br>↳ *核心机制*：Linux重开中断但中断处理上下文结构体未初始化完成即产生硬件中断 |
| **5星 (强烈推荐)** | Case-062 | In-Handover | 暗光初始化时序边界缺陷 | **快启启动前遮住摄像头，必现主核AX_VIN_Init failed, ret=0x80110180**<br>↳ *核心机制*：遮挡摄像头导致曝光极长，出帧慢打破了快启固定的等待窗口，必现初始化失败 |
| **5星 (强烈推荐)** | Case-063 | Post-Handover | 硬件几何校正模块GDC挂死 | **运行后串口打印VPP/GDC stop, need check，IVPS错误码0x800d0101**<br>↳ *核心机制*：GDC/VPP硬件加速器在时钟切换或接管后寄存器状态异常触发硬件Stop保护 |
| **5星 (强烈推荐)** | Case-064 | In-Handover | 跨模块复位踩共享寄存器 | **ITP异常，npu reset把sync manager寄存器清0**<br>↳ *核心机制*：NPU执行Reset时将负责ISP/VIN同步的Sync Manager寄存器冲掉，导致硬件管线瞬间脱节 |
| 4星 | Case-065 | Pre-Handover | 长跑后VIN驱动异常报错 | **64M单2M运行3210次后rtos侧vin报错，未交接**<br>↳ *核心机制*：Sensor/VIN长周期采集后硬件FIFO上溢报错 |
| 4星 | Case-066 | In-Handover | 暗光突变编码超时丢流 | **双摄4+2遮挡进入暗光场景，串口刷屏AX_VENC_GetStream timeout**<br>↳ *核心机制*：暗光曝光延长打乱了VENC出帧节拍，导致获取码流超时 |
| 4星 | Case-067 | Pre-Handover | 小核启动早期断流 | **33轮交接失败，rtos 1.3s后vin断流，无智能和编码帧**<br>↳ *核心机制*：仅运行33轮即在1.3s断流，证明初期参数配置边界有脆弱点 |
| 4星 | Case-068 | Pre-Handover | VIN底层中断丢失导致断流 | **64M快启4257次交接失败，rtos侧proc显示vin断流**<br>↳ *核心机制*：长跑中断控制器未及时清除标志位 |
| 4星 | Case-069 | In-Handover | IVPS发送队列满失败 | **交接卡住，rtos侧报错：ivps_user_send_frame_by_id: send frame failed in grp 0**<br>↳ *核心机制*：小核IVPS向后端传递帧失败，造成流水线阻塞 |
| 4星 | Case-070 | In-Handover | Linux端Grp未启动时序颠倒 | **交接卡住，linux侧报错：ivps_user_get_frame_by_id: grp not start 0**<br>↳ *核心机制*：Linux未启动IVPS Group却尝试取帧，双核状态时序未对齐 |
| 4星 | Case-071 | Post-Handover | ISP Pipe启动失败 | **2135轮takeover后ISP pipe0启动失败**<br>↳ *核心机制*：Linux接管后重新配置ISP寄存器时发生状态机冲突 |
| 4星 | Case-072 | Pre-Handover | Pipe后处理任务创建失败 | **rtos报错start pipe post task failed, ret:0x80110115**<br>↳ *核心机制*：RTOS线程/任务资源不足导致Post Task创建失败 |
| 4星 | Case-073 | Pre-Handover | 双摄拼接VENC送帧失败 | **快启过程中RTOS侧打印stitch VENC SendFrame chn=0 failed**<br>↳ *核心机制*：拼接后图像格式或分块参数不符合VENC规格 |
| 4星 | Case-074 | Pre-Handover | 调度FIFO队列溢出 | **启动过程RTOS侧打印ax_ivps_sched_fifo_mgr.c(64) GRP[0] ififo full**<br>↳ *核心机制*：调度管理模块在启动初期帧到达速率失控 |
| 4星 | Case-075 | Pre-Handover | AINR Node野指针访问 | **烧录后重启偶现panic，vin_ainr_node_trigger访问非法地址**<br>↳ *核心机制*：快启冷启动时AINR内存初始化存在未初始化的脏数据 |
| 4星 | Case-076 | In-Handover | ISP Open驱动状态机冲突 | **快启启动失败AX_ISP_Open failed, ret=0x80010180**<br>↳ *核心机制*：小核尚未释放ISP硬件，Linux侧AX_ISP_Open即抢先占用失败 |
| 4星 | Case-077 | Post-Handover | 快启停止流程状态机反锁 | **QSdemo stop过程提示AX_VIN_StopPipe failed, ret=0x80110180**<br>↳ *核心机制*：应用层退出时反向销毁顺序错误导致底层驱动返回Device Busy |
| 4星 | Case-078 | Pre-Handover | MIPI Lane物理层异常无告警 | **快启出现Lane0异常后无错误中断**<br>↳ *核心机制*：硬件物理信号失步，无错误中断上报导致上层逻辑一直盲等 |
| 4星 | Case-079 | In-Handover | 双核出流状态未解冻 | **rtos侧overflow，Linux侧vin ch0不出流**<br>↳ *核心机制*：小核FIFO溢出后硬件通道未解冻，交接给Linux后Ch0不出流 |
| 4星 | Case-080 | Pre-Handover | ISP底层等待中断超时刷屏 | **烧录后不出流，rtos刷屏：pipe id:0, isp wait failed, ret:0x80110127**<br>↳ *核心机制*：烧录后首次冷启动，Sensor时序未就绪导致小核ISP中断永久等不到 |
| 4星 | Case-081 | Pre-Handover | I2C通信闪断引发断流 | **rtos i2c写失败导致ipc断流**<br>↳ *核心机制*：Sensor配置通过I2C下发时产生NACK，导致未进入出流流程 |
| 4星 | Case-082 | All-Stages | 全链路HSK握手死锁 | **全链路HSK开启下，VIN预配导致VENC异常，整体Overflow**<br>↳ *核心机制*：硬件同步信号(HSK)开启时，由于预配顺序颠倒引发整体溢出 |

---

## 智能算法与模型推理 (共 13 条：5星 4 条，4星 9 条)

### 1. 核心技术机理与故障规律总结
- **模型句柄与权重跨核移交失效**：小核加载模型后，模型分区未在交接前释放，或模型指针/权重句柄移交大核后算子未成功激活。
- **NPU 算子越界与地址未对齐**：双摄拼接叠加 AIISP 时，算子输出物理地址未按 DMA 要求对齐，导致 DMA 溢出踩踏邻近物理内存。
- **长跑推理队列失衡**：压测数千轮后，SKEL 实例创建句柄耗尽，或推理线程与结果取走线程队列不匹配引发 0x80140122 大量丢弃。

### 2. 5星与4星核心工单检索与机制清单

| 推荐指数 | 案例编号 | 影响阶段 | 故障特征与分类 | 故障机理与技术分析要点 |
|---|---|---|---|---|
| **5星 (强烈推荐)** | Case-083 | Post-Handover | 交接后智能算法功能失效 | **快启视频流从头到尾没有检测到人**<br>↳ *核心机制*：视频画面正常流转，但检测算法输出全空，揭示SKEL模型接管后算子未重新激活 |
| **5星 (强烈推荐)** | Case-084 | Post-Handover | SKEL获取推理结果超时刷屏 | **Linux串口刷屏AX_SKEL_GetResult(grp0,chn2) failed, err=0x80140122 丢失检测结果**<br>↳ *核心机制*：算法推理线程与结果取走线程队列不匹配，出现0x80140122大量丢弃 |
| **5星 (强烈推荐)** | Case-085 | Post-Handover | NPU算子执行越界踩内存 | **双摄拼接AIISP NPU踩内存**<br>↳ *核心机制*：NPU算子输出物理地址对齐未对齐引发DMA溢出，踩踏邻近物理页 |
| **5星 (强烈推荐)** | Case-086 | Pre-Handover | 模型分区读取失败引发Panic | **烧录后重启卡住并panic，rtos侧模型分区加载失败**<br>↳ *核心机制*：模型分区偏移或坏块导致RTOS读取损坏数据，解包引发系统崩溃 |
| 4星 | Case-087 | Post-Handover | SKEL实例创建失败(资源耗尽) | **64M快启压测出现AX_SKEL_Create error, ret:0x80140129**<br>↳ *核心机制*：64M极限内存下Linux端SKEL创建句柄返回资源不足错误 |
| 4星 | Case-088 | Pre-Handover | RTOS端SKEL实例创建失败 | **1021轮交接失败，rtos skel创建失败**<br>↳ *核心机制*：小核在千轮压测后无法创建轻量级算法上下文 |
| 4星 | Case-089 | In-Handover | 模型文件跨核解析校验失败 | **295轮交接失败，Linux SKEL没有出帧，模型解析报错**<br>↳ *核心机制*：模型头信息在跨核交接时校验不一致导致无法出帧 |
| 4星 | Case-090 | In-Handover | PCD参数校验阻断交接 | **Pcd创建失败导致Rtos不继续交接，skel传入值无效**<br>↳ *核心机制*：PCD算法模块参数非法，导致小核退出交接流程 |
| 4星 | Case-091 | Pre-Handover | 模型文件加载并发竞态 | **AIISP偶现网络模型加载失败**<br>↳ *核心机制*：从Flash读取模型与NPU载入时序竞态偶现损坏 |
| 4星 | Case-092 | Pre-Handover | AIISP轻量模型小核加载失败 | **双摄拼接AIISP模型加载失败，RTOS侧：AX_AIISP_ModelLoad pipe[0] MILD failed**<br>↳ *核心机制*：MILD轻量模型在RTOS加载时校验内存限制超限 |
| 4星 | Case-093 | In-Handover | 模型内存释放越界/错误 | **重启串口报错AX_SYS_ModelMemRelease pipe[0] failed, ret=0xffffffff**<br>↳ *核心机制*：ModelMemRelease返回-1，句柄已失效导致泄漏 |
| 4星 | Case-094 | In-Handover | 模型加载失败级联ISP报错 | **重启报错AX_ISP_Open failed, ret=0x80010180，syslog打印Load axmodel failed**<br>↳ *核心机制*：NPU模型加载失败直接导致后续ISP Open无法正常进行 |
| 4星 | Case-095 | In-Handover | 客户人形算法使能后启动挂死 | **【行业客户】打开人形后快启版本启动失败**<br>↳ *核心机制*：客户工程打开人形检测后算力与内存突破阈值导致交接超时 |

---

## 系统引导与启动性能 (共 12 条：5星 4 条，4星 8 条)

### 1. 核心技术机理与故障规律总结
- **启动指标劣化回归**：代码迭代引入额外的跨核同步等待或 IFE 前端计算排队，导致首帧时间突破 100ms/交接突破 100ms 红线。
- **长跑循环异常跌入 Recovery**：压测几千轮后因未清空 BootCount 或 Flash 分区静默损坏，系统误判为启动失败跌入 Recovery 模式。
- **全内置裁剪缺失驱动**：Lite 极限裁剪工程遗漏将 ASoC Machine 驱动强配为内置，导致声卡节点缺失。

### 2. 5星与4星核心工单检索与机制清单

| 推荐指数 | 案例编号 | 影响阶段 | 故障特征与分类 | 故障机理与技术分析要点 |
|---|---|---|---|---|
| **5星 (强烈推荐)** | Case-096 | All-Stages | 快启各阶段时延劣化严重超标 | **性能测试RTOS首帧503ms，Linux交接233ms，不满足首帧Raw 100ms及交接100ms指标**<br>↳ *核心机制*：快启核心指标分解典型：首帧Raw耗时503ms远超100ms目标，交接耗时233ms超出指标 |
| **5星 (强烈推荐)** | Case-097 | In-Handover | 暗光长曝光拖垮交接性能 | **暗光下交接耗时过长，交接比demo版慢1秒以上，视频断档丢帧**<br>↳ *核心机制*：暗光下曝光周期拉长，双核同步机制同步阻塞，交接时间被拖长1s以上导致肉眼断流 |
| **5星 (强烈推荐)** | Case-098 | Post-Handover | 压测后镜像或BootCount触发Recovery | **压测循环后板子异常进入recovery模式**<br>↳ *核心机制*：快启压测几千次后由于重启标志未清空或Flash分区校验失败，异常跌入Recovery模式 |
| **5星 (强烈推荐)** | Case-099 | Post-Handover | 全内置内核裁剪遗漏ALSA Machine驱动导致声卡节点缺失 | **【DDR64_lite】【mis20s1】开启音频采集/播报功能，快启后linux侧串口音频模块报错AX_AI_EnableDev failed, ret 0x80200215**<br>↳ *核心机制*：全内置内核裁剪未打包.ko且simple-card编译为=m导致声卡未创建 |
| 4星 | Case-100 | All-Stages | 代码合入引入启动时序回归 | **快启启动及首帧时间回退14%~19%**<br>↳ *核心机制*：驱动提交引入额外的同步延时导致首帧时间出现15%+回退 |
| 4星 | Case-101 | Pre-Handover | IFE前端计算耗时异常 | **ife耗时异常导致快启性能劣化**<br>↳ *核心机制*：前端图像增强模块计算排队，影响了整体首帧时间 |
| 4星 | Case-102 | Pre-Handover | AB分区/Recovery回退机制失效 | **破坏镜像后无法自动进入recovery模式**<br>↳ *核心机制*：快启Bootloader安全防砖机制失效，镜像损坏未触发自动恢复 |
| 4星 | Case-103 | Pre-Handover | 双Flash片选与启动引脚适配 | **【行业客户】双nor flash 8M flash硬件改板后烧录后起不来**<br>↳ *核心机制*：客户定制硬件改板，双8M Flash硬件拓扑与Bootloader时钟/CS不匹配 |
| 4星 | Case-104 | Pre-Handover | RootFS解压缩内存不足破坏 | **系统启动时gzip解压rootfs失败或probe失败**<br>↳ *核心机制*：快启预留内核解压内存过小，解压缓冲区踩踏损坏 |
| 4星 | Case-105 | In-Handover | 控制台串口被双核占用卡死 | **烧录后重启只打印启动日志，无法操作**<br>↳ *核心机制*：UART串口驱动双核交接时波特率或时钟门控被关闭导致无响应 |
| 4星 | Case-106 | Pre-Handover | Reboot标志位丢失未触发快启 | **reboot文件创建后无法进入快启流程，手动重启后reboot文件消失**<br>↳ *核心机制*：非易失性寄存器或标志文件在卸载文件系统时被清空 |
| 4星 | Case-107 | Pre-Handover | NAND驱动与UBIFS挂载失败Panic | **烧录fastnand_V2.7.0镜像无法正常启动，panic: VFS: Unable to mount root fs**<br>↳ *核心机制*：FastNAND分区布局与Bootargs传参不匹配 |

---

## 外设驱动与环境功能 (共 6 条：5星 1 条，4星 5 条)

### 1. 核心技术机理与故障规律总结
- **日志海森堡现象（Heisenbug）**：关闭串口日志或调低 log_level 后，少了打印延时的掩护，双核隐蔽的时序竞争立刻爆发并挂死。
- **外设双核裁决冲突**：极暗场景下补光灯 GPIO 使能时序过迟，或夜视 IRCUT 切换状态机在双核判定上互打架导致电机震荡。

### 2. 5星与4星核心工单检索与机制清单

| 推荐指数 | 案例编号 | 影响阶段 | 故障特征与分类 | 故障机理与技术分析要点 |
|---|---|---|---|---|
| **5星 (强烈推荐)** | Case-108 | All-Stages | 关闭日志改变时序引发时序竞争 | **配置rtos_log_level或关闭串口log后，板端重启失败或qsdemo无法启动**<br>↳ *核心机制*：经典海森堡Bug：开启串口Log时延时充当了保护，关闭串口Log后双核时序竞争立刻爆发挂死 |
| 4星 | Case-109 | Post-Handover | 音频编码共享帧创建失败 | **【mis20s1】audio_enable使能后，重启设备，串口提示：Aenc: shframe_writer_create failed，rtsp码流没有声音**<br>↳ *核心机制*：音频共享环形缓冲区创建失败导致无声 |
| 4星 | Case-110 | In-Handover | I2C通信超时阻塞 | **HDR模式报错hal_i2c_read: Failed to read reg: Connection timed out**<br>↳ *核心机制*：HDR模式下高频读写I2C导致总线死锁超时 |
| 4星 | Case-111 | Post-Handover | 异常下电/重启导致文件系统损坏 | **板端存储exFAT-fs invalid boot record signature**<br>↳ *核心机制*：快启测试中频繁非正常下电损坏TF卡引导扇区 |
| 4星 | Case-112 | Pre-Handover | 硬件补光灯GPIO/PWM使能时序 | **极暗环境下快启无法点亮补光灯**<br>↳ *核心机制*：小核在极暗检测到出图前未及时拉高补光灯GPIO |
| 4星 | Case-113 | In-Handover | 红外IRCUT切换双核判定打架 | **低照下快启Linux启动偶发来回切换红外**<br>↳ *核心机制*：RTOS切夜视与Linux启动时IRCUT默认状态冲突导致电机反复震荡 |

---
