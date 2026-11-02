# sdk-venc-rc-config-audit

审查 AX615/AX VENC 码控配置与可选码流结构。输入 `/proc/ax_proc/venc` 的 proc 快照、码控参数、码流文件或呼吸效应、码率偏高/超出、竞品对比、GOP/IP 比例、帧率异常等问题描述，按 CBR/VBR/AVBR/CVBR/FIXQP/QPMAP/智能编码的规则给出证据、风险和修改建议。

Skill 正文在仓库顶层 SKILL.md，可供 Codex / Claude Code / OpenCode 等 agent 直接加载。

## 适用场景

- 码控配置静态审查：字段合法性、字段间矛盾、当前模式生效参数。
- 呼吸效应、码率超出/偏高、GOP/IP 比例、帧率异常等问题的规则化排查。
- 有码流时用 ffprobe 统计实际结构并与 proc 配置逐项对照。
- 运行 RC Golden Case 回归自检（`evals/`，Case ID `rc-001`~`rc-006`）。

## 评测材料

- `evals/cases/rc-00X/`：每 Case 含 `input/`（proc 快照）、`fixtures/`（供 axap-eval 的工作区副本）、`answer/`（oracle，仅评分阶段可读）、`assert.sh`（确定性断言）与顶层 `case.yaml`（axap-eval 外壳）。

本交付包保留用例、预检脚本和独立断言，不提供原内部自动评测工作流。具体入口见 [评测说明](evals/README.md)；静态检查不等于模型或实板验证通过。
