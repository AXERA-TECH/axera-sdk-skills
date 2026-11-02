# AX615 wakeup_count/gpio_lp 诊断输出模板

使用以下结构输出 `wakeup_count`/`gpio_lp` 诊断结论。缺失信息写“未提供，不能判断”，不要用历史案例或经验补全。快速诊断可直接填写此模板；需要完整案例复盘时，再结合主 `SKILL.md` 第 8 节的专用汇报模板。

```text
结论等级：已确认 / 高可信候选 / 待验证
问题层级：硬件/Boot / kernel/driver / 系统服务 / 中间件 / 应用 / 跨层
平台与版本：
硬件、低功耗 GPIO 与环境：

现象：
- 保留原始日志、错误码、GPIO pulse 参数和时间点

复现条件：
- suspend 类型：
- 是否使用应用层 wakeup_count：
- GPIO pulse 与业务负载：
- 复现次数/成功次数：

依据：
1. 日志、时间线或统计计数：
2. gpio_lp 代码路径、配置或构建产物：
3. wakeup_count 读写结果与 wakeup source/IRQ 计数：
4. 变更记录/测试证据：
5. 修复前后或单变量 A/B 结果：

机制：
- 只解释被现有证据支持的因果链；区分 GPIO IRQ、PM wakeup event、wakeup_count 写回、任务冻结和应用取帧。

验证方案：
1. 操作/命令：
   预期观察：
   对照变量：
   恢复方法：
2. 操作/命令：
   预期观察：
   对照变量：
   恢复方法：

反证条件：
- 如果确认有效 GPIO IRQ 已同步 PM wakeup source，但现象仍在，则不能继续把问题归因于缺失 `__pm_wakeup_event()`。
- 如果 `Freezing of tasks aborted` 发生在正常 suspend 之前，应先定位冻结阶段，不应直接归因于 GPIO 唤醒。
- 如果只有 `GetDevFrame` 错误而没有 GPIO/PM 时序证据，不能据此判定 suspend 根因。

边界：
- 当前证据不能推出：

下一步：
1. 必须补充的日志/配置/代码：
2. 需要硬件或平台协作的项目：
3. 通过判据（可靠性、进入 deep suspend、写回失败处理、唤醒延迟）：
```

## 结论等级定义

- **已确认**：有可重复证据，且实际源码、配置、运行产物与机制相互吻合；修复前后或反证测试排除了主要替代解释。
- **高可信候选**：现象、代码和机制高度一致，但仍缺少至少一项关键 A/B、复现或运行产物核对。本案例中“未调用 `__pm_wakeup_event()`”在未核对当前镜像时属于此等级。
- **待验证**：只有单次现象、单条日志、经验类比或不完整 Jira 资料支持，必须先补取证。

## 分层判定提醒

不要将以下现象直接等同于根因：

- 单条 `error`、非零返回值或一次性 crash；
- `AX_SYS_Sleep` 或 `GetDevFrame` 的单次错误码；
- `PM: suspend entry (deep)` 后很快 `PM: suspend exit`；
- `Freezing of tasks aborted` 中列出的任务名；
- 性能下降、丢帧、延迟增加或一次 GPIO 唤醒失败；
- 某个 Jira 标题、临时 workaround 或历史实验成功。

至少提供一个反证条件，并明确 GPIO 事件、timer32/其他唤醒源、任务冻结和 VIN/ISP 是否已区分。
