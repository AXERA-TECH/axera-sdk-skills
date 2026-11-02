# IVD Golden Case 评测集

`evals/` 存放 sdk-ivps-venc-diagnose 的离线评测用例（Golden Case）。每个 Case 的 `input/` 放现场采样文件，`answer/` 放评分契约，两者物理隔离。

## 输入约定

所有 Case 的现场输入统一为单文件 `input/hsk_proc.txt`：按 SKILL.md 第 1 节的采样 SOP，把 `link_table`、`link_table_kernel`、`syncagent`、`venc`、`jenc`、`ivps` 连续 `cat` 到同一文件；卡死类 Case 需含 `===== SAMPLE n =====` 标记的两轮采样（间隔 3~10 秒）。

## 用例配比（六类场景）

| Case | 六类场景 | 考察规则（SKILL.md 章节 / 故障矩阵行） | 数据来源 | 状态 |
|---|---|---|---|---|
| ivd-001 | 1 典型真实故障 | HSK 编码消费侧停滞：Send2EncCnt 领先 EncSucCnt 一帧在途、HwUsed=Y、编码侧 update 停 initVal 而 VPP 侧推进（决策树步骤 5） | captured：板端真实双轮采样（人工构造现场） | **可运行** |
| ivd-002 | 2 正常无误现场 | 各链路计数持续推进、HSK 节奏正常 → 输出"运行正常"（故障矩阵"正常与卡死的区别"） | captured：正常出流双轮采样 | **可运行** |
| ivd-003 | 3 相似症状不同根因 | 单支冻结：JENC chn1 支路停滞而 VENC chn0/chn2 与 IVPS 主链正常，只判停止分支，不判整组（决策树第 10 条） | derived：ivd-002 基底，S2 的 JENC 支路替换为 S1 | **可运行** |
| ivd-004 | 4 缺少关键证据 | 仅单次采样：可静态判读但"停滞"必须标"疑似"，并要求第二次采样；禁止断言持续卡死（第 1 节证据分级） | captured：真实单次采样 | **可运行** |
| ivd-005 | 5 矛盾数据 | link_table 声明 HSK 但 syncagent 无对应 session → 输出"拓扑/同步配置不一致"，优先排查 link 建立/解除顺序（第 2 节步骤 5） | derived：ivd-002 基底，删除两轮 SessId 0 块 | **可运行** |
| ivd-006 | 6 前置条件门禁 | HSK session State≠2 → 先报 session 未正常工作，不归因 VPP/VENC/JENC（决策树步骤 2） | derived：ivd-002 基底，sess0 State 改 1 + chn0 支路冻结 | **可运行** |

后备扩展（第二批次，按需增加）：一对二中 JENC 分支冻结；JENC `RatDrpCnt` 预期丢帧不判卡死；`EncSucCnt` 增长而 `ReadCycle` 冻结判用户态取流；`OutSts` 逼近 `OutDepth` 判 link 派发。

## 目录结构与评测方式

每个 Case 目录：

```
evals/cases/ivd-XXX/
├── case.yaml          # axap-eval 外壳：prompt（读当前目录 hsk_proc.txt 写 result.md）+ expect（result.md / assert.sh）
├── fixtures/          # axap-eval 工作区副本（hsk_proc.txt）——answer/ 不进 agent 工作区的机械隔离
├── input/hsk_proc.txt # 现场采样原件（盲测协议与 check_input 消费）
├── assert.sh          # 确定性断言（关键标记命中、禁错断言、answer 未泄漏）
└── answer/            # manifest.yaml + oracle.yaml，仅评分阶段可读
```

`case.yaml` 这个名字专属于 Case 根目录的 axap-eval 外壳；`answer/` 里的案例元数据命名为 `manifest.yaml`（axap-eval 会递归扫描 `case.yaml`，`answer/` 内出现同名文件会被当成未登记的第二个用例，用例发现可能失败）。

`fixtures/hsk_proc.txt` 与 `input/hsk_proc.txt` 内容必须一致，评测前需核对两份输入一致。新增 Case 时两处都放，并更新 `evals/suite.yaml`。

## 预检与判定

```bash
python3 scripts/validate_case.py ivd-001        # 结构与隔离正交性
python3 scripts/check_input.py evals/cases/ivd-001/input   # 现场完整性（含单次采样提示）
python3 scripts/validate_oracle.py evals/cases/ivd-001/answer/oracle.yaml
bash evals/cases/ivd-001/assert.sh              # 在含 result.md 的目录中执行
```

语义判定规则见 [references/grading.md](../references/grading.md)：Root cause / Required concepts / Forbidden conclusions / Evidence grounding / Confidence 五维，PASS/FAIL/ERROR 三态。关键故障用例（ivd-001）一票否决，不允许多次运行取多数。
