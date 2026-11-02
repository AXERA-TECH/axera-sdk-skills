# 板端环境避坑与测试高可靠性原则

在对 AX615 / AXERA 单板执行 `axck_test` 时，由于单板采用 NOR Flash 或资源受限嵌入式环境，必须严格遵循以下避坑指南：

## 1. 真实菜单退出键与主菜单退出死锁
- **现象**：测试在执行完某子菜单（如 Media）后，后续用例全部报错 `not found`（如 `-bin/sh: 3: not found`），串口回显进入 Linux Shell。
- **根因**：
  1. `axck_test` 中所有子菜单（Media, Storage, Dtcf, Device）返回上级主菜单的选项是 **`0. Back.`**，而不是 `q`！
  2. 主菜单（Options）的 `0` 对应 **`0. Exit test.`**（退出 axck_test 进程至系统 Shell）。
  3. 如果在退出子菜单时连发了两次 `0`，或者因异步刷新时延在已返回主菜单时误发了 `0`，会导致 `axck_test` 直接退出，后续菜单编号被当做 Shell 命令执行。
- **对策**：
  - 驱动状态机维护当前菜单层级，退出子菜单时仅允许发送单个 `0` 并等待主菜单关键字 `Options:`。
  - `ensure_in_main_menu` 增加防重入机制：若当前已处于 `main`，绝对禁止再次发送 `0`。
  - 增加 Shell 级自愈：检测到命令行提示符（如 `/opt/bin #`）时，自动执行 `cd /opt/bin && ./axck_test -t 2 -l 2` 恢复主菜单。

## 2. OxideTerm MCP 串口数据结构与 Buffer 特性
- **现象**：`read_lines()` 报错 `'str' object has no attribute 'get'`，或者 `tail=True` 捕获到大量尾部空行而丢失菜单选项。
- **根因**：
  1. OxideTerm MCP 的 `terminals_read` 返回的数据结构中，`lines` 直接是字符串数组（`[str, ...]`），而不是包含 `{"text": ...}` 的字典。
  2. 虚拟终端设置了较大的缓冲区（如 40+ 行），`tail=True` 会获取终端窗口底部的空填充行；而 `axck_test` 每次 `system("clear")` 重绘时菜单是打印在顶部。
- **对策**：
  - 驱动中 `lines = [line if isinstance(line, str) else line.get("text", "") for line in lines]` 保证兼容性。
  - 默认采用 `tail=False` 并读取合适行数（如 45 行），确保完整捕获屏幕顶部的菜单标题和选项。

## 3. 网络与 NFS 驱动加载依赖序（关键）
- **现象**：直接挂载 NFS 报错 `No such device` 或串口完全挂死在等待 NFS 响应状态（`nfs: server <NFS_IP> not responding`）。
- **根因**：
  1. AX615 板端网卡驱动与 NFS 协议栈为模块化设计（位于 `/soc/ko/`），系统冷启动后默认未加载 RPC/NFS 模块。
  2. 仅手动 `insmod /soc/ko/nfs.ko` 缺少板级网络调优脚本前置配置，容易导致网络吞吐抖动与挂载超时。
- **对策**：在单板开机或重启后，必须执行标准脚本加载序列：
  ```sh
  net_load.sh
  nfs_load.sh
  mkdir -p /tmp/test_archive
  mount -t nfs -o nolock,soft,timeo=30,tcp <NFS_SERVER>:<REMOTE_PATH> /tmp/test_archive
  ```

## 4. NOR Flash 空间不足触发 syslogd 卡死
- **现象**：板端执行几条命令后串口突然卡死无响应，或者日志输出停滞。
- **根因**：单板 `/var/log` 挂载在 RAM 或空间受限分区，大量调试日志写满存储导致 `syslogd` 同步写磁盘阻塞，引发全系统 D 状态卡死。
- **对策**：在测试前执行预检与清理：
  ```sh
  rm -rf /var/log/* /tmp/*
  ```

## 5. 避免残留进程资源争抢
- **现象**：`axck_test` 提示 `Init failed` 或 `Resource busy`（如 0x80070216 或 0x80050004）。
- **根因**：旧的 `axck_service` 或前一次崩溃的 `axck_test` 仍在后台运行，独占了 Sensor、VIN、ISP 或 VENC 硬件通道。
- **对策**：启动测试前强制复位：
  ```sh
  killall -9 axck_test axck_service
  ```

