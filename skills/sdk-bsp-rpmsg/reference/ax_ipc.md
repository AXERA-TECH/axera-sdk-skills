# M57 AX IPC / RPZC 知识库

## requirements

- 主域运行 M57 Linux `linux-6.1.83`；IPC 依赖 `CONFIG_AXERA_MBOX`、`CONFIG_RPMSG_CHAR`、`CONFIG_RPMSG_CTRL` 和 `CONFIG_RPMSG_AXERA`。启用 zero-copy 时还需要 `CONFIG_RPZC_SERVICE_RPMSG` 与 `CONFIG_RPZC_CONTROLLER`。
- 主域运行QNX时，其IPC和IPCZC驱动框架和MCU域IPC&IPCZC一致。
- 远端为 SafetyIsland R-core。本文以 `SafetyIsland/mcal/` 的 MCAL IPC 配置为准；RT-Thread 或 bare-metal 使用不同配置时，必须分别核对 endpoint、mailbox slot 与共享内存。
- 本文使用 `demo_nor_nand` 的设备树举例。其他平台的 reserved-memory、启用的 `rpmsgN` 节点和 GPIO 通知方式可能不同，不能照搬物理地址或设备节点编号。

## overview

AX IPC 为 A-core 与 SafetyIsland R-core 提供两类通信能力：

- **RPMsg**：用于控制消息和小数据。Linux 使用标准 RPMsg 框架：Axera transport 将 mailbox / GPIO 通知与 shared-memory virtqueue 接入 virtio RPMsg bus；用户态通过 `RPMSG_CTRL`、`RPMSG_CHAR` 导出的字符设备收发消息。
- **RPZC（Remote Processor Zero Copy）**：用于大块数据。它以名为 `axera,rpzerocopy` 的 RPMsg service 传输 buffer 创建、销毁、传输和 ACK 控制消息，payload 则通过共享 DMA buffer 访问。Linux 侧通过 `/dev/rpzc_ctrlN` 和动态创建的 `/dev/rpzc-<name>` 使用该能力。

Mailbox 或 GPIO 只承担通知职责；RPMsg payload 位于 virtqueue buffer，RPZC payload 位于 controller 分配的 DMA buffer。不要把 mailbox data 当作业务大数据通道。

### 特性

- 基于 virtio RPMsg bus、共享内存 vring 与 Axera mailbox；`rpmsg0` 在单物理通道配置下可通过 `ipc-gpio` 脉冲通知。
- 支持 remote name service 和 Linux 用户态动态创建 endpoint。
- 支持 RPZC buffer 的创建、销毁、传输、接收、可用性查询、同步传输和 ACK。
- Linux RPZC buffer 支持 `mmap()`，映射由内核设置为 non-cached。
- SafetyIsland MCAL 侧保留静态 endpoint / buffer 配置；Linux 侧的 RPZC payload 内存由 controller 使用 DMA API 分配。

### 代码路径

| 层次 | Linux 实现 | SafetyIsland 对端 |
| --- | --- | --- |
| RPMsg transport | `kernel/linux/linux-6.1.83/drivers/rpmsg/axera_rpmsg.c` | `SafetyIsland/mcal/mcal_drv/Ipc/` |
| mailbox controller | `kernel/linux/linux-6.1.83/drivers/mailbox/mailbox-axera.c` | MCAL IPC mailbox 配置 |
| Linux 用户态 RPMsg ABI | `kernel/linux/linux-6.1.83/drivers/rpmsg/rpmsg_char.c`、`rpmsg_ctrl.c`、`include/uapi/linux/rpmsg.h` | `SafetyIsland/mcal/mcal_drv/Ipc/inc/Ipc.h` |
| RPZC framework / 用户态 ABI | `kernel/linux/linux-6.1.83/drivers/rpmsg/axera_rpmsg_zc/`、`include/uapi/linux/rpzc_cdev_user.h` | `SafetyIsland/mcal/mcal_drv/Ipc_zc/` |
| 平台资源 | `kernel/linux/linux-6.1.83/arch/arm64/boot/dts/axera/m57.dtsi` 和平台 `.dts` | `SafetyIsland/mcal/mcal_config/generated/` |
| Linux 示例 | `msp/sample/ipc_rpmsg/`、 `SafetyIsland/mcal/mcal_example/examples/Demo/` |

QNX平台IPC和IPCZC驱动框架和MCU域MCAL IPC&IPCZC基本一致。代码路径：kernel/osdrv/open_drv/ax_ipc/
RTOS平台IPC和IPCZC驱动框架和MCU域MCAL IPC&IPCZC基本一致。代码路径：SafetyIsland/rt-thread/bsp/m57/drivers/ipc/

