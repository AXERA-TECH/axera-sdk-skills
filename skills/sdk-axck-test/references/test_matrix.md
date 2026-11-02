# SDK-AXCK-TEST 全量验证用例与硬件门限矩阵

## 一、双驱动模式架构说明
- **HTTP RPC Driver (`--driver=http`)**：直接面向板端 `axck_service` 内置 HTTP (thttpd/CGI) 服务，单步时延 30~80ms，返回强类型 JSON 数据与确定性业务码。配合 HTTP/1.0 穿透机制避开企业局域网软路由 DPI 劫持。推荐作为自动化回归、CI 流水线和高频压测的首选驱动。
- **UART Menu Driver (`--driver=uart`)**：通过串口交互驱动板端 `axck_test` 菜单层级，配合 Telnet 带外并发巡检。用于无网络环境、底层固件调试与交互式现场排查。

---

## 二、带外硬件探针门限矩阵 (Hardware Observable Gates)

| 序号 | 硬件子节点 | 探测方式 | 判定指标与断言表达式 | 门限阈值要求 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **P01** | `/proc/ax_proc/ivps` | Telnet 文本正则 | Chn0 宽度与高度几何尺寸匹配 | 单摄 `2880 1620` / 双摄 `1920 1080` & `2560 1440` | 校验 IVPS 图像处理管线几何输出自适应 |
| **P02** | `/proc/ax_proc/ivps` | Telnet 文本正则 | Chn0 进出流帧率比稳定 | `25.0 : 25.0` 或 `30.0 : 30.0` | 校验图像管线无掉帧卡顿 |
| **P03** | `/proc/ax_proc/venc` | Telnet 文本正则 | Chn0 编码协议与尺寸 | `H265 Main` 匹配主摄基线 | 主码流硬件编码器规格校验 |
| **P04** | `/proc/ax_proc/venc` | Telnet 文本正则 | Chn1 编码协议与尺寸 | `H264 Main 960x540` 或 `1280x720` | 子码流硬件编码器规格校验 |
| **P05** | `/proc/ax_proc/ai` | Telnet 文本正则 | 音频驱动采集状态与增益 | `ai_volume >= 0.0` | 校验音频驱动初始化正常 |
| **P06** | `/proc/ax_proc/mem_cmm_info` | Telnet 双轨监控 | CMM 连续物理内存水位比率 | 单摄 `< 90.0%` / 双摄 `<= 99.0%` | 预防视频驱动与 DMA 物理内存耗尽 OOM |
| **P07** | `/proc/meminfo` | Telnet 双轨监控 | Linux OS 可用内存 `MemAvailable` | `> 5.0 MB` | 校验操作系统常规堆栈内存安全 |
| **P08** | `/proc/<pid>/status` | Telnet 双轨监控 | 守护进程物理常驻页 `VmRSS` | `< 25.0 MB` | 监控 `axck_service` 进程堆内存 |

---

## 三、HTTP RPC 领域原子 API 用例矩阵 (Domain Atomic Cases - 共 29 项)