## 6. 高频控制台清屏对抗与延时等待
- **现象**：驱动获取菜单时经常丢失匹配文本或指令无响应。
- **根因**：`axck_test` 在每次操作后有内置的延时机制（如 `msSleep(2000)`），之后调用 `system("clear")` 重绘界面。如果上位机发送指令过快，菜单重绘尚未就绪，输入会被丢弃或打乱。
- **对策**：
  - 每次发送功能指令后，显式等待至少 2.0~2.5 秒以匹配板端清屏周期。
  - 剥离 ANSI 颜色与控制字符后再进行关键字判定。

## 7. 动态分辨率切换与抓拍落地验证
- **现象**：抓拍成功但在板端找不到文件，或者分辨率没有生效。
- **根因**：
  - 抓拍选项是 Media 菜单下的 `28. Capture image.`，图像保存路径受 DTCF 规范控制，前摄默认路径为 `/mnt/tfcard/Photo/F/PH<timestamp>-<seq>F.jpg`。
  - 切换分辨率（选项 `7. Update front main stream resolution`）需选择子选项（`0: 2560x1440`, `1: 1920x1080`, `2: 1280x720`），切换后需留足 2 秒使编码通道重置完成，再触发抓拍。
- **对策**：抓图测试前先清空 `/mnt/tfcard/Photo/F/*`，抓拍后通过 NFS/nas-sync 同步至服务器本地，并使用 PIL/OpenCV 读取图像 Header 校验真实分辨率与完整性。

## 8. AOV 低功耗休眠模式下的网络与交互特性
- **现象**：在 `Media api options` 中执行 `Start AOV`（如 Option 14）后，终端会持续高频刷屏 `System enter SLEEP.` 和 `System WAKEUP by type:0.`，同时 Telnet/SSH/HTTP 网络连接完全超时失效。
- **根因**：AX615 在 AOV (Always-On Video) 低功耗模式下，CPU 和外部高速外设进入休眠唤醒循环，以太网控制器（MAC/PHY）断电/挂起，TCP/IP 协议栈不可用，因此在此期间无法通过 Telnet/网络访问板端。
- **双通道解耦架构与退出机制**：
  - **业务控制通道 (HTTP)**：在板端清醒窗口或利用指数退避重试（Backoff Retry）下发 `aov_ctrl?cmd=stop` 退出 AOV。
  - **带外监控通道 (串口 UART / Telnet)**：硬件永不断线，监听内核 `PM: suspend entry` / `PM: suspend exit` 与以太网 PHY `Link is Up - 100Mbps/Full` 恢复日志。
  - 退出 AOV 后，系统停止 AOV 线程并恢复常规推流，TCP/IP 协议栈完全自愈。
- **自动化测试规范**：在常规自动化流媒体、编解码、分辨率切换等测试套件中，应避免引入快速循环休眠的 AOV 测试项，以免干扰以太网通信与 Inspector 状态采集；如需测试 AOV，必须将其设计为独立闭环用例，且保证休眠唤醒测试周期满足 MP4 分片打包要求（例如 60s 以上）。

## 9. 多摄/双摄 DTCF 数据库与目录映射隔离
- **现象**：在单摄切换为双摄（如 OS04D10 + XS9950）后，`AXCK_DTCF_Load` 报 `project not match`，或者后摄录像与抓拍无法生成。
- **根因**：
  1. TF 卡内历史 `file.db` 记录的项目标识（如 `ax620q_single`）与新工程（如 `ax615d_cust_dual`）冲突，导致 DTCF 拒绝挂载并报警。
  2. 板端 `/opt/bin/res/config/dtcf_config.json` 默认仅配置了 `CamId: 0`（`MainFolder: "F"`），未配置 `CamId: 1`（`MainFolder: "R"`），后摄抓拍与录像无目标落盘目录。
- **对策**：
  - 切换多摄工程时，必须同步更新 `dtcf_config.json` 确保包含 `CamId: 0 -> F` 与 `CamId: 1 -> R` 完整映射。
  - 清理旧数据库 `rm -f /mnt/tfcard/file.db*` 并调用 `storage.mount()` 触发系统自愈，重新建立规范的 `Photo/F`、`Photo/R`、`Normal/F`、`Normal/R`、`AOV/F`、`AOV/R` 树形结构。

## 10. 外接 AHD 芯片 (XS9950) 与 AOV 休眠唤醒流控制差异
- **现象**：在双摄 AOV 休眠唤醒压测中，前摄 OS04D10 唤醒后出流与落盘正常，但后摄 XS9950 唤醒后出现无图像或无法触发 AOV 录像落盘。
- **根因**：
  - OS04D10 为原生 MIPI RAW 传感器，支持寄存器级低功耗模式与时钟变频。
  - XS9950 为模拟高清（AHD）解码芯片，休眠时必须显式操作 D-PHY 控制寄存器（`0x4030`）和 MIPI 控制寄存器（`0x0e08`, `0x5004~0x5007`）进行 Stream Off / Stream On 软件复位与时钟恢复，否则唤醒后前端芯片未恢复发流，导致 VI/ISP 无法捕获新帧。