## design-decisions

### Linux 主域架构

主域分层如下：

1. `mailbox-axera` 提供 Linux mailbox controller；设备树以 `<slot, destination-core>` 描述 mailbox channel。
2. `axera_rpmsg` platform driver 从设备树获取 `rx` / `tx` mailbox channel、vring 地址和可选 `ipc-gpio`，注册 virtio device。
3. `virtio_rpmsg_bus` 创建 RPMsg device / endpoint；remote name service 会公布服务名。
4. `RPMSG_CTRL` 创建 `/dev/rpmsg_ctrlX`，`RPMSG_CHAR` 为 endpoint 创建 `/dev/rpmsgX`。用户态以 `read()` / `write()` / `ioctl()` 通信。
5. `RPZC service` 匹配 service 名 `axera,rpzerocopy`，将 RPZC 控制消息收发映射到 RPMsg；RPZC controller 再导出 `/dev/rpzc_ctrlN` 和 buffer 字符设备。

### MCU 域框架

- `Ipc`：封装 `rpmsg_lite` endpoint、ring buffer、mailbox IRQ 和 callback。
- `Ipc_zc`：维护 `IpcZC` buffer 表、zero-copy message 格式、ACK 状态机和 buffer callback。
- `Ipc` 与 `Ipc_zc` 通过 MCAL config 绑定，不应在业务代码中硬编码新的 endpoint、slot、shared memory 或 buffer name。

### 平台资源与数据流

以工程 `demo_nor_nand` 为例：

- 基础节点 `rpmsg0` 的 compatible 为 `axera_rpmsg`，使用 mailbox slot `0` / `1`，destination core 为 `3`；`rpzc_ctrl0` 关联到 `rpmsg0`，controller index 为 `0`。
- 平台 `.dts` 为 `rpmsg0` 配置 vring 地址 `0x400000`、`rpmsg0_reserved`，并配置 `ipc-gpio`；为 `rpzc_ctrl0` 配置 `rpzc0_reserved`。
- `rpmsg0` 创建两个 virtqueue。Linux 发送 RPMsg 时将消息写入 virtqueue，随后通过 GPIO 或 mailbox 唤醒远端；接收 mailbox 通知后在 delayed work 中触发对应 virtqueue。

不要仅在一端修改 shared-memory 地址、mailbox slot、endpoint 名称或 service 名称。此类配置同时约束 Linux DTS、SafetyIsland 配置和启动阶段的内存布局。

### RPMsg endpoint 创建与使用

SafetyIsland 在 MCAL 配置中定义 endpoint。对需要 name service 的 endpoint，Linux 会按服务名匹配相应 kernel driver；用户态也可以从 `/dev/rpmsg_ctrlX` 创建 endpoint。

Linux 用户态的标准流程如下：

1. 等待远端启动、`axera_rpmsg` probe 完成，确认 `/sys/class/rpmsg/` 存在对应 RPMsg device。
2. 打开 `/dev/rpmsg_ctrlX`，以 `RPMSG_CREATE_EPT_IOCTL` 提交 `struct rpmsg_endpoint_info`（service name、src、dst）。
3. 打开创建出的 `/dev/rpmsgX`，使用 `write()` 发送、`read()` 接收。
4. 完成后在 endpoint fd 上调用 `RPMSG_DESTROY_EPT_IOCTL`，再关闭 fd。

`rpmsg_endpoint_info` 的 `name` 长度为 32 字节；不用地址时使用 `RPMSG_ADDR_ANY`。`RPMSG_CREATE_DEV_IOCTL` / `RPMSG_RELEASE_DEV_IOCTL` 是 control device 的另一组 ABI，不应私自复用 ioctl 编号。

### RPZC buffer 生命周期

RPZC 的 Linux 用户态 API 定义在 `include/uapi/linux/rpzc_cdev_user.h`：

