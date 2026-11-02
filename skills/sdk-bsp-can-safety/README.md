# sdk-bsp-can-safety

用于诊断 M57 Linux/QNX 项目 Safety 侧 AUTOSAR MCAL CAN/CAN FD 问题。

## 适用范围

- 支持：M57 Linux/QNX 项目的 Safety 侧 AUTOSAR MCAL CAN。
- 不支持：AX637/AX637R Safety 侧 RTT RTOS CAN、主 CPU Linux SocketCAN、QNX 原生 CAN、SafetyIsland baremetal CAN。

主项目 OS 不能单独决定是否适用；应同时确认芯片、CAN ownership 和 Safety 侧 CAN 框架。

## 目录说明

```text
.
├── SKILL.md               # 技能入口：S0-S6 诊断流程、输出格式与 reference 路由
├── skill-card.md          # 版本、平台和维护边界
├── agents/openai.yaml     # Agent 发现元数据
├── references/            # 随包知识库（install.py 投影白名单）
│   ├── M57 CAN 常见问题解决思路.md
│   ├── M57 MCAL CAN EB 配置说明.md
│   ├── 代码地图-mcal.md
│   └── 平台范围.md
├── scripts/install.py     # 投影安装器：只打包 SKILL.md/agents/references，物理剔除评测答案
├── evals/
│   ├── suite.yaml         # 套件定义：smoke 门禁（can-002）、预算、并发
│   ├── evals.json / trigger-evals.json   # 静态校验用例数据
│   ├── run_evals.py       # M57 仓库侧 SDK 源码路径与 API 校验（依赖 M57 SDK）
│   └── cases/<id>/        # 标准评测用例：fixtures/ + case.yaml + assert.sh
│                          # 平台门 3 个 + 反向防御 1 个（证据不足刹车）
└── tests/test_structure.py # 自包含单测（无 SDK 依赖）
```

- `evals/cases/`：平台门用例（Linux 接受 / QNX 接受 / AX637R 拒绝）和
  反向防御用例（can-004，证据缺失时必须输出"证据不足"并给出补采清单），
  输入在 `fixtures/`，断言在 `assert.sh`，答案不进模型 bundle。

## Reference 原则

- FAQ 和 EB 配置说明是按需读取的 reference，不直接等同于目标项目事实。
- 实现行为应结合目标 SDK 源码、EB 工程、生成配置和现场证据确认。
- 没有明确输入的诊断结论不写入 Golden Case。

## 验收

分层运行：

```bash
# 1. 自包含结构单测
python3 -m unittest discover -s tests -v

# 2. M57 仓库侧 SDK 源码路径与 API 校验（需 M57 SDK 工作区）
python3 evals/run_evals.py

```

本交付包保留用例与独立断言，不提供原内部自动评测工作流。结构检查、模型行为评测和实际 SDK/板端验证分别记录。

## 数据边界

- reference 和 eval 只收录合成数据，或经授权、脱敏且完成最小化处理的证据。
- 不提交原始客户日志、账号或凭据、个人主目录、客户/项目标识及无关的设备、主机或网络标识。
- 诊断所需的 CAN ID、错误状态和时序信息可以保留；与结论无关的字段应删除或替换。