- **对策**：在 Sensor 驱动层实现 `.pfn_sensor_sleep_wakeup` 回调，休眠时关闭 D-PHY 时钟与 MIPI 传输，唤醒时开启 D-PHY 并对 MIPI 控制器触发脉冲复位。

## 11. TF 卡热拔插与 MMC 控制器复位
- **现象**：TF 卡格式化或长时间高负荷写入时，内核偶发报错 `mmc0: Timeout waiting for hardware cmd interrupt`，导致 `/dev/mmcblk0` 掉盘或出现 `FAT-fs (mmcblk0): bread failed` / `Device or resource busy`。
- **根因**：SDHCI 控制器中断超时或总线状态失步，导致 MMC 块设备进入离线状态。
- **对策**：
  - 无需整机冷启动，可通过 sysfs 对 SDHCI 控制器执行解绑并重新绑定热重置：
    ```sh
    umount -l /mnt/tfcard
    echo 1b50000.sdhci > /sys/bus/platform/drivers/sdhci-axera/unbind
    echo 1b50000.sdhci > /sys/bus/platform/drivers/sdhci-axera/bind
    echo 1 > /sys/class/mmc_host/mmc0/detect
    mount -t vfat /dev/mmcblk0 /mnt/tfcard
    ```

## 12. AOV 休眠自动自退出与 pthread_join 自身死锁陷阱
- **现象**：在 `app_config.json` 中配置了 `sleep_count` 期望休眠指定次数后自动退出 AOV 模式，但达到计数后系统 hang 死或 Sensor 帧率依然停留在 1fps，MP4 录像无法封包落盘。
- **根因**：
  - 若在 `AOVTrd` 循环中仅执行 `break` 退出循环，未调用 `AXCK_PPL_StopAOV()`，导致 Sensor 帧率、音频未恢复，正在写入的 MP4 未写入尾部索引（moov box）；
  - 若在 `AOVTrd` 线程内部直接同步调用 `AXCK_PPL_StopAOV()`，其内部会调用 `DestroyThread(g_tPPLObjt.hAOVThread)` -> `pthread_join(self)`，自身 join 自身必然造成永久死锁 (Deadlock)。
- **对策**：
  - 采用**异步分离工作线程 (Detached Worker Pattern)**：在 `AOVTrd` 达到计数时，创建并分离独立的 `AutoStopAOVWorker` 线程，`AOVTrd` 自身立即安全 `break` 退出；工作线程延迟 50ms 避开原线程上下文后，调用 `AXCK_PPL_StopAOV()` 触发管线恢复与 MP4 容器封包刷盘。

## 13. AX615 AOV 定时器周期与参数配置原则 (sleep_ms / wakeup_ms)
- **现象**：在 `app_config.json` 中同时配置了 `sleep_ms: 800` 与 `wakeup_ms: 120`，发现休眠定时器总时长与实际预期偏差。
- **根因**：AX615 平台硬件休眠定时器驱动中，配置的休眠定时器时间为**包含唤醒时间的完整单周期总时长**。若同时给 wakeup_ms 赋值可能导致周期计算冗余。
- **对策**：AX615 平台统一规范为 `sleep_ms: 1000`，`wakeup_ms: 0`。

## 14. 4K 插值管线内存池 (CMM Pool) 与 HSK 切片缓冲对齐约束
- **现象**：在 Sensor 原生 2.5K (2560x1440) 下开启 IVPS Chn 0 4K (3840x2160) 插值并送入 VENC 0 编码时，若未联动调整 HSK 内存池，板端启动报错 `0x80050004` (POOL UNEXIST / 内存池不足) 或编码行溢出。
- **根因**：
  - VIN 与 IVPS 之间的公共 Buffer `pool.common[0]` 输入端为 Sensor 原生尺寸（2560x1440），不应扩大；
  - 但 VENC 的低内存握手切片环形缓冲 `pool.common[1]` (`SW_LOW_MEM`) 必须与编码器输出尺寸严格对齐（行跨度宽度 Stride 必须达到 3840，即 `3840x128`），否则行切片内存不足以容纳 4K 行缓冲。
