# Skill Card: sdk-bsp-ota

| Field | Value |
|---|---|
| name | sdk-bsp-ota |
| owner | Axera BSP Team |
| kind | workflow (reference + diagnosis) |
| riskLevel | high — 目标槽擦写、状态标记和内容同步可能影响可启动性 |
| platforms | M57 Linux/QNX；AX637 / AX637R Linux |
| reviewCycle | 每次 SDK、OTA 状态机、handler、签名链或部署规则变化时 |
| version | 0.2.0 |
| license | MIT |

## Use case

生成、定制和诊断 Axera OTA 升级包、SWUpdate 调度、首次启动验证、A/B fallback 与内容同步恢复。通过 `routing.yaml` 识别 SDK，加载 `platforms/<id>.md` 与 reference 索引，不要求为每个芯片切换 skill。SDK 家族、OS 和构建 PLAT 分别确认。

## Platform matrix

| 平台 id | 说明 | 自动检测触发条件 |
|---|---|---|
| `ax637` | AX637/AX637R Linux；extends m57，子平台覆盖同名条目 | `SafetyIsland/rt-thread/bsp/m57/configs_ax637` 或 `configs_ax637r` 存在；先匹配 |
| `m57` | 公共 OTA 架构与 M57 Linux/QNX 环境差异 | `SafetyIsland/mcal` 存在 |

新增平台：`routing.yaml` + `platforms/<id>.md` + `reference/<id>/_index.md` 与相应原始资料 + `evals/<id>/tasks.yaml`。继承不包含未声明适用的 OS 专属实现和历史问题根因。

## Known risks

- BCB OTA 状态、AB metadata 和实际启动槽混淆可能导致错误回退；保护唯一成功槽。
- 同步会覆盖旧槽，只在新槽功能验证通过后进行；文件升级与共享数据需单独验证掉电一致性。
- Linux/QNX 的设备、擦除工具、ETFS 和部署链不同，不可由平台家族自动推导。
- 首次启动验证脚本名称随文档/版本变化，缺脚本默认成功不能证明业务已验证。
- M57 历史问题尚未逐项核实修复版本；AX637 的具体功能组合尚未实板验收。

## Sources

- [platforms/m57.md](platforms/m57.md) — 公共流程事实、M57 路径、状态机、Linux/QNX 差异与故障表。
- [platforms/ax637.md](platforms/ax637.md) — AX637 Linux 覆盖项、SDK 路径和平台故障表。
- [reference/m57/_index.md](reference/m57/_index.md)、[reference/ax637/_index.md](reference/ax637/_index.md) — 原始资料与复用范围的文档路由。
- [reference/m57/Linux-OTA-知识库.md](reference/m57/Linux-OTA-知识库.md) — Linux 实现优先来源；与 QNX 知识库共用框架、区分部署和路径。
- [reference/sources.md](reference/sources.md) — 本地技术来源、版本适用范围和证据边界。
- [evals/m57/tasks.yaml](evals/m57/tasks.yaml)、[evals/ax637/tasks.yaml](evals/ax637/tasks.yaml) — 分平台验收用例。
