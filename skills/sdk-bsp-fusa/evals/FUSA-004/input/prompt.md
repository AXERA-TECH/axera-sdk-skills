# 客户提问（原始措辞）

> 我们 M57 QNX SDK，版本 QNX_V1.10.0。
> 现场复现：反复调用 FCU 的 set_mask 之后，会出现中断风暴，串口刷一堆 FCU 相关日志，严重时看起来像卡死。
>
> 我在 FAQ 里看到说这个竞态问题 V1.1.0 已经修了，于是我们按 FAQ 的描述去代码里找线索：
> 在 `kernel/osdrv/private_drv/fcu/` 下面 grep 关中断相关的原语（`irq_save`、`InterruptLock` 之类），
> 结果是 **0 个匹配**。
>
> 我们版本比 V1.1.0 高，按理应该已经修了，为什么搜不到？是不是说明这个修复根本没进来？

## 后续回填：grep 的原始输出与版本判据

（见 `grep-result.txt`、`sdk-check.txt`。）
