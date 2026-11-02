# sdk-bsp-fusa

面向 M57 客户的 **FuSa 诊断框架自助排查 skill**，同时覆盖 **Linux** 与 **QNX** 两套 SDK。目标是让客户不必联系芯片原厂即可闭环大部分 FuSa 现象（heartbeat、error_mask、ECM/FCU、注入不生效、Call trace / RCU stall、压测稳定性等）；真正需要原厂介入时，则产出一份原厂工程师和 AI 都能直接接手的交接文档。

- 入口文件：[`SKILL.md`](SKILL.md)
- 激活方式：**explicit**，用户显式输入 `/sdk-bsp-fusa`、`$sdk-bsp-fusa` 或 `use sdk-bsp-fusa` 才会加载
- 语言：全程中文输出

## 适用现象

- 心跳 `heartbeat time:N` 刷屏 / `heartbeat timeout` 报错
- `error_mask` 解读、ECM / FCU 故障、故障注入不生效
- `cyclework` / `cyclecheck` 周期自检超时
- 改 Excel / JSON / 编译开关不生效
- 模块自检误报、Call trace / RCU stall、压测稳定性

## 排查流程（S0 → S6）

`SKILL.md` 中定义的固定阶段，S4↔S5 之间的循环最多三轮：

| 阶段 | 作用 |
|---|---|
| S0 输入闭合 | 现象 / 完整日志 / 复现步骤三项齐全 |
| S1 平台判定 | **硬闸门**，Linux vs QNX 判定明确前不许往下走 |
| S1b 环境落定 | 版本号、manifest 分支 |
| S2 归属定位 | 三步定位法（domain / module / event）+ ECM/FCU 双层检查 |
| S3 FAQ 检索 | 命中即出结论：设计预期 / 配置使用方法 / 已修故障 |
| S4 取证收敛 | 6~8 条命令让客户回填，逐条比对 |
| S5 代码反查 | 定性为四类之一 |
| S6 交接文档 | 疑似新缺陷或三轮无果时产出，供交回原厂 |

## 目录结构

```
.
├── SKILL.md               skill 入口与主流程（S0–S6）
├── agents/openai.yaml     展示信息与显式启用策略
├── tests/                 独立断言测试
├── references/            分平台的知识库
│   ├── 平台差异.md          Linux / QNX 判据、原语换算、可互通边界
│   ├── 归属定位-公共.md      三步定位法、domain 枚举、module 全表
│   ├── 归属定位-linux.md    /  归属定位-qnx.md
│   ├── FAQ-linux.md        /  FAQ-qnx.md
│   ├── 运行时接口-linux.md   /  运行时接口-qnx.md
│   ├── 取证框架.md          /  取证命令-linux.md  /  取证命令-qnx.md
│   ├── 代码地图-linux.md    /  代码地图-qnx.md
│   ├── 已知可疑点-linux.md   （Linux 侧文档未记录的实证事实）
│   └── 交接文档模板.md
└── evals/                 验收用例集
    ├── run_evals.py       确定性校验器（结构 / 隔离 / 跨平台串味 / FAQ 编号纪律）
    ├── evals.json         标准 evals 条目
    ├── trigger-evals.json 触发与跨 skill 边界用例
    ├── README.md          验收方式、盲测纪律、判定规则
    ├── suite.yaml         自动模型评测清单与预算
    ├── cases/             3 个评测场景（fixtures/ 输入 + 独立 assert.sh）
    └── FUSA-001 … FUSA-007  Golden Case 盲测（input/ 现场材料 + answer/ 期望结论）
```

## 核心铁律

来自 `SKILL.md`，改动任何 reference 前先复读：

1. **不判定平台不许往下走**——两平台命令零重合，猜错等于让客户白跑一整轮
2. **绝不落盘改 FuSa 源码**——功能安全代码，可以给配置 / diff，不能替客户改 `.c/.h`
3. **绝不编造**——每条结论要有 FAQ 条目号、`文件:行号` 或客户回填的命令输出
4. **先归属、再套 FAQ**——同一 err 号在不同 module 下语义完全不同
5. **不跨平台套结论**——只有 mask 解码、错误码含义、心跳语义可互通；路径 / 命令 / 代码位置一律不能
6. **能在 S3 出结论就不走到 S4**——每一阶出了结论就停

## 验收自检

改动 `SKILL.md` 或 `references/*.md` 之后必须回归。

```sh
# 1. 确定性校验（随时可跑）
python3 evals/run_evals.py

# 2. Golden Case 盲测（一次一个 Case）
python3 evals/run_evals.py --list FUSA-001
# 只读预检给出的 input/ 文件，按 S0–S6 排查，冻结结论后再读 answer/oracle.yaml 比对
```

盲测纪律：进入评分阶段之前不得读该 Case `answer/` 下任何文件，否则该次自检作废。详见 [`evals/README.md`](evals/README.md)。

## 行为评测材料

`evals/cases/` 保留 Linux mask、QNX 服务和输入不足三个场景，输入位于 `fixtures/`，独立断言位于 `assert.sh`。原有 `FUSA-001` 至 `FUSA-007` 仍按 [评测说明](evals/README.md) 做语义核对。

评测时仅向分析器提供当前用例输入及运行知识，答案与断言由评测方独立持有。本交付包不提供原内部自动评测工作流。确定性检查和用例断言不能替代完整语义评分、SDK 编译或实板测试。
