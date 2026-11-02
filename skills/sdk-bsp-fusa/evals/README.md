# 验收用例（evals/）

本目录是 `sdk-bsp-fusa` 的**验收用例集**。用途：任何一次改动 `SKILL.md`、`references/*.md` 之后，
用它确认这个 skill 的判定能力没有退化——尤其是三条硬闸门（S0 输入闭合、S1 平台判定、S2 归属定位）
和两条铁律（不落盘改源码、不跨平台套结论）。

目录名 `evals/` 与 `skills/` 组织下其它 skill（`sdk-axck-test`、`sdk-axck-diag`、`sdk-dataflow-analysis`）保持一致。

## 目录结构

```
evals/
├── README.md            本文件：验收方式、盲测纪律、判定规则、执行话术、维护规范
├── evals.json           标准 evals（与 sdk-axck-* 同构，供外部评测框架读取）
├── trigger-evals.json   触发与跨 skill 边界用例（本 skill 是 explicit activation）
├── run_evals.py         确定性校验器：结构、隔离、编号、跨平台串味（不调用 LLM）
└── FUSA-00x/            盲测 Golden Case
    ├── input/           现场材料：分析阶段唯一可读的内容
    └── answer/          case.yaml（元数据 + 隔离声明）、oracle.yaml（期望结论）
```

## 两条验收轨道

`suite.yaml` 和 `cases/` 保留从 FUSA-002、005、007 输入构造的三个行为场景，分别验证 Linux 归属、输入门禁和 QNX 服务缺失。原有 7 套 Golden Case 保持不变；三个核心行为断言不代替完整语义评分。本交付包提供评测材料，不提供原内部自动评测工作流。

### 轨道 A · 确定性校验（可自动跑，不含 LLM）

```sh
python3 <skill-dir>/evals/run_evals.py
```

`run_evals.py` 检查的是**能被机械判定的事实**，不判语义对错：

| 检查项 | 判据 |
|---|---|
| SKILL.md 前置元数据 | `name: sdk-bsp-fusa`、`activation: explicit`、description 非空且足够长 |
| 参考文件完整性 | SKILL.md 里引用到的 `references/*.md` 全部存在（`<平台>` 这类占位名被跳过） |
| evals.json / trigger-evals.json 结构 | 必填字段齐全；trigger 集必须同时含 `should_trigger: true` 与 `false` |
| Case 结构 | `input/` 非空；`answer/case.yaml` + `answer/oracle.yaml` 存在且必填键齐全 |
| 隔离声明 | `analyzer_visible` 只能列 `input/` 下真实存在的文件，且必须覆盖 `input/` 的全部文件；`evaluator_only` 必须含 `answer/case.yaml`、`answer/oracle.yaml` |
| 证据可溯源 | `oracle.evidence_signatures` 的每个文件都必须出现在 `analyzer_visible` 里 |
| 跨平台串味 | Linux Case 的答案正文（`root_cause`/`required_concepts`/`required_actions`）不得出现另一平台特征（`/proc/ax_diag`、`QNX_V*`、`pidin`、`hogs`）；QNX Case 不得出现 `sysfs` 节点路径、内核 `Kconfig/.config` 这类另一平台手段。`platform: unknown` 的 Case 跳过此项；平台纠偏场景在 `case.yaml` 里声明 `lint.allow_cross_platform: true` 豁免 |
| FAQ 编号纪律 | Linux Case 的答案不得出现补零编号 `FAQ-0N`（那是 QNX 的形态） |
| 元数据一致性 | `case.yaml` 的 `id` 必须等于目录名；`case.yaml` 与 `oracle.yaml` 的 `platform` 必须一致（防止只改一边导致平台漂移） |
| 盲测隔离 | 预检只打印 `input/` 清单，绝不打印 `answer/` 下任何路径或内容 |

用法变体：

```sh
python3 evals/run_evals.py                 # 跑全部检查
python3 evals/run_evals.py --list FUSA-001  # 预检单个 Case，只输出可读文件清单
python3 evals/run_evals.py --case FUSA-001  # 只做该 Case 的结构与隔离检查
```

