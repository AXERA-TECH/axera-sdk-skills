# AX615 历史问题记录

本文件记录一组历史问题资料。客户、工单与内部项目元数据已脱敏；字段只填入现有技术参考和历史记录能够支持的内容，不根据标题和现象补猜。

## 历史问题案例

```text
历史问题编号：已脱敏
标题：wakeup_count 机制异常问题
状态：未提供，不能判断
客户/项目：已脱敏
影响模块：BSP；gpio_lp 低功耗 GPIO 与 Linux PM 唤醒路径
影响芯片/板卡：AX615；具体板卡版本未提供，不能判断
影响 SDK/BSP 版本：AX615_SDK_V2.0.0_P8
修复版本：AX615_SDK_V3.3.0、AX615_SDK_V3.11.1
关联 commit/change：未提供，不能判断；资料仅提到 gpio_lp.diff

现象：
- 不使用应用层 wakeup_count 时，约 1~8 ms 的短时 GPIO 唤醒可能丢信号；较长脉冲的结果需结合现场复测。
- 使用应用层 wakeup_count 读写路径后，GPIO 唤醒可能生效，但系统可能无法正常进入休眠或后续 AX_SYS_Sleep 返回非零。
- 日志可能出现 `PM: suspend entry (deep)` 后 `Freezing of tasks aborted` 或 `PM: suspend exit`。
- VIN/AOV 同时运行时可能出现 `GetDevFrame` 错误或时序相关结果，但该现象不能单独证明 PM 根因。

复现条件：
- 硬件版本：未提供，不能判断
- 温度/电压/负载：未提供，不能判断
- 低功耗 GPIO 编号、触发类型和设备树精确配置：未提供，不能判断
- 休眠类型：资料指向 Linux deep suspend
- 应用层 wakeup_count：分别测试不使用、错误简化写法和正确 read/write 协议
- GPIO pulse 时序：历史资料覆盖约 1 ms、8 ms、15 ms、几十毫秒和 500 ms 等档位；当前样本数和概率未提供，不能判断
- 复现步骤：在相同硬件、BSP、业务负载和 timer32 配置下，记录 GPIO pulse、wakeup_count、PM 日志和应用结果的完整时序

证据：
- 日志/时间线：当前 Skill 给出关键日志模式，但具体现场原始日志未提供，不能判断
- 代码或配置：问题版本的 gpio_lp IRQ handler 可能只更新私有等待队列并清除 GPIO 状态，未调用 `__pm_wakeup_event(gpio_lp->ws, 0)`；实际分支需核对
- 修复前后对照：资料描述 `gpio_lp.diff` 在历史实验中改善丢中断，但同时唤醒时延可能增加；当前镜像是否包含该变更未提供，不能判断
- 测试报告/附件：未提供，不能判断

根因：高可信候选——有效 GPIO 低功耗中断未及时同步到 Linux PM wakeup-source，导致应用层 wakeup_count 读写窗口与 GPIO 事件之间存在竞态。只有在当前源码、运行镜像和 A/B 结果对齐后，才能升级为已确认。
修复内容：在有效 `int_status` 分支调用 `__pm_wakeup_event(gpio_lp->ws, 0)`；在 remove 和 probe 错误回滚路径正确注销 `wakeup_source`。具体 patch/commit 未提供，不能判断。
验证结果：历史资料记录修复后“不再丢中断”，并观察到约 46 ms/50 ms 的唤醒时延参照值；当前平台的可靠性、时延和多次 probe/remove 结果未提供，不能判断。
适用边界：仅适用于 AX615、Linux deep suspend、低功耗 GPIO 作为唤醒源且代码/版本/时序与案例相符的场景；不能直接解释单独的 VIN/ISP、帧队列、冻结失败或 timer32 问题。
反证条件：若确认有效 GPIO IRQ 已执行对应 `__pm_wakeup_event()`、wakeup source 计数同步且修复前后 A/B 仍无差异，则不能继续把问题归因于该缺失调用；若 suspend 在任务冻结阶段已失败，也应先排除冻结问题。
遗留问题：历史资料中的原始状态、完整附件、精确 commit、板卡条件、样本数、时延统计方法和当前运行镜像是否包含修复均未提供。
```

## 使用规则

- 只有平台/版本、现象、复现条件和验证结果相符时，才能把本案例作为当前问题的直接参考。
- 案例中的“高可信候选”不是当前设备的自动根因结论；必须核对实际源码、构建产物和至少一组单变量 A/B 结果。
- 历史 pulse 延时、唤醒时延和修复版本只作为参照，不作为固定阈值或当前产品承诺。
- `AX_SYS_Sleep`、`GetDevFrame` 的返回值必须与同一周期的 kernel PM 日志和唤醒源计数关联，不能单独套用案例。
- 临时命令、寄存器值、驱动卸载和 workaround 必须记录适用硬件、原值、恢复方式和副作用。

## 快速匹配表

| 当前现象 | 可匹配案例前提 | 不能直接推出 |
| --- | --- | --- |
| 短时 GPIO 唤醒丢失，且 gpio_lp IRQ 与 PM wakeup event 不一致 | AX615、deep suspend、低功耗 GPIO 为唤醒源，版本和代码路径相符 | 不能仅凭丢帧或单条 error 判定为 内部案例 |
| wakeup_count 写回失败后仍请求 suspend | 应用层遵循同一 read/prepare/write 流程，且有并发 GPIO/timer 等事件证据 | 不能把所有写回失败都归因于 gpio_lp |
| `Freezing of tasks aborted` | 需先证明任务冻结失败路径，而不是把它当作 GPIO 唤醒证据 | 不能直接推出 wakeup-source 缺失 |
| 修复后唤醒时延变长 | 需要修复前后同一硬件、同一负载和同一计时边界的统计 | 不能仅凭时延增加判定修复回归或失败 |
