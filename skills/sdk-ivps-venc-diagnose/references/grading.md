# Golden Case 判定规则

按语义判定，不要求分析结果复述 oracle 原文。先应用 `evaluation_notes`；其约束高于其他字段，可声明某个隐藏值不要求、不可推断或仅用于 evaluator 确认。

## 判定项

### Root cause

分析结论必须与 `root_cause` 的故障对象、错误配置或条件、失败机制和直接结果一致。oracle 中仅由 evaluator-only 材料确认、且 `evaluation_notes` 明确不要求推断的具体值，不作为缺失项。

### Required concepts

逐条检查 `required_concepts`。等价表述算 matched；只提到术语、但没有表达该条关系或约束，算 missing。全部 matched 才通过此项。

### Forbidden conclusions

检查分析结果是否将 `forbidden_conclusions` 中任一项断言为根因或主要原因。明确排除、否定或作为后续噪声说明不算 asserted。出现任一 asserted 即失败。

### Evidence grounding

分析结果引用的日志、返回码、模块 tuple、状态和时序必须能在 `analyzer_visible` 输入中找到。`evidence_signatures` 用于确认 Case 输入含关键证据，不要求逐字出现在分析结果中。捏造 input 不可见的参数值、日志或状态即失败；由约束和可见证据推出的结论可以标为推断。

### Confidence

将分析结果的置信度与 `expected_confidence` 对比。一致则 `PASS`，不一致则 `WARN` 并说明原因。置信度差异本身不改变总 verdict。

## 总 verdict

- `PASS`：Root cause、Required concepts、Forbidden conclusions、Evidence grounding 全部通过。
- `FAIL`：上述四项至少一项失败。
- `ERROR`：Case 结构无效、输入完整性检查失败、对应分析 Skill 不存在、Skill 调用失败或没有产生可评测结果。

评测不得用 oracle 替分析结果补齐缺失概念。分析结果为 `INCONCLUSIVE`、而 oracle 期待可确定根因时，Root cause 判 `FAIL`；如果 oracle 本身标注为不可确定，则按其标注判断。
