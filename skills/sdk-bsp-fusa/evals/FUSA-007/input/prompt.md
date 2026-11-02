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
