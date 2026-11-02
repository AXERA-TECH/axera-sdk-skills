# Skill Card: sdk-bsp-sdk-environment

| Field | Value |
|---|---|
| name | sdk-bsp-sdk-environment |
| owner | Axera BSP Team |
| kind | workflow |
| riskLevel | medium — system packages, `/usr/local`, and shell PATH are changed |
| platforms | AX637 / AX637R / M57 SDK Linux host |
| reviewCycle | Each SDK release and toolchain revision |

## Use case

Provision a Linux development host, install required cross-toolchains, expand SDK sources (`sdk_unpack.sh`), and verify build readiness across supported Axera platforms (M57, AX637).

## Sources

- `platforms/m57.md` — M57 架构开发主机环境规范（系统依赖、ARM64 9.2 与 Linaro 7.5 ARM32 工具链、`sdk_unpack.sh` 机制）
- `platforms/ax637.md` — AX637 开发主机规范（3套工具链、RT-Thread `EXEC_PATH` 路径对齐、AX637 包名与板级目标）
- `reference/m57/_index.md` — M57 参考资料路由与说明
- `reference/ax637/_index.md` — AX637 参考资料路由与说明
- `build/platforms/<PLAT>/config.mk`
- `SafetyIsland/rt-thread/bsp/m57/configs_*/rtconfig.py`
