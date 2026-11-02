# sdk-ivps-venc-diagnose

诊断 AX615 IVPS(VPP/VGP) 到 VENC/JENC 编码器之间的链路卡死。输入 `/proc/ax_proc/link_table`、`link_table_kernel`、`syncagent`、`venc`、`jenc`、`ivps` 的 proc 采样，按 HSK 握手形态（`SW_Low_Mem`/`SW_Low_Latency`）与 `SW_Offline` 业务计数差值定位卡死模块。

Skill 正文在仓库顶层 SKILL.md，可供 Codex / Claude Code / OpenCode 等 agent 直接加载。

## 适用场景

- IVPS 出图正常但编码无输出、帧率掉零、某个编码通道停住。
- HSK 绑定的握手进度判读与 16 位模进度差值定位。
- `SW_Offline` 链路按 IVPS 输出与编码器收帧/送编码/取流的计数差值分段定位。
- 运行 IVD Golden Case 回归自检（`evals/`，Case ID `ivd-001`~`ivd-006`）。

## 评测材料

- `evals/cases/ivd-XXX/`：每 Case 含 `input/`（现场采样）、`fixtures/`（供 axap-eval 的工作区副本）、`answer/`（oracle，仅评分阶段可读）、`assert.sh`（确定性断言）与顶层 `case.yaml`（axap-eval 外壳）。

本交付包保留用例、预检脚本和独立断言，不提供原内部自动评测工作流。具体入口见 [评测说明](evals/README.md)；静态检查不等于模型或实板验证通过。
