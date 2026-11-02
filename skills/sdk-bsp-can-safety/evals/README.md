# evals

# CAN Skill 评测

## 目录说明

```text
evals/
├── suite.yaml            # 套件定义：smoke 门禁、预算、并发
├── evals.json            # 平台边界用例数据（结构校验输入）
├── trigger-evals.json    # 触发路由用例数据（结构校验输入）
├── run_evals.py          # M57 仓库侧 SDK 源码路径与 API 校验（依赖 M57 SDK）
└── cases/                # 确定性行为评测用例（axap-eval 消费）
    ├── can-001-m57-linux-mcal/          # M57 Linux + MCAL CAN FD → 支持（主项目 OS 门）
    ├── can-002-m57-qnx-mcal/            # M57 QNX + MCAL CAN → 支持（smoke 用例）
    ├── can-003-ax637r-reject/           # AX637R RTT CAN → 拒绝（芯片 + 框架门）
    └── can-004-m57-busoff-inconclusive/ # 反向防御：
                                         #   只有现象无配置/日志 → 必须输出"证据不足"
                                         #   + 最小补采清单，禁止断言根因
```

每个 case 遵循输入与答案物理分离：

- `fixtures/`：黑盒输入（prompt.md + evidence.txt），复制进模型 workspace。
- `case.yaml`：任务提示词与输出契约，不含答案。
- `assert.sh`：evaluator-only 独立断言，由 harness 在模型执行后调用；
  原 `answer/oracle.yaml` 的 required_concepts / forbidden_conclusions /
  evidence_signatures 在此转写为确定性检查。

## 运行

- M57 仓库侧 SDK 校验：`python3 evals/run_evals.py`。

`evals.json` 只收录具有明确输入字段的验收用例；没有目标配置、日志、生成文件
或现场现象的诊断问题不写入 Golden Case。主 CPU Linux SocketCAN 不收录测试用例。
Golden Case 只使用合成数据，或经授权、脱敏且最小化的证据；不收录原始客户日志或可识别
客户、人员和环境的信息。
