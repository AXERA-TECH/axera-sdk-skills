# Golden Case 判定规则

按语义判定，不要求分析结果复述 oracle 原文。先应用 `evaluation_notes`；其约束高于其他字段，可声明某个隐藏值不要求、不可推断或仅用于 evaluator 确认。

本文件服务于 `sdk-vo-analysis` 的 Golden Case。`root_cause` 字段按 Case 类别承载不同语义：诊断类 Case（`AXVO-analysis-*`）表示期望的**根因结论**；配置生成类 Case（`AXVO-setting-*`）表示期望生成结果的**核心内容**（关键参数值、调用序列要点、能力结论）。其余字段语义通用。

## 判定项

### Root cause（配置生成类为 Expected config）

分析结论/生成结果必须与 `root_cause` 的故障对象、错误配置或条件、失败机制和直接结果一致（配置生成类：与期望的关键参数值、预设/表条目命中、能力结论一致）。oracle 中仅由 evaluator-only 材料确认、且 `evaluation_notes` 明确不要求推断的具体值，不作为缺失项。

### Required concepts

逐条检查 `required_concepts`。等价表述算 matched；只提到术语、但没有表达该条关系或约束，算 missing。全部 matched 才通过此项。

### Forbidden conclusions

检查分析结果/生成配置是否将 `forbidden_conclusions` 中任一项断言为结论或写入配置。明确排除、否定或作为后续噪声说明不算 asserted。出现任一 asserted 即失败。配置生成类的禁止项通常是不合法的参数值（如不在 PCLK 离散档位表的时钟值、AX615D 不能支持的接口组合）。

### Evidence grounding

分析结果引用的参数值、返回码、proc 字段、时序表条目名必须能在 `analyzer_visible` 输入或本 skill 内化 references 中找到。`evidence_signatures` 用于确认 Case 场景文本含关键证据，不要求逐字出现在分析结果中。捏造场景不可见的参数值、日志或状态即失败；由约束和可见证据推出的结论可以标为推断。引用时序表/PCLK 表/行为摘要时须带固定版本标注。内化 references 条目只支持**事实确认**；把事实连成"本次故障"的因果链需要 `analyzer_visible` 输入中的现场证据（返回值/日志/proc/现象），仅引用文档条目不足以判根因成立。

### Confidence

将分析结果的置信度与 `expected_confidence` 对比。一致则 `PASS`，不一致则 `WARN` 并说明原因。置信度差异本身不改变总 verdict。

## 总 verdict

- `PASS`：Root cause、Required concepts、Forbidden conclusions、Evidence grounding 全部通过。
- `FAIL`：上述四项至少一项失败。
- `ERROR`：Case 结构无效、预检失败、对应分析 Skill 不存在、Skill 调用失败或没有产生可评测结果。

评测不得用 oracle 替分析结果补齐缺失概念。分析结果为 `INCONCLUSIVE`、而 oracle 期待可确定根因时，Root cause 判 `FAIL`；如果 oracle 本身标注为不可确定，则按其标注判断。

## 批量评测

批量跑多个 Case 时，必须先把**全部** Case 的分析结果冻结为 `analyzer_result`，之后才进入评分阶段读取各 Case 的 `answer/`。不得边分析边评分，也不得在读取任一 Case 的 oracle 后回头修改其他 Case 的冻结结果；若某个 Case 的分析阶段已接触答案，该 Case 结果作废。

## 输出格式

```text
Case: <id>
Verdict: PASS | FAIL | ERROR

Analyzer result:
<冻结的原始输出>

Comparison:
- Root cause: PASS | FAIL — <原因>
- Required concepts: PASS | FAIL — matched [...]; missing [...]
- Forbidden conclusions: PASS | FAIL — asserted [...]
- Evidence grounding: PASS | FAIL — <原因>
- Confidence: PASS | WARN — expected <...>; actual <...>

Summary: <一两句话>
```