| 序号 | 领域模块 | API/命令 | 参数说明 | 验证与断言依据 | 典型耗时 | 门限判定 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **A01** | Device | `device.get_status` | 无 | 校验 HTTP 200 与业务状态码 `code == 0` | 30~40ms | 必须 PASS |
| **A02** | Device | `device.get_status` | 前摄状态断言 | 校验 `front_status == 1`（前摄硬件在线） | 1ms | 必须 PASS |
| **A03** | Device | `device.get_status` | TF卡状态断言 | 校验 `sdcard == 1`（TF存储介质在线） | 1ms | 必须 PASS |
| **A04** | Device | `device.get_status` | ACC点火状态断言 | 校验 `acc == 1`（车机ACC处于工作模式） | 1ms | 必须 PASS |
| **A05** | Storage | `storage.get_status` | 挂载状态 | 校验 `sd_status == 0`（存储卡挂载就绪无报错） | 30~40ms | 必须 PASS |
| **A06** | Storage | `storage.get_status` | 剩余容量 | 校验 `free_size > 1.0 GB` 确保录像空间充裕 | 1ms | 必须 PASS |
| **A07** | Audio | `audio.set_mute` | `val=1` | 校验 HTTP 200 及带外 `/proc/ax_proc/ai` 驱动硬件静音切断 | 40~60ms | 必须 PASS |
| **A08** | Audio | `audio.get_mute` | 无 | 校验回读静音标志 `mute == 1` | 30~40ms | 必须 PASS |
| **A09** | Audio | `audio.set_mute` | `val=0` | 校验 HTTP 200 及音频采集驱动恢复通畅 | 30~40ms | 必须 PASS |
| **A10** | Audio | `audio.get_mute` | 无 | 校验回读解静音标志 `mute == 0` | 30~40ms | 必须 PASS |
| **A11** | Audio | `audio.set_volume` | `val=85.0` | 校验 HTTP 200 动态调整音量为 85% | 30~40ms | 必须 PASS |
| **A12** | Audio | `audio.get_volume` | 无 | 校验音量回读数值合法断言 | 30~40ms | 必须 PASS |
| **A13** | Audio | `audio.set_volume` | `val=70.0` | 校验音量平滑复原至基线 70% | 30~40ms | 必须 PASS |
| **A14** | Stream | `stream.set_mirror` | `cam=0, val=1` | 校验水平镜像生效 `mirror == 1` | 30~40ms | 必须 PASS |
| **A15** | Stream | `stream.set_mirror` | `cam=0, val=0` | 校验水平镜像复原 `mirror == 0` | 30~40ms | 必须 PASS |
| **A16** | Stream | `stream.set_flip` | `cam=0, val=1` | 校验垂直翻转生效 `flip == 1` | 30~40ms | 必须 PASS |
| **A17** | Stream | `stream.set_flip` | `cam=0, val=0` | 校验垂直翻转复原 `flip == 0` | 30~40ms | 必须 PASS |
| **A18** | Stream | `stream.set_fps` | 动态调节帧率 | 单摄 25fps / 双摄 20fps 动态下发 | 30~50ms | 必须 PASS |
| **A19** | Stream | `stream.get_fps` | 回读帧率 | 校验实时帧率与目标下发值精确对齐 | 30~40ms | 必须 PASS |
| **A20** | Stream | `stream.set_fps` | 恢复基准帧率 | 单摄 30fps / 双摄 25fps 平滑复原 | 30~50ms | 必须 PASS |
| **A21** | Stream | `stream.set_resolution` | 动态降分辨率 | 单摄 2560x1440 / 双摄 1280x720 动态重构 | 100~200ms | 必须 PASS |
| **A22** | Stream | `stream.set_resolution` | 中间级分辨率 | 单摄 1920x1080 切换断言（双摄自适应跳过或执行） | 100~200ms | 必须 PASS |
| **A23** | Stream | `stream.set_resolution` | 恢复基准分辨率 | 单摄 2880x1620 / 双摄 1920x1080 硬件复原 | 100~200ms | 必须 PASS |
| **A24** | Stream | `stream.set_record_time`| `sec=60` | 校验动态配置普通录像分片时长为 60 秒 | 30~40ms | 必须 PASS |
| **A25** | RTSP | `rtsp.start` | `cam=0` | 校验启动 RTSP 服务，板端 `8554` 端口进入 `LISTEN` | 800~1100ms | 必须 PASS |
| **A26** | RTSP | `rtsp.stop` | `cam=0` | 校验停止 RTSP 服务，`8554` 端口优雅释放 | 40~60ms | 必须 PASS |
| **A27** | DTCF | `dtcf.get_file_count` | `file_type=0` | 校验 DTCF 数据库媒体文件索引总数统计 | 30~40ms | 必须 PASS |
| **A28** | Media | `media.switch_prev` | `mode=1` | 校验无屏架构下前端预览切换防御机制 | 30~40ms | 必须 PASS |
| **A29** | AOV | `aov.control` | `cmd=stop` | 校验常规工作模式下对非法/未启动 AOV 状态机的受控保护 | 30~40ms | 必须 PASS |

---

## 四、全链路业务场景流水线矩阵 (Scenario Pipelines)

