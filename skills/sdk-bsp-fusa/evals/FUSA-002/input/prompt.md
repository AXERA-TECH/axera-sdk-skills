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
