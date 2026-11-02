# sdk-dataflow-analysis

分析 AX615/MC20L 模块间数据流转日志，定位 AX_SYS_Link_V2、HSK、LowMem/LowLatency/Offline link 参数或硬件拓扑约束导致的启动失败、断流或卡死。

Skill 正文在仓库顶层 ，可供 Codex / Claude Code / Grok / OpenCode 等 agent 直接加载。

## 适用场景

- 分析 FRTDemo、SYS、VIN、IVPS、VENC 数据流日志。
- 定位 AX_SYS_Link_V2 参数检查错误、IVPS→VENC/JENC HSK 资源冲突。
- 诊断 HSK 模式下的参数切换时序违规、多通道独立启停异常。
- 运行 AXDF Golden Case 回归自检。

## 脱敏约定

现场日志中的板卡地址统一替换为 `<board_ip>`，保留协议、端口、流路径、时间戳和诊断字段。
发布前核对现场日志和材料来源，保留诊断所需的协议、端口、时间戳及硬件字段。文本检查不代替资料授权、非文本材料和 Git 历史审查。

## 评测材料

`evals/` 保留 9 个 Case 的输入、元数据、oracle 和独立断言；本交付包不提供原内部自动评测工作流。`AXDF-009` 是输入不完整的负例，预期要求补采并拒绝确定归因。

每个 Case 的 `assert.sh` 检查输出的状态、关键结论、证据标记及缺失项。评测时输入和答案分离，结果按 [评分规则](references/grading.md) 核对；确定性断言不等同于完整语义评分。知识库中的 Golden Case 说明仍是运行知识的一部分，评测衡量技能对给定日志的应用，不宣称未知案例泛化或实板验证已通过。