| 序号 | 场景名称 | 包含步骤 | 执行动作与验证门限 | 典型耗时 | 门限要求 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **S01** | `Smoke_Test_Pipeline` | 5 步 | 综合状态自检 -> 存储自检 -> 开启录像 -> 动态抓拍 -> 停止录像 | ~3.0s | 全部步骤必须 PASS |
| **S02** | `Burst_Capture_Pipeline` | 6 步 | 存储检查 -> 开启录像 -> 突发连拍 3 张 (间隔0.5s) -> 停止录像 | ~2.5s | 全部步骤必须 PASS |
| **S03** | `Continuous_Record_Pipeline` | 5 步 | 开录 -> 录像保持 -> 触发紧急加锁录像 -> 抓拍 -> 安全停录 | ~8.0s | 全部步骤必须 PASS |

---

## 五、高频并发压力与时延浸泡矩阵 (Stress & Soak)

| 序号 | 压测用例 | 并发配置 | 目标接口 | 门限要求 | 达标实测值 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ST01** | 高频状态查询并发浸泡 | 3 并发线程 / 30 次请求 | `device.get_status` | 1. 零失败 (Zero Failure)<br>2. 吞吐 QPS $\ge 20\text{ req/s}$<br>3. P99 时延 $< 200\text{ ms}$ | 1. 0 Failure<br>2. QPS: 55.88 req/s<br>3. P99: 67.34 ms |
| **ST02** | 双摄 AOV 休眠唤醒与录像落盘浸泡压测 | 60s 持续休眠唤醒浸泡 | `aov.control` + 带外内核监控 | 1. HTTP start/stop 双向响应正常<br>2. 内核捕获 PM 休眠唤醒序列与网卡 Link Up 自愈<br>3. AOV 录像分片文件落盘生成 (`AOV*.mp4` 20MB)<br>4. 退出 AOV 后媒体抓拍功能自愈恢复 | 1. HTTP start/stop 200 OK<br>2. 捕获 Timer32 唤醒与 PHY 恢复<br>3. Cam1 (OS04D10) 成功落盘 20MB MP4<br>4. 拍照自愈通过 |

---

## 六、VENC 专项编解码与稳态质量矩阵 (VENC Dedicated Suite)

针对双摄（前摄 OS04D10 2.5K + 后摄 XS9950 1080P）共 4 路编码通道（Chn0: H.265 主流, Chn1: H.264 子流, Chn2: H.264 主流, Chn3: H.264 子流），严格区分断流切换与非断流切换：

| 序号 | 类别 | 用例名称 | 测试操作与方法 | 硬件断言与质量门限 | 典型耗时 | 门限要求 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **C01** | 非断流 | 动态降频变频 | 调用 `stream.set_fps(0, 20.0)` | 1. HTTP 200 OK<br>2. 变频后采样 `OutFPS` 收敛在 15.0~25.0 fps | ~3.1s | 必须 PASS |
| **C02** | 非断流 | 降频稳态出流断言 | 持续嗅探 `/proc/ax_proc/venc` | 1. 出流不中断 (`d_send > 0`)<br>2. `ErrorCnt == 0`<br>3. `abs(EncSuc - Send) <= 2`<br>4. `DropBsCnt <= 1` | ~1.1s | 必须 PASS |
| **C03** | 非断流 | 动态恢复基准帧率 | 调用 `stream.set_fps(0, 25.0)` | 1. HTTP 200 OK<br>2. 恢复后采样 `OutFPS` 收敛在 20.0~28.0 fps | ~3.1s | 必须 PASS |
| **C04** | 非断流 | 水平镜像切换 | 调用 `stream.set_mirror(0, True)` 随后复原 | 1. HTTP 200 OK<br>2. `/proc/ax_proc/ivps` 对应 Filter 状态同步更新<br>3. 编码通道出流持续不中断 | ~150ms | 必须 PASS |
| **C05** | 非断流 | 垂直翻转切换 | 调用 `stream.set_flip(0, True)` 随后复原 | 1. HTTP 200 OK<br>2. `/proc/ax_proc/ivps` 对应 Filter 状态同步更新<br>3. 编码通道出流持续不中断 | ~150ms | 必须 PASS |
| **C06** | 非断流 | 双摄并发出流健康 | 采样 Chn0~Chn3 四路编码通道 | 1. 四路全部持续发流 (`d_send > 0`)<br>2. 全部通道 `ErrorCnt == 0` | ~1.1s | 必须 PASS |
| **D01** | 断流 | 前摄切 H.264 (管线重建) | 调用 `stream.set_venc_type(0, 0, h264)` | 1. HTTP 200 OK (耗时 ~9-10s)<br>2. PPL 重构完成，Chn0 编码格式变为 `H.264` | ~9.5s | 必须 PASS |
| **D02** | 断流 | 切 H.264 后出流自愈 | 延时等待并采样 `/proc/ax_proc/venc` | 1. Chn0 重新捕获帧并出流 (`d_send > 0`)<br>2. `ErrorCnt == 0`<br>3. 格式与尺寸对齐 (2560x1440) | ~1.2s | 必须 PASS |
| **D03** | 断流 | 前摄切回 H.265 (管线重建) | 调用 `stream.set_venc_type(0, 0, h265)` | 1. HTTP 200 OK (耗时 ~9-10s)<br>2. PPL 重构完成，Chn0 格式恢复为 `H.265` | ~9.5s | 必须 PASS |
| **D04** | 断流 | 切回 H.265 后出流自愈 | 延时等待并采样 `/proc/ax_proc/venc` | 1. Chn0 重新捕获帧并出流 (`d_send > 0`)<br>2. `ErrorCnt == 0`<br>3. 格式为 H.265，尺寸保持 2560x1440 | ~1.2s | 必须 PASS |
| **M01** | 稳态 | 4 通道计数器零丢包断言 | 3 秒双采样 Chn0~Chn3 全量计数器 | 1. 4 路通道采样周期内 `ErrorCnt` 增量严格为 0<br>2. `DropBsCnt` 增量严格为 0<br>3. `EncSucCnt` 与 `Send2EncCnt` 紧致对齐 (容差 <= 8) | ~3.1s | 必须 PASS |
| **M02** | 稳态 | 4 通道帧率与码率稳定性 | 采样 Chn0~Chn3 `RecvFPS` 与 `OutFPS` | 1. 4 路通道 `abs(RecvFPS - OutFPS) <= 2.0 fps`<br>2. 帧率达到设计指标 (25fps 主流 / 25fps 子流) | ~1.1s | 必须 PASS |