1. 打开 `/dev/rpzc_ctrl0`（编号由 DTS `rpzcctrl-index` 决定）。
2. 使用 `RPZC_CTRL_DEV_IOCTL_CREATE_BUF` 传入 `struct rpzc_buffer_info`，指定跨端一致的 buffer name 与长度；内核创建 `/dev/rpzc-<name>`。
3. 打开 buffer 设备并调用 `mmap()`，从该映射读写 payload。单个 buffer 设备同一时间只允许一个 opener。
4. 通过 `RPZC_BUF_DEV_IOCTL_CHECK_AVAIL` 确认远端 buffer 已就绪后再传输。
5. 用 `RPZC_BUF_DEV_IOCTL_TRANSMIT_BUF` 提交 offset 与 data_len。若 buffer 开启同步传输，发送方会等待远端 ACK。
6. 接收端用 `RPZC_BUF_DEV_IOCTL_RECEIVE_BUF` 获取 offset、data_len、剩余 timeout 和 `need_ack`；当 `need_ack != 0` 时，在消费完 payload 后调用 `RPZC_BUF_DEV_IOCTL_REPLY_ACK`。
7. 停止使用时关闭 buffer fd，并通过 `RPZC_CTRL_DEV_IOCTL_DESTROY_BUF` 销毁 buffer device；关闭 control fd 时，内核会清理该 fd 未销毁的 buffer。

RPZC 的控制消息长度上限是 96 字节，buffer name 长度为 32 字节。offset、data_len、timeout 及返回的 `need_ack` 均使用 UAPI 结构体中的定宽类型，用户态必须与内核头文件保持一致。

### SafetyIsland 对端约束

- `SampleEpt_IPC_ZC_ID` 使用 name-service 名称 `axera,rpzerocopy`，它是 Linux `rpzc_service_rpmsg` 所匹配的控制 service；普通业务 endpoint 不得复用它。
- MCAL 侧 endpoint 数量上限为 20。新增 endpoint 前应评估静态 ring buffer 占用及启动时间。
- MCAL RPZC 以 `BufferName` 匹配远端 buffer；枚举名的 Read / Write 方向在两端可能镜像，不能只依据 enum 名称判断方向。
- RPZC 同步 buffer 的发送端在 ACK 完成前不得复用同一 buffer。
- Linux 内核示例与 MCAL demo 的 buffer 名称并不相同，不能直接把两者作为互通测试组合；实际测试必须选择两端配置一致的一组名称、长度和方向。

### reset / reinit 与并发

- 链路未建立、远端尚未完成 name service 或 endpoint 地址不匹配时，RPMsg send 失败是预期现象；先检查 transport 和 service，再检查业务 payload。
- Linux RPZC controller 和 service 的关联以底层 RPMsg transport device 为 token。RPMsg service remove 或 controller remove 时会注销对应 RPZC 对象和字符设备，已打开的用户态 fd / 映射不可假设继续有效。
- RPZC 接收 buffer 在上一笔数据尚未消费时再次收到数据，会报告 `previous recv data not treated` 并拒绝新数据。接收端应先复制或处理 payload，再回复 ACK。
- `RPZC_BUF_DEV_IOCTL_RECEIVE_BUF` 支持负数 timeout（可中断的无限等待）、零 timeout（不等待）和正数毫秒 timeout；业务代码必须处理 `-ETIMEDOUT` 与信号中断。
- SafetyIsland reset / reinit 使用 `IpcRpmsgReset()`、`IpcRpmsgReinit()`；MCAL 业务发送前应使用 `IpcEptLinkStatusCheck()`，RPZC 发送前应使用 `IpcZcLinkStatusCheck()`。
- MCU 域`IPC_ZC_POLLING_ACK_EN` 当前配置为 0；若改为 polling 语义，必须补充 CPU 占用、timeout 和并发测试。
- 锁保护，为了防止 ringbuf 数据丢失或混乱，同时又不降低执行效率，仅当 ept 操作 ringbuf 时需要锁保护。

## api-contracts

## pitfalls

### 常见误判

- **把 mailbox 当成 payload 通道**：错误。mailbox / GPIO 只触发通知；RPMsg payload 经过 virtqueue，RPZC payload 位于 DMA buffer。
- **认为 RPZC 独立于 RPMsg**：错误。RPZC 控制消息通过 `axera,rpzerocopy` RPMsg service 通信。
- **创建 RPZC buffer 后立刻发送**：不充分。远端需要完成同名 buffer 的协商；先检查 `RPZC_BUF_DEV_IOCTL_CHECK_AVAIL`。
- **收到 RPZC 描述符后延后消费共享 buffer**：高风险。后续数据可能覆盖该区域；应在回调 / 接收处理路径复制或完成业务消费后再 ACK。
- **只改 Linux 或只改 SafetyIsland 的名称、slot 或地址**：高风险。DTS、MCAL 配置和固件实际映射必须一致。
- **套用 kernel sample 的 buffer name 到 MCAL demo**：错误。示例的 buffer name 并非相同配置，不能默认互通。
- **用 enum 名称判断 `ipczc` 方向**：不充分。应核对 `BufferName`、local/remote 方向和业务读写关系。
- **不要在未确认 `IpcEptLinkStatusCheck` / `IpcZcLinkStatusCheck` 通过前发送数据**：link 未建立时 send 失败是预期行为。