- **对策**：
  - `pool.common[0]` (主流帧缓冲)：保持 Sensor 原生 2560x1440；
  - `pool.common[1]` (HSK low-mem ring)：设置为 `width: 3840, height: 128`；
  - IVPS Group 0 Chnl 0 Filter：引擎 `scl` (scl_type: 2)，输出 `3840x2160`；
  - Cache 0 `vout`：与 VENC 对齐设置为 `3840x2160`。

## 15. 双摄互换接线拓扑 (RX0 OS04D10 + RX1 XS9950) 适配原则
- **现象**：硬件实际连线将 RX0 接 OS04D10、RX1 接 XS9950 时，若使用默认双摄配置（RX0 为后摄/RX1 为前摄），系统会出现 I2C 通讯失败（`-121`）或 VENC 编码等待超时。
- **根因**：
  - RX0 对应 Dev 0 / Pipe 0 / `i2c-1`，默认硬件复位引脚为 GPIO 69；
  - RX1 对应 Dev 1 / Pipe 1 / `i2c-0`，复位引脚为 GPIO 66，外接 AHD 芯片需要 Power 引脚 GPIO 71 供电使能；
  - 必须由 `*_os04d10_xs9950.json` 系列配置文件将 Cam0 映射为 Dev 0 (OS04D10 RAW10 AI-ISP) 且 Cam1 映射为 Dev 1 (XS9950 AHD UYVY422 Bypass)。
- **对策**：
  - 加载 `app_config_os04d10_xs9950.json`、`ppl_config_os04d10_xs9950.json` 与 `sns_info_os04d10_xs9950.json`；
  - 启动后检查 `/proc/ax_proc/ivps` 与 `/proc/ax_proc/venc`，确认 Chn 0/1 (OS04D10) 与 Chn 2/3 (XS9950) 均稳定输出 25fps。

## 16. 极端受限内存下 tmpfs 日志爆炸触发 OOM 强杀核心进程
- **现象**：测试或录像运行一段时间后，串口突然打印 `Out of memory: Kill process ... (axck_service)`，守护进程被内核强制杀死。
- **根因**：
  - 板端物理内存仅 ~57MB，NOR Flash 仅数 MB，`/tmp`、`/dev/shm`、`/run` 均挂载在 RAM (`tmpfs`)。
  - 后台运行 `axck_service` 时若将输出重定向到 `/tmp/axck.log`，双摄持续高帧率下日志每分钟产生数兆，短短几分钟膨胀到 19MB+，直接占满可用内存触发内核 OOM Killer。
- **对策**：
  - **严禁向 tmpfs 无限输出日志**：服务与测试进程标准输出统一重定向至 `/dev/null`（如 `./axck_service -l 3 -t 1 > /dev/null 2>&1 &`）。
  - **海量数据/持久日志必须落地外部存储**：必须写入外挂 TF 卡（`/mnt/tfcard`，百G级空间）或 NFS 网络挂载目录（如 `/tmp/test_archive`）。
  - **测试前后主动检查**：每次执行压测或长录像前后，主动执行 `free` 与 `df -h` 检查可用内存与磁盘空间。

## 17. 断流切换（全管线销毁重建）的超时门限与 AI-ISP 恢复特性
- **现象**：通过 HTTP 调用 `stream.set_venc_type`（H.264 ↔ H.265 格式切换）或执行多分辨率动态重构时，默认 HTTP 请求容易超时（报错 `timed out`），或切换完成后前摄帧率长时间为 0。
- **根因**：
  - **全管线重建耗时**：`set_venc_type` 底层调用 `AXCK_PPL_Stop()` 与 `AXCK_PPL_Start()` 依次释放并按序拉起 VIN、ISP、IVPS、VENC、DTCF、Audio、Capture 等全套硬件模块，真实硬件重建耗时约 9.0~10.5 秒。
  - **AI-ISP 3A 算法收敛与 CMM 页面申请**：前摄 OS04D10 运行在 AI-ISP mode 1（2560x1440），在管线完全重建后，3A 算法需要一段连续帧输入才能收敛并达到额定帧率。若短时间内连续多次触发全管线冷重启，容易引发物理 CMM 内存碎片化而减慢恢复速度。
- **测试规程与对策**：
  - **客户端超时设置**：断流切换接口调用时，HTTP 客户端超时时间必须配置为 $\ge 15.0\text{s}$。
  - **采样等待窗口**：切换完成后需预留足够的稳定时间（推荐 3 秒以上），等待 VENC 帧率滑动窗口平滑收敛后再进行 `RecvFPS` 与 `OutFPS` 断言。
  - **自愈守护检查**：在执行断流大用例前，先探针检查当前 VENC 通道是否正常发流，若前摄未处于健康出流状态，可先行自愈重启一次守护进程。







