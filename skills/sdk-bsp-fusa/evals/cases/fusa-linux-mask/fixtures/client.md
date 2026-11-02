# 离线验收素材

来源：原有 FUSA-002 的 input/，无客户 SDK 或板端连接。

## prompt.md

# 客户提问（原始措辞）

> 我们 M57 Linux SDK 的应用收到诊断事件，日志里有这么一行：
>
> ```text
> [  412.882104] diag-netlink: err ID: 17 module ID: 45 domain ID: 0
> ```
>
> 另外用户态打印的 `error_mask: 0x002D0011` 也对得上。
>
> 我查了 FAQ，说 err 17 是 server 心跳超时，但我们板子 CPU 很闲（顶多 5%），
> 也没有别的异常，为什么还会心跳超时？是不是心跳线程有问题？

## 后续回填：SDK 判据与更多日志

（见 `sdk-check.txt`、`serial.log`。）

## sdk-check.txt

$ cd /workspace/sdk/m57-linux
$ test -d kernel/linux/linux-6.1.83/drivers/soc/axera/fusa && echo LINUX_HIT
LINUX_HIT
$ test -f kernel/osdrv/private_drv/diag_core/driver/diag_stl.c && echo QNX_HIT
$ cat build/version/m57_version.mk
SDK_VERSION=V2.10.0
SDK_BRANCH=m57h_trunk
$ rg -n "0x002D0011" header/external/ax_diag_type_ex.h | head -2
(LINUX 侧错误码表存在，条目由排查者自行查证)

## serial.log

# FUSA-002 串口摘录（客户原始保存，已去 ANSI 颜色码）

[    0.000000] Linux version 6.1.83 (build@axera) #1 SMP PREEMPT
[    9.882104] axdiag: register_axdiag: platform device created
[  120.000000] ax_diag_service is up, netlink handshake done
[  400.120301] isp_pipe: stream on chn 0
[  412.881900] diag-netlink: err ID: 17 module ID: 45 domain ID: 0
[  412.882104] axdiag: diagnosis_error_send: report=1 forward=1 reset=0
[  412.883012] NetlinkHeartBeatHandle: ack
[  420.110000] diag_stl: heartbeat time:1
[  420.130119] NetlinkHeartBeatHandle: ack
[  440.110000] diag_stl: heartbeat time:1
[  440.130119] NetlinkHeartBeatHandle: ack
[  460.110000] diag_stl: heartbeat time:1
[  460.130119] NetlinkHeartBeatHandle: ack

# ---- 用户态侧打印 ----
[  412.883900] AxDiagCore: recv event error_mask: 0x002D0011
