# 快起与交接日志指征与排查指引

## 1. 关键模块与日志指征特征库

### A. I2C / 外设仲裁类冲突
- **Linux 侧错误日志**：
  ```text
  i2c_designware ...: ax_i2c0 busy, rtos using
  i2c_designware ...: failure requesting irq 12: -16
  ```
  - **指征**：Linux 在交接前访问外设，发现共享寄存器中状态为 1（RTOS 正在占用）。
  - **排查点**：
    1. 检查该 I2C 通道上连接的是否为 Sensor？若为 4G、RTC、PMIC 等 Linux 端需提前通信的外设，RTOS 绝不可占用。
    2. 检查 RTOS 环境变量 `rtos_i2c_claim_mask`，确认是否包含了不需要的通道位。
- **RTOS 侧错误日志**：
  ```text
  [E/I2C] i2c channel 1 is not claimed by rtos
  [E/ISP] set sensor bus info failed with 0xffffffff!
  ```
  - **指征**：RTOS 的 Sensor 驱动试图使用未被 Claim 的通道。

---

### B. Handover (交接) 超时与失败类
- **Linux 侧错误日志**：
  ```text
  [ERR][SYS] rpmsg wait handover done timeout!
  [ERR][VIN] ax_rpmsg_request failed, mod_id(1)
  ```
  - **指征**：大核向小核发送交接请求后，在规定超时内未收到 `AX_SYS_HANDOVER_DONE`。
- **RTOS 侧错误日志**：
  ```text
  [ERR][SYS] handover cb running timeout, mod_id: 2
  [ERR][SYS] handover refcnt not zero! mod: VIN, refcnt: 1
  [ERR][VIN] pipe_mask[0x1] status[0x1,0x0,0x0,0x0,0x0] recovery[0x0] overflow[0x0]
  [ERR][VIN] PIPE[0] recovery_status invalid, abort!
  ```
  - **排查点**：
    1. 哪一个模块未减引用计数？（`AX_ID_SYS` / `AX_ID_VIN` / `AX_ID_IVPS` / `AX_ID_VENC`）。
    2. Sensor 首帧是否正常输出？若无中断或 Sensor 没出流，`yuv_done_mask` 未匹配，VIN 会主动触发 `handover abort`。

---

### C. 内存 / Buffer / PrivPool / CMM 异常
- **日志特征**：
  ```text
  [ERR][VIN] pool hand over fail
  [ERR][SYS] Block_giveback_to_pool checkref failed
  [ERR][MMZ] cmm alloc fail in fastboot
  Unable to handle kernel NULL pointer dereference at virtual address 00000024
  PC is at __vunmap+0x58/0x78
  LR is at ax_cmm_free+0xbd/0x194 [ax_sys]
  ```
  - **指征**：
    1. 小核分配的 CMM / PrivPool 物理内存块在大核接管时未正确对接或引用计数双重释放；
    2. 双核未交接或异常退出时，Linux 释放 CMM 远端向 RTOS 查询内核虚拟地址，对端返回脏数据导致 `ax_iounmap` -> `__vunmap` 崩溃。
  - **排查点**：
    - 检查多核共存标志 `ax_sys_is_co_exist()`；
    - 检查 RPMSG 获取 kvirt 响应中是否有错误校验（禁止直接将对端指针传给 `vunmap`）；
    - 检查 CMM pool 剩余空间及是否发生碎片化。

---

### D. RTOS POSIX 兼容层 / 并发锁死锁
- **日志特征**：
  ```text
  (mutex != RT_NULL) assertion failed at function: rt_mutex_take...
  assertion failed at function: rt_mutex_release... (mutex owner is empty)
  [ERR][SYS] handover cb running timeout, mod_id: 2
  ```
  - **指征**：压测多轮后偶发交接超时，小核控制台抛出 `rt_mutex` 断言挂死。
  - **排查点**：
    - 检查 RTOS 代码中是否存在全局或静态变量直接使用 `PTHREAD_MUTEX_INITIALIZER` 或 `PTHREAD_COND_INITIALIZER`；
    - RT-Thread POSIX 适配层中静态初始化未真正调用 `rt_mutex_init`，多线程并发争抢锁时导致内核链表破坏。必须在代码入口显式调用 `pthread_mutex_init()`。

---

### E. 极限裁剪 (Lite / DDR64) 驱动与节点缺失
- **日志特征**：
  ```text
  [ERR][AI] AX_AI_EnableDev failed, ret 0x80200215
  ls: /dev/snd: No such file or directory
  ```
  - **指征**：功能使能后应用层报权限不足 `0x80200215 (NOT_PERM)` 或找不到对应设备节点。
  - **排查点**：
    - 检查工程是否为无动态模块机制的裁剪版（无 `/lib/modules`）；
    - 检查 Linux `defconfig` 中相关子系统驱动（如 ALSA Machine 驱动 `CONFIG_SND_SIMPLE_CARD`）是否被误配为了 `=m`；
    - ASoC 链路必须保证 Platform DAI、Codec、Machine 三者均内置编译为 `=y`。

---

### F. 跨核内存踩踏、CMM 负数与 DMA 溢出类
- **日志特征**：
  ```text
  cat /proc/ax_proc/mem_cmm_info -> remain 数据为负数
  Kernel panic - not syncing: Attempted to kill init!
  [DMA] invalid physical address 0x...
  ```
  - **指征**：
    1. CMM 剩余内存统计下溢为负数，证明发生 Double Free 或跨核计数失步；
    2. Linux 接管后在 CMM 申请到重复的物理地址，两模块相互踩踏；
    3. 硬件外设 DMA 寄存器交接时基地址配置错误，将图像数据直接写到了 Linux 内核代码段。
  - **排查点**：
    - 检查 CMM 接管后分配位图（Bitmap）在 Linux 端的初始化对齐情况；
    - 检查各外设在 Handover 切换驱动所有权时是否彻底关闭/清空了旧有的 DMA 通道与描述符。

---

## 2. 交互式调试与定位步骤

### 步骤 1：确认故障发生的精准阶段
1. **Pre-Handover**（RTOS 运行，Linux 启动中，交接未发生）：
   - 典型问题：外设冲突（如 I2C/SPI busy）、内存踩踏、DDR 争抢。
2. **In-Handover**（Linux 发起交接，RTOS 执行 callback）：
   - 典型问题：Handover 超时、Abort、Refcnt 未清零、中断切换风暴。
3. **Post-Handover**（交接已完成，Linux 运行业务）：
   - 典型问题：首帧丢帧、大核驱动无法复用通道、小核未完全释放外设时钟。

### 步骤 2：提取关键配置与状态
- **检查环境参数**：
  - U-Boot / RTOS env：`rtos_i2c_claim_mask`、`isp_cam`、`bootargs` 中的快起相关参数。
- **检查硬件寄存器**：
  - 共享状态寄存器（如 `AX_DUMMY_SW6_ADDR` / `0x0280xxxx`）各 bit 状态。
  - 外设时钟门控（`PERIPH_CLK_EB_*`）。

### 步骤 3：看门狗与现场保护
若复现时伴随突然重启（ROM/SPL 重新打印）：
1. 必须优先关闭或放宽 RTOS 及 Linux 软硬件看门狗（Watchdog）。
2. 让系统停留在 Hang 住的现场，使用 Trace32 连上两核，检查各自 PC 指针停在哪个函数（是 wait completion 还是 assert 死循环）。