退出码 `0` = 全部通过；`1` = 有 FAIL。

<EXTREMELY-IMPORTANT>
**负面测试（临时构造 Case）不要在仓库里和全量校验并行跑。**
`run_evals.py` 会扫描 `evals/` 下所有 `FUSA-0NN` 目录，并行执行时临时 Case 会被全量校验一起扫到，
导致「验收结论被自己的测试污染」。做法：把 `SKILL.md`、`references/`、`evals/` 拷到 `/tmp` 的临时树里做负面测试，
或者串行执行并在结束前确认临时目录已清理。
</EXTREMELY-IMPORTANT>

### 轨道 B · Golden Case 盲测（语义判定，靠 agent 执行）

`evals/FUSA-00x/` 是盲测题。执行方式见 SKILL.md 的「验收自检」章节。一句话：
**先只看 `input/`，按正常排查流程作答并冻结结论，之后才允许读 `answer/` 评分。**

## 盲测纪律

答案和输入在同一个 skill 目录里，隔离靠**执行顺序**保证，不靠目录边界。因此：

<EXTREMELY-IMPORTANT>
进入评分阶段之前，不得以任何方式读取该 Case `answer/` 下的任何文件（`case.yaml`、`oracle.yaml`），
**也不得读 `evals/evals.json`（它含 `expected_output` / `expectations`，等价于答案）**；
**本文件（`evals/README.md`）同样在答案侧**——下面的「Case 清单」写着每题的考点，会泄题。
也不得通过全文检索、grep、`--list` 之外的输出猜测答案。一旦提前读到，这次自检结论作废，
必须换一个没读过答案的 Case 重跑。

**最稳的做法是物理隔离**：给执行者一个只含 `SKILL.md` + `references/` + 该 Case `input/` 的目录
（如 `/tmp/blind-run/<CASE>/`），`answer/`、`evals.json`、本 README 都不放进去，并让执行者以该目录为工作目录。
2026-09-20 的三次盲测都按此执行（每次沙箱 19 个文件、泄漏检查为 0）。
</EXTREMELY-IMPORTANT>

单个 Case 的作答与评分必须在同一轮内完成，且**一次只跑一个 Case**：批量跑时逐 Case 冻结、逐 Case 评分，
`FUSA-00x` 的 oracle 不得用来评判另一个 Case。

**常见反模式（见到就作废）**：出题人自评、边看 oracle 边答、答完回头改答案、要求逐字复述 oracle、
把 `evals/evals.json` 当题面读、多 Case 共用一次冻结。

## 执行步骤

**执行者（analyzer，必须没读过答案）只做第 1–3 步；第 4–5 步由维护者做。** 不要让执行者自己看 oracle 自评。

1. 预检：`python3 <skill-dir>/evals/run_evals.py --list FUSA-001`
   失败（`ERROR`）时不进入分析，先修 Case。
2. 只读取预检给出的 `analyzer_visible` 文件，按 SKILL.md 的 S0→S6 流程正常排查，把自己当作一个没有答案的排查者。
3. 把输出**冻结**成 `analyzer_result`。冻结之后不得依据答案补写、删改或重跑。
4. **维护者**此时才读 `answer/oracle.yaml`，按下面的「判定规则」做语义比对。
5. **维护者**按固定格式输出结论（见下）。

## 执行话术（交接给盲测执行者）

盲测必须由**没读过答案**的人（或一个全新进程）执行。**执行者只负责分析并冻结，评分由维护者做。**

**方式一 · 交互式会话**：把下面整段发给执行者（agent）：

```text
请对 sdk-bsp-fusa 执行一次盲测，Case = FUSA-002。你只做分析，不要评分、不要读答案。

严格按顺序：
1. 运行：python3 evals/run_evals.py --list FUSA-002
2. 只读它列出的 input/ 文件，加载 /sdk-bsp-fusa，按 SKILL.md 的 S0–S6 正常排查，输出完整结论。
   此阶段禁止读取或检索 evals/*/answer/、evals/evals.json、evals/README.md、以及其它 Case 的内容。
3. 把第 2 步的输出原样冻结为 analyzer_result，之后不得增删改或重跑；输出完就停。
```