---

## 七、UART 经典交互式菜单用例矩阵 (Legacy Menu)

| 序号 | 步骤名称 | 驱动操作 | 验证与断言依据 | 判定要求 |
| :--- | :--- | :--- | :--- | :--- |
| **0** | **进入 Media 菜单** | 发送 `1\n` | 捕获 `Media api options:` | 必须 PASS |
| **1** | **前后摄开流/关流** | 发送 `1\n` -> 延时 1.5s -> 发送 `1\n` | 检查开流/关流返回状态码与状态回显 | 必须 PASS |
| **2** | **获取实时帧率** | 发送 `2\n` | 正则捕获 `fps: ([0-9\.]+)`，断言 `fps > 0` | 必须 PASS |
| **3** | **JPEG 抓拍验证** | 发送 `28\n` | 检查 JENC 抓拍日志与落盘路径 `/mnt/tfcard/Photo/F/` | 必须 PASS |
| **4** | **MP4 录像起停** | 发送 `9\n` -> 延时 2.5s -> 发送 `10\n` | 检查 DTCF / MP4 封包事件及停止响应 | 必须 PASS |
| **5** | **多分辨率动态切换** | 发送 `7\n` -> 选 `0`/`1`/`2` | 断言编码器无崩溃，捕获图片分辨率匹配 | 推荐 PASS |
| **6** | **退出 Media 菜单** | 发送 `0\n` | 捕获主菜单 `Options:` | 必须 PASS |
| **7** | **Storage 状态校验** | 进入 Storage (`2\n`) -> 查状态 -> 查容量 -> 退出 | 检查 TF 卡挂载状态与容量数值 | 必须 PASS |
| **8** | **DTCF 目录树校验** | 进入 DTCF (`3\n`) -> Dump DTCF (`1\n`) -> 退出 | 确认 DTCF 节点导出成功 | 必须 PASS |
| **9** | **Device 状态与信息**| 进入 Device (`4\n`) -> 查状态 -> 查信息 -> 退出 | 检查固件版本、SN 与各子系统正常 | 必须 PASS |
| **10**| **防退出自愈机制** | 主菜单状态防误退检测，Shell 提示符捕获重起 | 自动拉起 `./axck_test` 并回到主菜单 | 推荐 PASS |
