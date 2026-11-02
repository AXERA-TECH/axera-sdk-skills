# sdk-bsp-nand-fs

Axera SoC NAND 与文件系统 Skill，面向 M57 Linux/QNX 以及 AX637/AX637R Linux 主域的 NAND、Flash scan、MTD、UBI/UBIFS、分区、烧录和故障排查。

## 目录结构

```text
sdk-bsp-nand-fs/
├── SKILL.md
├── skill-card.md
├── routing.yaml
├── platforms/
│   ├── m57.md
│   └── ax637.md
├── reference/
│   ├── m57/
│   │   ├── _index.md
│   │   ├── nand-filesystem-faq.md
│   │   ├── flash-scan.md
│   │   ├── flash-adaptation.md
│   │   └── qnx-ax-mtd.md
│   └── ax637/
│       ├── _index.md
│       ├── nand-filesystem-faq.md
│       ├── flash-scan.md
│       └── flash-adaptation.md
└── evals/
    ├── m57/tasks.yaml
    └── ax637/tasks.yaml
```

- `SKILL.md`：触发边界、平台路由、资料收集清单、安全约束和执行入口。
- `skill-card.md`：owner、风险、平台矩阵、来源和维护周期。
- `routing.yaml`：工作区平台检测与 fallback 规则。
- `platforms/`：平台事实、源码位置、环境差异和验证边界。
- `reference/m57/`：M57 资料；其中 FAQ、Flash scan 和 Flash 适配文档也作为 AX637/AX637R 的共性方法副本维护，`qnx-ax-mtd.md` 仅适用于 M57。
- `reference/ax637/`：AX637/AX637R 的共性 NAND 文档副本；不放 QNX、virtual flash 或 MCAL/EB FLS 专属内容。
- `evals/`：按平台维护 Linux/QNX 验收任务；AX637/AX637R 仅维护 Linux 主域和 Safety/RTOS 启动链相关任务。

## 平台与环境边界

M57 可同时覆盖 Linux 与 QNX；AX637/AX637R 当前按仓库中的 Linux 主域和 Safety/RTOS 启动链处理，不把 QNX 文件系统内容套用到 AX637。公共文档分别放在两个平台目录中，便于平台独立发布；具体 Flash 型号、DTS、Kconfig、分区和命令仍必须以目标平台源码与配置为准。

当前文档记录的是 Wiki 整理内容和 checkout 中可核对的源码事实，未声称已经完成板级构建、烧录或硬件回归。任何擦除、重分区和烧录操作前都必须确认目标 board、`PLAT`、SDK revision、Flash geometry、镜像和持久化数据策略。

## 主要来源

- 部门 SDK BSP Skills 实施计划（M57 & AX637）
- nand文件系统FAQ
- linux下nand及文件系统FAQ汇总
- M57 flash scan功能使用指南
- 当前 checkout 中的 `build/`、`boot/uboot/`、`kernel/`、`SafetyIsland/` 和 `tools/` 相关源码与配置。