**方式二 · 独立 CLI 进程（2026-09-20 实测可用，推荐用于正式验收）**：给执行者一个只含 `SKILL.md` + `references/` + 该 Case `input/` 的沙箱，
用 `codex exec` 以只读沙箱跑同一段提示词，结果用 `-o` 落盘，再由维护者评分：

```sh
CASE=FUSA-002; D=/tmp/blind-run/$CASE; SRC=<skill-dir>
rm -rf $D && mkdir -p $D
cp $SRC/SKILL.md $D/ && cp -r $SRC/references $D/ && cp -r $SRC/evals/$CASE/input $D/
find $D -name '*oracle*' -o -name 'case.yaml' -o -name 'README.md'   # 必须为空
codex exec -p llmproxy -C $D -s read-only --skip-git-repo-check \
  -o /tmp/result_$CASE.txt "$(cat prompt_$CASE.txt)" < /dev/null
```

**环境事实（2026-09-20 实测，省得重复踩）**：

| 事实 | 说明 |
|---|---|
| `claude -p` 当前不可用 | 经路由到 `glm-5.3[1m]` 时稳定报 `API Error: Content block is not a thinking block`（28–38 秒即退）；覆盖模型后能跑但会卡住不出结果 |
| `codex` 必须用 `-p llmproxy` | 默认 provider `axera` 报 `Selected model is at capacity`；`-p apirouter` 报 `401 Invalid token`；`-p llmproxy` 实测连续三次成功 |
| 单 Case 耗时 | 约 2–3.5 分钟（`gpt-5.6-sol`，medium effort），冻结件 3–5 KB |
| 命令要加 `< /dev/null` | 否则 CLI 会去读 stdin 并打印 `no input` 警告 |

推荐首跑 `FUSA-002`；时间充裕再跑 `001`、`004`。**一次只跑一个 Case。**

可选：再把下面这段发给第三个没读过答案的人，复核评分有没有放水。

```text
请复核这次盲测评分是否放水或过严：
- 只看执行者冻结的 analyzer_result 与该 Case 的 answer/oracle.yaml；
- 逐项确认 required_concepts 是"表达了关系"而非"提到术语"；
- 确认 forbidden_* 的命中判定：明确排除/否定不算 asserted；
- 确认 evidence grounding 没有把 oracle 里的内容算成执行者说的；
- 若与维护者的评分不一致，指出分歧项与理由。
```

归档至少记 6 项：日期 / 被验版本（commit + 工作区摘要）/ 执行者（含"未读过答案"确认）/ Case + Verdict / 失败项 / 处置与重跑结果。`PASS` 也要记。

失败分类处置：skill 知识或流程退化 → 改 `SKILL.md` 或 `references/` 后重跑轨道 A 与该 Case；
oracle 过严或含糊 → 改 `oracle.yaml` 并跑 `run_evals.py`；执行者越界 → 该次结论作废，换人重跑；
素材不足 → 补 `input/`（**绝不补答案**）。

## 判定规则（语义比对）

### Linux 验收口径（2026-10-15）

Linux 单平台验收只运行 `FUSA-001`、`FUSA-002`、`FUSA-006`，另用 `FUSA-005` 检查输入不足时的处理；
`FUSA-003`、`FUSA-004`、`FUSA-007` 属于 QNX 场景，跳过且不计入通过率。

本口径优先于下方逐项全过的判定方式。验收看核心判断是否正确、证据是否真实、处理方向是否可用，
不要求逐字复述 oracle，也不要求把每条参考知识写成教程。阶段标签、FAQ 编号格式、置信等级、
解释深度、重复的平台依据，以及不影响判断的参数或建议遗漏，只记 `WARN`，不因此改 skill。
`required_*` 用作核对清单；遗漏只有导致核心判断错误、关键处理不可用或明显误导客户时才判 `FAIL`。

