# 安装 AXERA SDK Skills

运行环境：Linux / WSL、Bash、Python 3.10+。安装器只使用 Python 标准库；技能运行或评测可能需要各自声明的 SDK、工具及 Python 依赖。

从本仓库 clone，或下载 Releases 中对应版本的源码归档，解压后进入包含 `install.sh` 的目录：

```bash
bash install.sh --verify
bash install.sh --target /path/to/agent/skills
bash install.sh --chip AX615D --target /path/to/agent/skills
bash install.sh --chip M57 --target /path/to/agent/skills
bash install.sh --chip AX637R --target /path/to/agent/skills
```

`--verify` 只读校验完整技能集合、路径及指纹，不安装或执行技能，不代表功能评测通过。芯片筛选支持清单中的别名；实际 SDK 与操作系统支持范围见每个 `SKILL.md`。

Codex 项目目录通常为 `.agents/skills`，Claude Code 为 `.claude/skills`，OpenCode 为 `.opencode/skills`。Agent 在远程或容器中运行时，应安装到对应环境。

默认复制技能；`--mode link` 创建软链接，来源目录需要持续保留。重复安装无变化时跳过。遇到未管理的同名内容、本地修改或被修改的链接时保留原内容并报错；更新使用同一个目标目录。安装状态文件与锁文件用于保护已有内容，请勿手动删除以绕过检查。

安装后启动新会话或刷新技能列表，按名称调用技能并确认实际加载的 `SKILL.md`。未知芯片、空集合或内容指纹不一致时停止安装。

贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。仓库采用 MIT License，见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。

## 技能速查

<!-- skills:start -->
| 技能 | 简短用途 | 芯片 |
|---|---|---|
| [sdk-audio-aec-diag-skill](skills/sdk-audio-aec-diag-skill/SKILL.md) | 分析 AEC 回声、参考信号和时延问题，给出修正与复测建议。 | AX615 |
| [sdk-axck-app](skills/sdk-axck-app/SKILL.md) | AXCK 应用开发、模块编译、固件打包及 Client-Service 调试。 | AX615 |
| [sdk-axck-config](skills/sdk-axck-config/SKILL.md) | AXCK Sensor 适配、图像管线配置、拓扑校验及内存预算。 | AX615 |
| [sdk-axck-diag](skills/sdk-axck-diag/SKILL.md) | 分析 AXCK 启动与运行日志，定位系统、媒体和 IPC 故障。 | AX615 |
| [sdk-axck-test](skills/sdk-axck-test/SKILL.md) | 执行 AXCK 板端功能测试、服务巡检及媒体链路验证。 | AX615 |
| [sdk-bsp-aov-diag-skill](skills/sdk-bsp-aov-diag-skill/SKILL.md) | 诊断深度休眠、wakeup_count 与低功耗 GPIO 唤醒异常。 | AX615 |
| [sdk-bsp-boot](skills/sdk-bsp-boot/SKILL.md) | M57 / AX637 启动链、SBL、U-Boot 与启动失败诊断。 | M57, AX637 |
| [sdk-bsp-boot-diag-skill](skills/sdk-bsp-boot-diag-skill/SKILL.md) | 分析 BL1、U-Boot 和 Linux 启动日志，定位镜像与启动链路故障。 | AX615 |
| [sdk-bsp-build](skills/sdk-bsp-build/SKILL.md) | 编译 BSP 与固件模块，生成并核对完整或增量 AXP 包。 | AX615 |
| [sdk-bsp-can-safety](skills/sdk-bsp-can-safety/SKILL.md) | 诊断 M57 Safety MCAL CAN / CAN FD；不适用于 AX637。 | M57 |
| [sdk-bsp-ddr-diag-skill](skills/sdk-bsp-ddr-diag-skill/SKILL.md) | 排查 DDR 初始化、训练、内存测试及稳定性问题。 | AX615 |
| [sdk-bsp-fast-boot-skill](skills/sdk-bsp-fast-boot-skill/SKILL.md) | 分析快启、RTOS/Linux 双核交接、外设仲裁及跨核内存问题。 | AX615 |
| [sdk-bsp-fusa](skills/sdk-bsp-fusa/SKILL.md) | 排查 M57 Linux / QNX 功能安全诊断、故障上报与注入问题。 | M57 |
| [sdk-bsp-memory-partition](skills/sdk-bsp-memory-partition/SKILL.md) | M57 / AX637 DDR、CMM 内存与 FLASH 分区规划和调整。 | M57, AX637 |
| [sdk-bsp-nand-fs](skills/sdk-bsp-nand-fs/SKILL.md) | M57 / AX637 NAND、MTD、文件系统挂载、ECC 与性能排障。 | M57, AX637 |
| [sdk-bsp-network-card-skill](skills/sdk-bsp-network-card-skill/SKILL.md) | 排查网卡链路、PHY 协商、IP/DHCP、TCP 服务及吞吐问题。 | AX615 |
| [sdk-bsp-ota](skills/sdk-bsp-ota/SKILL.md) | M57 / AX637 OTA、SWUpdate、A/B 升级、回退与恢复诊断。 | M57, AX637 |
| [sdk-bsp-rpmsg](skills/sdk-bsp-rpmsg/SKILL.md) | M57 / AX637 核间通信、RPMsg / RPZC 配置与共享内存排障。 | M57, AX637 |
| [sdk-bsp-sd-card-skill](skills/sdk-bsp-sd-card-skill/SKILL.md) | 排查 Linux 阶段 SD 卡识别、挂载、读写与热插拔问题。 | AX615 |
| [sdk-bsp-sdk-build](skills/sdk-bsp-sdk-build/SKILL.md) | M57 / AX637 SDK 全量和组件构建、平台选择及 AXP 打包。 | M57, AX637 |
| [sdk-bsp-sdk-environment](skills/sdk-bsp-sdk-environment/SKILL.md) | 准备 M57 / AX637 SDK 主机环境、依赖与交叉工具链。 | M57, AX637 |
| [sdk-bsp-secure-boot](skills/sdk-bsp-secure-boot/SKILL.md) | M57 / AX637 安全启动、签名加密、eFuse 与验证失败诊断。 | M57, AX637 |
| [sdk-bsp-sys-diag-skill](skills/sdk-bsp-sys-diag-skill/SKILL.md) | 通过日志和问答定位 CMM 内存释放、内存不足、挂死及崩溃。 | AX615, AX620 |
| [sdk-dataflow-analysis](skills/sdk-dataflow-analysis/SKILL.md) | 分析模块绑定、HSK 握手与数据流日志，定位启动失败或断流。 | AX615 |
| [sdk-ivps-venc-diagnose](skills/sdk-ivps-venc-diagnose/SKILL.md) | 分析 IVPS→VENC 链路卡死，定位握手或离线数据流停滞段。 | AX615 |
| [sdk-tx-analyse](skills/sdk-tx-analyse/SKILL.md) | 分析 TX 同轴输出问题，生成 VO→TX 配置与示例代码。 | AX615 |
| [sdk-venc-rc-config-audit](skills/sdk-venc-rc-config-audit/SKILL.md) | 审查 VENC 码控参数与码流结构，分析码率、GOP 和帧率异常。 | AX615 |
| [sdk-vo-analysis](skills/sdk-vo-analysis/SKILL.md) | 诊断 VO 输出问题，并生成接口、时序和颜色配置。 | AX615 |
<!-- skills:end -->
