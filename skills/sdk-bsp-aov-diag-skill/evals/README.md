# AX615 AOV 低功耗休眠唤醒 Skill 评测集 (Evals)

本目录为 `sdk-bsp-aov-diag-skill` 的评估评测套件，用于测试和验证大模型在诊断 AX615 Linux 深度休眠（deep suspend）中 `wakeup_count` 与低功耗 GPIO（`gpio_lp`）唤醒中断异常时的专业性、纪律性与准确率。

## 1. 评测集设计原则

根据 BSP 技能工程规范与诊断约束，评测集重点考核以下核心能力：

1. **证据驱动与等级划分**：区分“已确认”、“高可信候选”与“待验证”，禁止在缺乏构建产物与镜像核对时直接将历史案例断定为当前事实。
2. **缺失信息诚实处理**：凡缺少日志、版本、GPIO 编号、板卡配置的项，必须标注“未提供，不能判断”，严禁用经验脑补。
3. **问题分层定位**：能够准确划分硬件/Boot、kernel/driver、系统服务、中间件/应用层级，不混淆层级界限。
4. **反证条件与 A/B 验证**：每个分析结论必须提供支持证据、反证条件和最小单变量 A/B 对照验证方案。
5. **常见误判识别与防御**：
   - 区分“GPIO 唤醒丢中断”与“`Freezing of tasks aborted` 任务冻结失败”；
   - 区分底层内核 PM resume 与上层 `GetDevFrame` 取帧超时；
   - 识别应用层 `cat /sys/power/wakeup_count > /sys/power/wakeup_count` 的协议缺陷；
   - 兼顾“唤醒可靠性”与“唤醒延迟”，防范时延回归。

## 2. 评测用例矩阵

| 用例 ID | 名称 | 分类 | 考核重点 |
| --- | --- | --- | --- |
| `eval-01-missing-wakeup-event` | 短时GPIO唤醒丢中断与__pm_wakeup_event缺失排查 | 根因分析 | 识别 gpio_lp handler 缺失 `__pm_wakeup_event`，高可信候选定级，A/B 方案 |
| `eval-02-wakeup-count-protocol-race` | wakeup_count错误简化用法与并发时序竞态分析 | 协议与时序分析 | 识别 `cat >` 破坏两阶段协议，解释写回失败的保护机制与标准休眠时序 |
| `eval-03-freeze-tasks-aborted` | Freezing of tasks aborted 任务冻结失败排除误判 | 误判排除 | 纠正测试人员将任务冻结失败误当 GPIO 丢中断的错误，定位 D 状态任务 |
| `eval-04-getdevframe-misdiagnosis` | GetDevFrame取帧超时误当GPIO唤醒故障的跨层排除 | 跨层隔离 | 隔离内核 PM resume 与图像 pipeline（VIN/ISP），避免单一归咎底层 |
| `eval-05-wakeup-latency-regression` | 修复丢中断后唤醒延迟变长的A/B评估与分析 | 性能时延回归 | 可靠性与延迟权衡，统一度量边界，多轮单变量 A/B 测量 |
| `eval-06-driver-lifecycle-leak-check` | gpio_lp驱动生命周期与wakeup_source注销泄漏检查 | 代码审查 | 审查 probe unwind 与 remove 中缺失 `wakeup_source_unregister` 的泄漏漏洞 |
| `eval-07-evidence-constraint-and-defensive-diag` | 信息缺失场景下的证据驱动与防御性排查要求 | 证据与纪律性 | 面对极简信息拒绝脑补补丁，输出安全取证清单与结构化分层假设 |

## 3. 文件清单

- `evals.json`：全量测试用例集合，包含 prompt、expected_output 与 criteria 评分项。
- `run_evals.py`：评测集校验与格式检查脚本。
