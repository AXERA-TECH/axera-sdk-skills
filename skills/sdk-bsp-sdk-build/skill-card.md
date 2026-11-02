# Skill Card: sdk-bsp-sdk-build

| Field | Value |
|---|---|
| name | sdk-bsp-sdk-build |
| owner | Axera BSP Team |
| kind | workflow |
| riskLevel | medium — clean removes generated build artifacts; flashing is out of scope |
| platforms | AX637 / AX637R / M57 SDK platforms listed by `make plist` |
| reviewCycle | Each SDK release and build-system change |

## Use case

Select a supported platform, compile the full SDK or standalone components, package AXP download bundles, and verify output artifacts across supported Axera platforms (M57, AX637).

## Sources

- `platforms/m57.md` — M57 架构编译与打包规范（工程命名、全量构建、分立组件构建、产物核验）
- `platforms/ax637.md` — AX637 板级编译规范（ax637/ax637r demo 目标、U-Boot 2022.10 配置、内核配置）
- `reference/m57/_index.md` — M57 参考资料路由与说明
- `reference/ax637/_index.md` — AX637 参考资料路由与说明
- `build/platforms/*/*/config.mk`
- `kernel/linux/linux-6.1.83/arch/arm64/`