### 禁止事项

- 禁止在未核对 endpoint link、远端 name service 和 `/sys/class/rpmsg/` 状态前，将发送失败归因为业务 payload。
- 禁止绕过 `include/uapi/linux/rpmsg.h` 或 `include/uapi/linux/rpzc_cdev_user.h` 私自构造 ioctl。
- 禁止使用未确认可用、已 destroy、reset 后失效或名称不匹配的 RPZC buffer。
- 禁止在需要 ACK 的接收数据未消费前调用 `RPZC_BUF_DEV_IOCTL_REPLY_ACK`。
- 禁止单端修改 `MaxEptNumber`、`MaxZCIDNumber`、endpoint name、buffer name 或 reserved memory 地址

### 首要 debug 证据

1. **内核配置**：确认目标配置启用 RPMsg、Axera mailbox 与 RPZC 选项。
2. **设备树**：确认 `mailbox`、目标 `rpmsgN`、`rpzc_ctrlN` 已启用；核对 `reg`、`memory-region`、`mboxes`、`rpmsg-index` 和可选 `ipc-gpio`。
3. **驱动 probe**：检查 `dmesg` 中 `axera rpmsg driver is registered`、mailbox 初始化、RPZC controller / service probe 日志及错误返回。
4. **RPMsg 枚举**：核对 `/sys/class/rpmsg/` 下 endpoint 的 name、src、dst，并确认 `/dev/rpmsg_ctrlX` / `/dev/rpmsgX` 存在。
5. **RPZC 生命周期**：记录 buffer name、len、available 状态、offset、data_len、need_ack、timeout、ioctl 返回值和 errno。
6. **SafetyIsland 状态**：核对 MCAL `IpcInitial()` / `IpcZcWholeInitial()` 是否完成，并检查 `IpcEptLinkStatusCheck()` 或 `IpcZcLinkStatusCheck()` 的结果。
7. **共享内存**：核对 Linux DTS reserved-memory 与 SafetyIsland `ReservedMemory_cfg.h` 的对应关系；不要只依据单侧 C 代码判断。
8. **reset**：确认远端是否重启、`IpcRpmsgReset()` / `IpcRpmsgReinit()` 是否执行、callback 是否重新注册。
9. **锁实现**：MCU 端可能是 BareMetal / RTOS / AUTOSAR，不同的情况下锁的实现是不同的，默认情况下 MCU 端 RPMSG 的锁是空的，需要用户自己实现，这个需要特别注意。

## test-strategy

- AX637在测试IPC/IPCZC时，需要先允许MCU端RTT下的测试工具，sample_ipc_test和sample_ipczc_test

### 构建前检查

- UT测试有主域端统一的平台触发，UT 代码生成后需要嵌入到平台控制代码中，代码路径：主域为ut/  MCU域为SafetyIsland/mcal/mcal_example/examples/Demo/

### RPMsg 基础链路

测试应覆盖：

- 远端公布 name service 后，Linux 能创建并打开目标 endpoint。
- Linux `write()` 与 SafetyIsland `IpcSendData()` 双向传输内容一致。
- endpoint name、src / dst 不匹配、远端未启动、空接收等负向场景均返回可诊断错误，不遗留 endpoint。
- 使用 kernel RPMsg sample 时，通过其 debugfs 节点触发小消息 loopback / 性能测试；该 sample 是否编入目标镜像取决于目标 defconfig。

### RPZC 基础链路

测试应覆盖：

- Linux 创建 buffer 后，SafetyIsland 同名 buffer 可用，`CHECK_AVAIL` 返回 ready。
- Linux `mmap()` 写入后，通过 `TRANSMIT_BUF` 发送正确的 offset / data_len；SafetyIsland 读取到一致的内容。
- SafetyIsland 向 Linux 回传时，Linux `RECEIVE_BUF` 得到正确描述符；`need_ack` 为真时回复 ACK，发送端在 timeout 前恢复。
- 测试 create / destroy、重复 buffer name、单 buffer 多次 open、未 ready 发送、offset / data_len 越界、ACK timeout、远端 reset 和 remove 后的 fd / mapping 失效行为。

## review-findings
