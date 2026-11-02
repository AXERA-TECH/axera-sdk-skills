# sdk-bsp-boot

Axera SoC Boot 启动支持 skill：覆盖 SBL/AB 启动管理、U-Boot 引导内核方式、内存与 FLASH 分区规划、BOOTROM、BootCnt、OTA 升级，以及基于串口日志的启动类问题定位。通过内部路由自动适配当前工作区所在的 SDK 平台（当前支持 `m57`、`ax637`），无需用户手动切换 skill。

> Skill 元数据与执行指令见 [SKILL.md](SKILL.md)；风险/来源摘要见 [skill-card.md](skill-card.md)。

## 适用场景

- 查询或配置 SDK 启动链路（BootROM → SBL → SPL → BL31 → OP-TEE → U-Boot → Kernel）。
- 规划/调整内存（Linux / CMM / Inline ECC）与 FLASH 分区（partitions.json、mtdparts、AB 约束）。
- 定制 U-Boot 引导内核方式（distro_bootcmd / extlinux / 各组合简化 BOOTCMD）。
- 定位启动类问题：BOOTROM 字符、SBL AB 管理 FAQ log、U-Boot/Kernel 启动日志。
- 对接 OTA A/B 升级、BootCnt、调试串口波特率等启动相关特性。

**不适用**：Secure Boot 签名/加密与 eFuse 规划（用 `sdk-bsp-secure-boot`）；纯 Linux 驱动、音视频、NPU 等非启动主题。

## 目录结构

```
sdk-bsp-boot/
  SKILL.md                  # 执行指令（路由、平台确认、Instructions、Safety）
  skill-card.md             # 风险/来源摘要
  routing.yaml              # 平台检测与加载顺序
  README.md
  platforms/
    m57.md                  # M57 架构公共：构建、启动链、内存/分区机制、BOOTROM、BootCnt、OTA、SBL 特性、故障定位
    ax637.md                # AX637/AX637R board/SDK 层差异（extends m57）
  reference/
    ax637/
      _index.md             # AX637 文档路由表
      00 - AX SDK 使用说明.md
      637-boot类问题.md
    m57/
      00 - AX SDK 使用说明.md
      M57 SBL启动特性介绍.md
  evals/
    m57/tasks.yaml
    ax637/tasks.yaml
```

## 平台矩阵

| 平台 id | 说明 | 自动检测触发条件 | 主文档 |
| --- | --- | --- | --- |
| ax637 | AX637 / AX637R SDK（基于 M57） | `SafetyIsland/rt-thread/bsp/m57/configs_ax637`、`configs_ax637r` 任一存在 | `platforms/ax637.md`（+ `platforms/m57.md`） |
| m57 | Axera M57 SDK（M57 架构） | `SafetyIsland/mcal` 存在 | `platforms/m57.md` |

路由匹配顺序由 `routing.yaml` 从上到下决定，具体 board/SDK 条目必须排在通用架构条目之前。不得用 `boot/uboot`、`kernel/linux`、`build/platforms/axera` 下的公共脚本等 M57/AX637 共用路径区分平台。

## 使用流程

1. 识别工作区平台（`args platform=<id>` 优先，否则按 `routing.yaml` 检测路径匹配）。
2. 加载选中平台的 `platforms/<id>.md`；命中 `ax637` 时叠加 `platforms/m57.md`。
3. 读取 `reference/<id>/_index.md` 定位对应参考文档。
4. 与用户确认目标板型/PLAT、FLASHTYPE、是否 AB、是否安全启动，再读写配置。
5. 按主题引用对应章节给出结论与操作步骤，涉及启动失败时按阶段对齐串口日志关键字。
6. 涉及分区/内存改动时提示风险与重新编译烧写验证要求。

## 关键风险（详见 SKILL.md §Safety、skill-card.md §Known risks）

- AB 场景 SBL 分区大小必须用默认值（NAND 768K / eMMC 128K），否则 RomCode 找不到 B 分区。
- NAND 分区需为 block size 整数倍并预留坏块 block；hsm 附在 SBL 镜像后，SBL 实际占 256K。
- AX637 与 M57 内存/CMM 调整入口一致（平台 `config.mk` 的 `SYSTEM_MEMORY_SZ` / `LINUX_MEMORY_SZ`）。
- BootCnt 仅 M57 支持，AX637 / AX637R 不支持。
- only_nand 与 only_emmc 分区表位置不同，不可套用。

## 新增平台

1. 在 `routing.yaml` 增加平台条目（`id`/`display`/`detect`/`load`/`reference_root`，必要时 `extends`），并按“具体在前、通用在后”排序。
2. 新增 `platforms/<id>.md`，只写与父平台的差异。
3. 新增 `reference/<id>/` 与 `reference/<id>/_index.md` 文档路由表。
4. 在 `evals/<id>/tasks.yaml` 增加验收任务。
5. 更新本文件 §平台矩阵、`SKILL.md` §平台矩阵与 `skill-card.md`。
