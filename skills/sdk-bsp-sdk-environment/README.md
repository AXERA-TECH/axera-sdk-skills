# sdk-bsp-sdk-environment

Axera SoC SDK Linux 开发主机环境准备与校验 skill 包。覆盖 Ubuntu 系统依赖包、交叉编译工具链的安装配置、SDK 源码解压打补丁（`sdk_unpack.sh`）以及离线恢复流程。

通过内部路由自动适配当前工作区所在的 SDK 平台（支持 `m57`、`ax637` 等）。

> Skill 元数据与执行指令见 [`SKILL.md`](SKILL.md)；风险与来源摘要见 [`skill-card.md`](skill-card.md)。

## 适用场景

- 配置全新 Linux / Ubuntu 编译开发机。
- 安装或修复 SDK 交叉编译工具链并配置环境变量。
- 解包原始 SDK 主包并运行 `sdk_unpack.sh` 释放 Linux、U-Boot、ATF、OP-TEE 源码树。
- 处理离线无网环境下 `sdk_unpack.sh` 源码包手动指定与修复。
- 校验 MCU RTOS（如适用）工具链绝对路径及编译环境就绪状态。

**不适用**：SDK 镜像编译、分立组件编译与 AXP 打包（请路由至 `sdk-bsp-sdk-build`）。

## 目录结构

```text
sdk-bsp-sdk-environment/
├── README.md              # Skill 说明、平台矩阵、使用流程
├── SKILL.md               # Skill 主体：when to use / routing / instructions / safety
├── skill-card.md          # 元数据卡片：owner / riskLevel / 平台矩阵 / 来源
├── routing.yaml           # 平台识别与加载规则（ax637 / m57）
├── platforms/
│   ├── m57.md             # M57 架构开发主机环境规范（依赖包、工具链、sdk_unpack 规范）
│   └── ax637.md           # AX637 板级环境规范（3套工具链、RT-Thread 路径对齐、解包与离线恢复）
├── reference/
│   ├── m57/               # M57 参考资料路由与说明
│   │   └── _index.md
│   └── ax637/             # AX637 参考资料路由与说明
│       └── _index.md
└── evals/
    ├── m57/
    │   └── tasks.yaml
    └── ax637/
        └── tasks.yaml
```

## 平台矩阵

| 平台 id | 说明 | 自动检测触发条件 | 主环境规范 | 参考文档 |
|---|---|---|---|---|
| `m57`   | Axera M57 SDK / 架构基线 | `board-M57` 或 `SafetyIsland/mcal/` 存在 | `platforms/m57.md` | `reference/m57/` |
| `ax637` | AX637 / AX637R SDK（extends `m57`） | `board-AX637` 或 `configs_ax637*` 存在 | `platforms/ax637.md` | `reference/ax637/` |

## 使用流程

1. **触发 skill**：依据主机环境准备需求调用 `sdk-bsp-sdk-environment`。
2. **平台识别**：
   - 若参数含 `platform=<id>`，直接使用；
   - 否则按 `routing.yaml` 检测；
   - 命中带 `extends` 的平台（如 `ax637`）先加载父平台再叠加当前平台；
   - 无匹配则执行 `fallback: ask`，停止并要求确认平台。
3. **一句话汇报**识别到的平台（display 名 + 命中路径/来源），便于用户纠正。
4. **加载对应平台规范与参考文档**：
   - 阅读 `platforms/<id>.md` 获取平台专有的安装依赖及交叉工具链参数；
   - 如需查看原始文档，查阅 `reference/<id>/_index.md` 索引后打开对应文档。
5. **按 `SKILL.md` §Instructions** 顺序执行：确认主机与环境 $\rightarrow$ 安装基础 apt/pip 依赖 $\rightarrow$ 部署平台对应的交叉编译器 $\rightarrow$ 对齐 MCU/RTOS 工具链路径（如适用） $\rightarrow$ 运行 `sdk_unpack.sh` 释放内核与 bootloader $\rightarrow$ 验证编译器与产物。

## 关键风险

- 工具链安装修改系统 `/usr/local` 与全局环境变量，需确认目标路径。
- `sdk_clean.sh` 会无差别删除已展开打补丁的代码树，切勿随意执行；若有私有修改需预先备份。
- 必须使用平台规范要求版本的交叉工具链，不可随意替换高版本编译器，以免导致 MCU 或驱动兼容性问题。
