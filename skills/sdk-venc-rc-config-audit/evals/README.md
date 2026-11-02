# RC Golden Case 评测集

`evals/` 存放 sdk-venc-rc-config-audit 的离线评测用例（Golden Case）。每个 Case 的 `input/` 放现场 proc 快照，`answer/` 放评分契约，两者物理隔离。

## 输入约定

所有 Case 的现场输入统一为单文件 `input/venc_proc.txt`：按 SKILL.md 第 1 节的采集约定，一次 `cat /proc/ax_proc/venc` 的输出（本 skill 解析单次 proc，不要求两次采样）。现场现象（用户反馈）通过 Case 根目录 `case.yaml` 的任务提示词提供，不在 proc 内。

## 用例配比（六类场景）

| Case | 六类场景 | 考察规则（SKILL.md 章节 / references） | 数据来源 | 状态 |
|---|---|---|---|---|
| rc-001 | 1 典型真实故障 | CBR 呼吸效应：MaxIQp=30 偏低 + IpropMax=100 + GOP=25@25fps 周期 1 秒（symptom-rules 呼吸效应节） | synthetic：按 proc 列宽构造 | **可运行** |
| rc-002 | 2 正常无误现场 | 正常 CBR 基线：QP 合法、帧率偏差 <10%、码率偏差 <10% → 必须输出"正常"，防误报（SKILL.md 公共规则） | synthetic | **可运行** |
| rc-003 | 3 相似症状不同根因 | 双通道同为码率超出约 20%：chn0 QP 上限过低 vs chn1 目标码率偏低，必须分通道归因（symptom-rules 码率超出节） | synthetic | **可运行** |
| rc-004 | 4 缺少关键证据 | proc 无 `[SDK version]` 行 + 未描述现象 → 版本标"未知（未经确认）"、审查后询问现象，禁止虚构（SKILL.md §2.1、§1） | synthetic：去掉版本头行 | **可运行** |
| rc-005 | 5 矛盾数据 | DstFr=25 但 OutFps=12.4 减半、RecvFps 正常 → 报配置/实测矛盾，给候选方向并要求码流确认，不得断言唯一根因（symptom-rules 帧率节） | synthetic | **可运行** |
| rc-006 | 6 次生噪声干扰 | 三通道：chn1 QP 范围颠倒为唯一真错误，chn2 QVBR 的 `-` 占位按未知处理不当异常（SKILL.md 公共规则"未知"） | synthetic | **可运行** |

后备扩展（第二批次，按需增加）：码流分析类 case（需先确认评测环境提供 ffprobe）；VBR/AVBR 静态场景偏码率；JENC（MJPEG）质量参数审查；SVC 智能编码 AbsQp 用反场景。

## 目录结构与评测方式

每个 Case 目录：

```
evals/cases/rc-00X/
├── case.yaml          # axap-eval 外壳：prompt（读当前目录 venc_proc.txt 写 result.md，现场现象随 prompt 给出）+ expect（result.md / assert.sh）
├── fixtures/          # axap-eval 工作区副本（venc_proc.txt）——answer/ 不进 agent 工作区的机械隔离
├── input/venc_proc.txt # 现场快照原件（盲测协议与 check_input 消费）
├── assert.sh          # 确定性断言（关键标记命中、禁错断言、answer 未泄漏）
└── answer/            # manifest.yaml + oracle.yaml，仅评分阶段可读
```

`case.yaml` 这个名字专属于 Case 根目录的 axap-eval 外壳；`answer/` 里的案例元数据命名为 `manifest.yaml`（axap-eval 会递归扫描 `case.yaml`，`answer/` 内出现同名文件会被当成未登记的第二个用例，用例发现可能失败）。

`fixtures/venc_proc.txt` 与 `input/venc_proc.txt` 内容必须一致，评测前需核对两份输入一致。新增 Case 时两处都放，并更新 `evals/suite.yaml`。

## 预检与判定

```bash
python3 scripts/validate_case.py rc-001        # 结构与隔离正交性
python3 scripts/check_input.py evals/cases/rc-001/input   # 现场完整性（含版本行缺失提示）
python3 scripts/validate_oracle.py evals/cases/rc-001/answer/oracle.yaml
bash evals/cases/rc-001/assert.sh              # 在含 result.md 的目录中执行
```

语义判定规则见 [references/grading.md](../references/grading.md)：Root cause / Required concepts / Forbidden conclusions / Evidence grounding / Confidence 五维，PASS/FAIL/ERROR 三态。关键故障用例（rc-001）一票否决，不允许多次运行取多数。
