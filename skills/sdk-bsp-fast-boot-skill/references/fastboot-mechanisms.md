# 快起与双核交接 (Handover) 机制参考

## 1. 架构总览与时序阶段

在 AX615 等芯片的快起（Fastboot / AOV / 打猎相机）场景下，系统采用 RTOS（小核）+ Linux（大核）双核共存运行模式：

```text
上电启动 (Power-on)
    │
    ▼
ROM / SPL / U-Boot (按配置引导)
    │
    ├─────────────────────────────┐
    ▼                             ▼
RTOS (E907 小核) 先跑          Linux (大核) 启动加载
  - 初始化系统时钟/外设          - 内核解压、设备树解析
  - Claim 关键外设 (I2C/ISP/...) - 加载驱动 (私有驱动/外设驱动)
  - 启动 Sensor / ISP / 预览     - 准备接管系统
    │                             │
    └──────────────┬──────────────┘
                   │
                   ▼
           交接协商 (Handover 阶段)
      Linux 发起 Rpmsg Handover 请求
      RTOS 执行 Callback 序列
        - 回收/移交 FrameBuffer
        - 释放外设通道 (Release I2C/SPI)
        - 移交中断亲和性 (IRQ Affinity)
        - 移交 CMM/PrivPool 资源
                   │
                   ▼
           交接完成 (Takeover / Done)
      Linux 完全接管业务流水线 (App/Sample)
```

### 关键阶段划分
1. **阶段 I：RTOS 独占期 (Pre-Handover)**
   - RTOS 启动快起应用（如 `msys`、`qsdemo`），配置 Sensor、ISP 硬件管线出首帧。
   - 需要使用的外设必须在此阶段被 RTOS 占用，未使用的外设必须允许 Linux 正常初始化并使用。
2. **阶段 II：交接协商期 (In-Handover)**
   - Linux 发起 `ax_sys_handover_dispatch_cmd`。
   - RTOS 的 `syshandover` 线程被唤醒，执行各注册模块（`AX_ID_VIN`、`AX_ID_IVPS`、`AX_ID_VENC`、`AX_ID_SYS` 等）的回调函数。
   - 释放外设状态（清除 Dummy Register 占用标志），切换中断路由，移交物理内存块引用。
3. **阶段 III：大核完全接管期 (Post-Handover)**
   - Linux 私有驱动与上层应用（如 sample_vin / QSDemo 大核端）开始正常流转，小核通常进入低功耗待机、监控或保持受限运行。

---

## 2. 硬件仲裁与共享状态寄存器

Linux 与 RTOS 属于异构多核系统，互斥与状态同步依赖硬件 Dummy / Syscon 寄存器以及 RPMSG IPC 通信机制。

### I2C 通道状态仲裁
- **状态寄存器**：`I2C_CHANNEL_STATUS_REG`（对应 `AX_DUMMY_SW6_ADDR`）。
- **位偏移定义**：
  - Bit 2: I2C0 占用状态（1: RTOS in use, 0: Linux 可用）
  - Bit 3: I2C1 占用状态
  - Bit 4: I2C2 占用状态
- **RTOS 驱动行为 (`drv_i2c.c`)**：
  - 必须按需 Claim：通过 `rtos_i2c_claim_mask` 环境变量或 `USER_I2C_CLAIM_MASK` 配置，仅置位实际连接外设的通道。
  - 交接时释放：在 Handover 回调中调用 `i2c_rtos_release_channels()` 清除状态位。
- **Linux 驱动行为 (`i2c-designware-master.c`)**：
  - 检查 `ax_get_rtos_use_status(dev)`。
  - 若为 1，则拒绝传输并返回 `-EBUSY`（禁止返回正数 `EBUSY`）。
  - 若为 0，才进行时钟配置、中断申请与正常传输。

---

## 3. Handover 关键流程与接口

### RTOS 端关键符号
- `ax_sys_handover_register_cb(mod_id, callback, data)`：注册交接回调。
- `ax_sys_handover_increase_refcnt(mod_id)` / `ax_sys_handover_decrease_refcnt(mod_id)`：维护交接引用计数。若引用计数未归零，交接将阻塞直至超时。
- `ax_sys_handover_callback_exec()`：逐个执行各模块交接回调。
- `ax_sys_handover_done(status)`：向 Linux 上报 `AX_SYS_HANDOVER_DONE` 或 `AX_SYS_HANDOVER_ABORT`。

### Linux 端关键符号
- `ax_sys_is_co_exist()`：返回当前多核共存状态：
  - `AX_CO_EXIST_NONE`：单 Linux。
  - `AX_CO_EXIST_RTT_OS`：双核共存，RTOS 正在主导。
  - `AX_CO_EXIST_LINUX_OS`：双核共存，已完成交接，Linux 主导。
- `sys_rpmsg_linux_takeover.c`：接收 RTOS 回复，唤醒等待交接的大核进程。

---

## 4. 典型异常模式与诊断切入点

| 异常表现 | 典型根因 | 关键排查手段 |
|---|---|---|
| **交接前 Linux 报 `-EBUSY` / `busy, rtos using`** | 小核未按需 Claim 外设，硬编码占用了全部通道（如 I2C/SPI） | 检查 RTOS 外设 Claim mask、共享状态寄存器读数 |
| **Linux 报 `rpmsg send failed` / Handover Timeout** | 某模块 `refcnt` 未释放、中断未响应、或 RTOS 线程死锁 | 打印 RTOS 端 `_ax_sys_handover_check_refcnt_log`，检查哪一个 `mod_id` 阻塞 |
| **交接瞬间系统软挂 / 触发硬件看门狗复位** | 1. 中断路由切换（Affinity）导致大核未挂接 ISR 却收到中断风暴；<br>2. 共享内存（CMM/PrivPool）引用计数混乱；<br>3. 释放通道时外设正在进行传输 | 禁用看门狗复现现场，连接 Trace32 抓取 PC/LR/SP，查看断言或 Hang 现场 |
| **首帧图像撕裂、丢帧或花屏** | FrameBuffer 移交时 `yuv_done_mask` 校验失败，或 DropFrame 标记不正确 | 查看 `vin_comm_glb_impl.c` 中的 `overflow_mask` 及 recovery 状态 |
| **压测多轮后交接超时，小核报 `rt_mutex` 断言挂死** | RT-Thread POSIX 静态互斥锁宏（`PTHREAD_MUTEX_INITIALIZER`）未真正初始化内核对象，高并发破坏挂起链表 | 废弃静态初始化宏，在模块入口显式调用 `pthread_mutex_init()` 动态初始化 |
| **Reboot 或交接异常时大核内核崩溃在 `__vunmap+0x58`** | Linux 释放 CMM 远端通过 RPMSG 查虚地址，RTOS 返回未初始化脏地址且 Linux 忽略返回值校验，传入非法地址引发解引用野指针 | 跨核 RPC 返回值防御性判空，严禁将未验证的对端虚拟地址传入 `ax_iounmap` |
| **快起进入 Linux 后子系统报 `0x80200215 (NOT_PERM)` 节点缺失** | 极限裁剪（DDR64 Lite）工程采用全内置策略，但关键驱动（如 ALSA Machine 驱动）被误配为 `=m` 导致无法加载 | 检查裁剪工程 `defconfig`，将必需的 Platform、Codec、Machine 驱动统一强配为 `=y` |
| **小核无法正常配置 Sensor** | Sensor 挂载的 I2C 通道被 RTOS claim mask 排除，或 Sensor Slave Addr 冲突 | 检查 `tSnsBusInfo.I2cDev` 与 `i2c_rtos_claim_mask_get()` |
