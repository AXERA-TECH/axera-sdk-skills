# sdk-bsp-sdk-build

Axera SoC SDK 镜像编译、分立组件构建与 AXP 烧录包打包 skill 包。覆盖支持的工程目标发现（`make plist`）、全版本编译打包（`make PLAT=... clean all install axp`）、分立组件独立编译（ATF, OP-TEE, U-Boot, Kernel, Rootfs）以及构建参数配置。

通过内部路由自动适配当前工作区所在的 SDK 平台（支持 `m57`、`ax637` 等）。

> Skill 元数据与执行指令见 [`SKILL.md`](SKILL.md)；风险与来源摘要见 [`skill-card.md`](skill-card.md)。

## 适用场景

- 执行 SDK 全版本编译并打包生成 AXDL 烧录用的 `.axp` 固件。
- 在 `build/` 目录下通过 `make plist` 查看和确认当前支持的硬件工程清单。
- 独立编译内核（`kernel/linux`）、Bootloader（`boot/uboot`）、ATF（`boot/atf`）、OP-TEE（`boot/optee`）或根文件系统（`rootfs`）。
- 定制或裁剪构建选项（如在 `build/platforms/<vendor>/<PLAT>/config.mk` 中配置 `SUPPORT_OPTEE`）。
- 校验构建输出目录结构（`build/out/<PLAT>/images/`）与镜像产物完整性。

**不适用**：
- Linux 开发主机环境准备、依赖安装与工具链配置（请路由至 `sdk-bsp-sdk-environment`）。
- DDR 内存分布与 Flash 存储分区配置（请路由至 `sdk-bsp-memory-partition`）。
- 安全启动签名配置（请路由至 `sdk-bsp-secure-boot`）。

## 目录结构

```text
sdk-bsp-sdk-build/
├── README.md              # Skill 说明、平台矩阵、使用流程
├── SKILL.md               # Skill 主体：when to use / routing / instructions / safety
├── skill-card.md          # 元数据卡片：owner / riskLevel / 平台矩阵 / 来源
├── routing.yaml           # 平台识别与加载规则（ax637 / m57）
├── platforms/
│   ├── m57.md             # M57 架构编译与打包规范（工程命名、全量与组件编译、产物结构）
│   └── ax637.md           # AX637 板级编译规范（ax637/ax637r目标、U-Boot配置、内核配置）
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
| `m57`   | Axera M57 SDK / 架构基线 | `board-M57` 或 `SafetyIsland/mcal` 存在 | `platforms/m57.md` | `reference/m57/` |
| `ax637` | AX637 / AX637R SDK（extends `m57`） | `board-AX637` 或 `SafetyIsland/rt-thread/bsp/m57/configs_ax637*` 标志存在 | `platforms/ax637.md` | `reference/ax637/` |

## 使用流程

1. **触发 skill**：依据编译与打包需求调用 `sdk-bsp-sdk-build`。
2. **平台识别**：
   - 若参数含 `platform=<id>`，直接使用；
   - 否则在 SDK 根目录按 `routing.yaml` 检测，只有一个平台命中时继续；多个平台标志同时命中时列出冲突并询问 SDK/平台；
   - 命中带 `extends` 的平台（如 `ax637`）先加载父平台再叠加当前平台；
   - 无匹配则执行 `fallback: ask`，停止并要求确认平台。
`build/platforms/axera/<PLAT>/` 保存板级构建配置，例如 `ax637_demo_only_nand` 目标的 `config.mk` 和分区表。这些目标目录可同时出现在同一 SDK 中，只用于确认候选构建目标，不用于识别 SDK 家族。

3. **一句话汇报**识别到的平台（display 名 + 命中路径/来源），便于用户纠正。
4. **加载对应平台规范与参考文档**：
   - 阅读 `platforms/<id>.md` 获取平台专有的工程名称与编译配置；
   - 如需查看原始文档，查阅 `reference/<id>/_index.md` 索引后打开对应文档。
5. **按 `SKILL.md` §Instructions** 顺序执行：
   核验平台（`make plist`） $\rightarrow$ 全量构建与打包（`make PLAT=... clean all install axp`）或分立组件构建 $\rightarrow$ 核验 `build/out/<PLAT>/images/` 与 `.axp` 产物。

## 关键风险

- `clean` 目标会清除指定平台的所有已有构建产物，对于大型工程在增量调试时应按需使用。
- 编译成功仅代表代码与镜像构建完成，不代表分区表、硬件外设兼容性或烧录流程已验证。
- 严禁通过直接修改内存分区 JSON 或安全启动密钥来绕过编译错误，需走专门的设计流程。