以下问题仍判 `FAIL`：混淆平台并给出不适用的操作，把 ISP 等模块事件误判成心跳，
把普通计数当成已上报故障，无依据地宣称配置生效或故障已排除，编造证据，实际修改 FuSa 源码，
或给出会明显扩大故障的操作。输入不足时应保留不确定性；一次简短追问即可，不要求复述全部缺失项。

除题面和 references 外，用户提供的 SDK 也可作为只读代码证据，引用时写清实际路径和行号。
参考源码只能证明该工作区的实现，不能据此宣称客户板端已运行相同代码。
先冻结作答再评分的要求保留；各题分别作答和冻结，评分者可在全部冻结后统一评分。
有分歧先核实题面、oracle 和代码；只有严重事实错误才修改原 skill，不为满足措辞或格式改流程。

按语义判定，**不要求复述 oracle 原文**。先应用 `evaluation_notes`：它的约束高于其它字段，
可声明某个值不要求、不可推断，或仅用于 evaluator 确认。

### QNX 验收口径（2026-10-15）

QNX 单平台验收运行 `FUSA-003`、`FUSA-004`、`FUSA-007`，另用 `FUSA-005` 检查输入不足时的处理。
沿用上面的宽松语义口径：核心判断、证据和关键处理正确即可；阶段标签、编号格式、置信等级、
参考知识未逐项展开等非实质缺项只记 `WARN`。本口径优先于下方逐项全过的要求。
平台混淆、错误归属、编造证据、无依据保证升级必然解决或宣称已排除故障、实际修改 FuSa 源码，
以及会明显扩大故障的操作仍判 `FAIL`。查不到关键词应保留不确定性，不要求盲目穷举目录或原语。
允许引用用户提供的 QNX SDK，只读源码仅证明该工作区实现，不能代替旧版客户代码、板端部署或发布历史。
修复版本可以引用现有 FAQ，但需区分资料记载与本轮独立验证；不能为了符合 oracle 承诺升级后所有异常消失。
逐题冻结、答案隔离和不替回答补写的要求保留；评分者可在全部冻结后统一评分。

### 判定项

| 判定项 | 通过条件 |
|---|---|
| **Platform**（平台判定） | 与 `platform` 一致；判不出平台时必须走勾选或追问，不得猜。`expected_stage: S0/S1` 的 Case 允许结论为「待平台确认」，但依据必须与 oracle 的判据一致。 |
| **Root cause** | 故障对象、错误配置或条件、失败机制、直接结果与 `root_cause` 一致。 |
| **Required concepts** | 逐条检查 `required_concepts`。等价表述算 matched；只出现术语、但没有表达该条关系或约束，算 missing。全部 matched 才通过。 |
| **Required actions** | 逐条检查 `required_actions`（该做的动作，如「追问日志上下文」「FCU 命令带 timeout」「给客户配置层规避方法」）。全部做到才通过。 |
| **Recommended concepts** | 逐条检查 `recommended_concepts`（可选字段）。缺项只判 `WARN` 并在报告里写明，**不改变总 verdict**。 |
| **Recommended actions** | 逐条检查 `recommended_actions`（可选字段）。缺项只判 `WARN`，**不改变总 verdict**。 |
| **Forbidden conclusions** | 把 `forbidden_conclusions` 任一项断言为根因或主因即失败。明确排除、否定、或作为后续噪声提到不算 asserted。 |
| **Forbidden actions** | 做了 `forbidden_actions` 里任一动作即失败（如落盘改 `.c`/`.h`、给出另一平台的路径或命令、编造修复版本号、在硬判据单边命中时仍弹平台勾选）。 |
| **Evidence grounding** | 引用的日志、返回值、路径、行号必须能在 `analyzer_visible` 输入或本 skill 的 `references/` 里找到。捏造输入中不可见的参数值、日志、代码行号即失败；由约束推出的结论可标为「推断」。 |
| **Confidence** | 与 `expected_confidence` 一致判 `PASS`，不一致判 `WARN` 并说明原因。置信度差异本身不改变总 verdict（`n/a` 表示该 Case 不评此项）。 |

### 总 verdict

