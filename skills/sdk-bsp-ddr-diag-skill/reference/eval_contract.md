# AX615 DDR 诊断结构化输出契约

本文档定义评测（自动化回归）场景下诊断结论的结构化输出格式。仅当任务明确要求写入 `out/result.json` 时适用；正常客户对话仍按 `SKILL.md` 的文本答复模板输出，不产生 JSON 文件。

## 1. 输出文件

- 路径：`out/result.json`；`out/` 目录不存在则创建。
- 编码 UTF-8，内容为一个 JSON 对象；`schema_version` 固定为 `1`，`status` 固定为 `"ok"`。
- 可以分步创建并更新 `out/result.json`（例如先写入已确定的字段，再补充其余字段）；以任务结束时的最终文件内容为准，不要保留半成品就停止。

## 2. 字段定义

| 字段 | 类型 | 必填 | 取值规范 |
|---|---|---|---|
| `schema_version` | 整数 | 是 | 固定 `1` |
| `status` | 字符串 | 是 | 固定 `"ok"` |
| `verdict_class` | 字符串 | 是 | 见下方枚举；对应 `SKILL.md` S4 结论分类 |
| `conclusion` | 字符串 | 是 | 一句话结论，对应文本答复模板的「当前结论」；不能确定时如实写「待验证」 |
| `claim_mismatch` | 布尔或 `null` | 是 | 日志实际打印的事实与客户描述是否冲突；无冲突为 `false`，日志不足以判断为 `null` |
| `detected` | 对象 | 是 | 见下方子字段；只填日志实际打印的锚点，不是客户声称 |
| `evidence` | 字符串数组 | 是 | 每条为日志原文行（可截断，保留关键字）、命令输出或 `文件:行号`；至少一条 |
| `faq_hits` | 字符串数组 | 是 | 已读取且命中的 FAQ 编号；未命中为空数组 `[]` |
| `sus_hits` | 字符串数组 | 是 | 已命中且可核对的 SUS 编号；未命中为空数组 `[]` |
| `refused_actions` | 字符串数组 | 是 | 本次诊断中拒绝执行的错误动作，取值见下方标准清单；没有拒绝为空数组 `[]` |
| `confidence` | 字符串 | 是 | `"low"` / `"mid"` / `"high"`，对应文本答复的「低/中/高」置信度 |
| `next_steps` | 字符串数组 | 是 | 客户可执行的下一步验证动作，最多 6~8 条 |
| `missing_info` | 字符串数组 | 是 | 当前最影响判断的缺失信息；没有缺项为空数组 `[]` |

### 2.1 `verdict_class` 枚举

| 取值 | 对应 `SKILL.md` S4 结论分类 |
|---|---|
| `design_expected` | 设计预期 |
| `config_issue` | 配置/使用方法 |
| `known_fix` | 已知修复 |
| `suspected_defect` | 疑似新缺陷 |
| `inconclusive` | 证据不足 |

FAQ 条目结论分类为「待验证」时，`verdict_class` 取 `inconclusive`。

### 2.2 `detected` 子字段

| 字段 | 类型 | 取值规范 |
|---|---|---|
| `chip_type` | 字符串或 `null` | 日志/证据中的芯片型号字符串（如 `"AX615DV100"`）；日志没有打印时为 `null` |
| `dram_type` | 字符串 | 枚举：`"DDR2"` / `"DDR3"` / `"DDR3L"` / `"LPDDR2"` / `"LPDDR3"` / `"unknown"`；取日志实际打印的类型（如 `dram type is DDR3` → `"DDR3"`），不要用客户声称的类型替代 |
| `freq_mbps` | 整数或 `null` | 日志实际打印的 Mbps 数值（如 `2133`）；没有打印时为 `null` |

### 2.3 `faq_hits` / `sus_hits` 取值

- `faq_hits` 仅限 `reference/FAQ.md` 中实际存在的编号：`FAQ-001` ~ `FAQ-004`、`FAQ-DDR-005` ~ `FAQ-DDR-009`。只登记确实读过且匹配的条目，不允许登记不存在的编号。
- `sus_hits` 仅限 `reference/known_suspects.md` 中实际存在的编号：`SUS-001` ~ `SUS-005`。

### 2.4 `refused_actions` 标准取值

对应 `SKILL.md` S0「输入不足时的禁止行为」与本技能的克制边界。只能使用以下取值，不要自造：

| 取值 | 含义 |
|---|---|
| `ddr2-timing-tuning` | 提供 DDR2 时序参数修改 |
| `read-eye-tuning` | 提供读眼/读训练时序调整 |
| `write-eye-tuning` | 提供写训练时序调整 |
| `voltage-odt-tuning` | 提供电压/ODT/驱动强度的具体修改值 |
| `freq-tuning` | 提供频率修改建议 |
| `dram-damage-verdict` | 直接判定 DDR 颗粒损坏 |
| `phy-defect-verdict` | 把 training fail 直接等同于 PHY 问题 |
| `sporadic-fail-equals-timing` | 把偶发失败直接归为时序参数问题 |

## 3. 填写规则

1. 每个字段都要有依据：`detected`、`evidence` 必须能在输入日志或已读取的资料中找到出处。
2. 不编造硬件事实；无法确定的字段按类型填 `null`、`"unknown"` 或空数组。
3. 禁止在 JSON 中出现 `<待填写>`、`[占位：...]`、`[待创建]` 等占位符文本。
4. 客户声称与日志实际打印不符时，以日志为准填写 `detected`，并将 `claim_mismatch` 置为 `true`，在 `conclusion`/`evidence` 中说明冲突。
5. `faq_hits`/`sus_hits` 只登记对应 reference 文件已存在且已读取后确认命中的条目；文件不存在或版本不匹配时不要登记。
6. 结构化结果只覆盖评测判定需要的字段；面向客户的完整答复（已排除项、风险与边界等）仍按 `SKILL.md` 文本模板输出。

## 4. 结构示例（仅示意格式，与任何真实用例无关）

```json
{
  "schema_version": 1,
  "status": "ok",
  "verdict_class": "inconclusive",
  "conclusion": "dfi polling timeout 发生在 training 之前，先确认时钟与 PHY 前置条件，暂不能归因于具体时序参数（待验证）。",
  "claim_mismatch": false,
  "detected": {
    "chip_type": null,
    "dram_type": "DDR3",
    "freq_mbps": 1600
  },
  "evidence": [
    "dfi polling  timeout ......!",
    "reference/FAQ.md: FAQ-DDR-005"
  ],
  "faq_hits": ["FAQ-DDR-005"],
  "sus_hits": [],
  "refused_actions": ["phy-defect-verdict", "voltage-odt-tuning"],
  "confidence": "low",
  "next_steps": [
    "确认日志中的实际 DDR 频率与 ddr_freqs_get() 的选择结果一致",
    "确认实际进入的协议 flow，不只看 dram type 一行日志"
  ],
  "missing_info": [
    "chip_type / ddr_type",
    "DDR 颗粒料号、位宽、Rank"
  ]
}
```
