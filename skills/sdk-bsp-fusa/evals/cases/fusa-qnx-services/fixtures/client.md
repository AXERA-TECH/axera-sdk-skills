# 离线验收素材

来源：原有 FUSA-007 的 input/，无客户 SDK 或板端连接。

## prompt.md

# 客户提问（原始措辞）

> 我们是 M57 QNX SDK，版本 QNX_V1.10.0。
>
> 手上有一份《FuSa 排查手册》，第一步就是让列节点：
>
> ```text
> $ ls /sys/devices/platform/axdiag/
> ls: /sys/devices/platform/axdiag/: No such file or directory
> ```
>
> 后面还有 `cat /sys/class/fusa/fcu/*/fsm`，我们读也读不到。
> 是不是说明我们的 FuSa 根本没有编译进去？
>
> 另外我们顺带看了下进程：`pidin ar | grep diag` 只有 diag_core_drv 和 m57_ecm_drv，其他没有了。
>
> 我们最担心的是：客户现场报过一个 FCU 相关故障，我们这边完全没收到诊断日志，
> 现在怀疑是 FuSa 没编进去导致的。

## 后续回填：SDK 判据与板端事实

（见 `sdk-check.txt`。）

## sdk-check.txt

# FUSA-007 客户回填：SDK 判据与板端事实

$ cd /workspace/sdk/m57-qnx
$ test -f kernel/osdrv/private_drv/diag_core/driver/diag_stl.c && echo QNX_HIT
QNX_HIT
$ test -d kernel/linux/linux-6.1.83/drivers/soc/axera/fusa && echo LINUX_HIT
$ cat build/version/m57_version.mk
SDK_VERSION=QNX_V1.10.0
SDK_BRANCH=m57qnx_trunk
$ ls .repo/manifests/ | tail -2
M57_SDK_QNX_V1.10.0.xml

# ---- 板端 ----
$ uname -a
QNX <hostname> 7.1.0 aarch64le
$ ls /proc/ax_diag/
domain0  domain1  domain16
$ ls /dev | grep -E "ecm|fcu|diag_extend"
/dev/ecm
/dev/diag_extend
$ pidin ar | grep -E "diag_core_drv|diag_extend|m57_ecm_drv|fcu_drv"
  4194321       1 diag_core_drv       10r   usr/bin/diag_core_drv
  4194322       1 diag_extend         10r   usr/bin/diag_extend
  4194323       1 m57_ecm_drv         10r   usr/bin/m57_ecm_drv
$ echo $?
0