- `PASS`：Platform、Root cause、Required concepts、Required actions、Forbidden conclusions、Forbidden actions、Evidence grounding 全部通过。
- `WARN` 只记录、不改变总 verdict：`Confidence` 与 `expected_confidence` 不一致，或 `recommended_concepts` / `recommended_actions` 缺项。
- `FAIL`：上述任一项失败。
- `ERROR`：Case 结构无效、预检失败、skill 无法加载、或没有产生可评测结果。

评测**不得用 oracle 替分析结果补齐缺失概念**。分析结果给不出结论、而 oracle 期待可确定结论时，Root cause 判 `FAIL`；
oracle 本身标注不可确定（如 `root_cause: INCONCLUSIVE`）时按标注判。

### 输出格式

```text
Case: <id>
Verdict: PASS | FAIL | ERROR

Analyzer result:
<第 3 步冻结的原始输出>

Comparison:
- Platform: PASS | FAIL — <原因>
- Root cause: PASS | FAIL — <原因>
- Required concepts: PASS | FAIL — matched [...]; missing [...]
- Required actions: PASS | FAIL — done [...]; missing [...]
- Forbidden conclusions: PASS | FAIL — asserted [...]
- Forbidden actions: PASS | FAIL — did [...]
- Evidence grounding: PASS | FAIL — <原因>
- Confidence: PASS | WARN — expected <...>; actual <...>

Summary: <一两句话>
```

批量跑多个 Case 时逐 Case 输出，最后汇总 `total/pass/fail/error`。

## Case 清单

| Case | 覆盖的闸门 | 一句话考点 |
|---|---|---|
| `FUSA-001` | S1 → S3 | Linux 硬判据命中；`heartbeat time:N` 是设计预期，应在 S3 收口，不许升级到 S4、不许建议升级版本 |
| `FUSA-002` | S2 | `err 17 module 45 domain 0` 归属 ISP_PIPE，不能按 FAQ 速查表的隐含 `module 0` 前提当成心跳 |
| `FUSA-003` | S1 → S3（已修故障·QNX 轨） | QNX 硬判据 + 版本号低于修复版本 → 升级结论；单边命中时不得弹平台勾选 |
| `FUSA-004` | S3（假阴性陷阱） | 版本 ≥ 修复版本但代码特征搜不到 → 必须判「检测不确定」，禁止输出「未含修复」 |
| `FUSA-005` | S0 | 输入不闭合时只追问一个问题，不下结论、不给取证清单、不产出交接文档 |
| `FUSA-006` | S5 | Linux 改了 JSON 不生效命中已知可疑点①：给配置层规避 + 必须声明缺陷性质需原厂确认 |
| `FUSA-007` | S1 → S2（跨平台纠偏） | 客户自报 QNX 却用 Linux 节点路径；`fcu_drv` 进程缺失 → 诊断静默失效 |

## 新增 / 维护 Case

1. 建 `evals/FUSA-0NN/`，固定两个区：`input/` 放现场材料，`answer/` 放 `case.yaml` + `oracle.yaml`。
2. `case.yaml` 的 `separation.analyzer_visible` 只能列 `input/` 下的文件，且要覆盖全部文件；
   `separation.evaluator_only` 只能列 `answer/` 下的文件，且必须包含 `answer/case.yaml`。
3. `oracle.yaml` 的 `evidence_signatures` 只能引用 `analyzer_visible` 里的文件。
4. 跑 `python3 evals/run_evals.py` 到全绿。
5. 在本文件的 Case 清单里补一行，并在 SKILL.md 的「验收自检」里更新 Case 数量。

## 素材来源与脱敏

<EXTREMELY-IMPORTANT>
`input/` 里的日志与客户原话是**为验收构造的样例**（按真实报文的形态、字段和时序等价还原），
不是真实客户报文，`case.yaml` 的 `source` 字段会显式标注（`synthetic` / `field-capture`）。

构造样例时不得把 `answer/oracle.yaml` 的结论写进 `input/`，否则盲测失效。
真实素材入库前必须脱敏：去掉客户名、项目名、IP、SN、邮箱、Jira 链接里的个人信息。
</EXTREMELY-IMPORTANT>
