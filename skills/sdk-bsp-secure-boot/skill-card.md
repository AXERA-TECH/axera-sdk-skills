# Skill Card: sdk-bsp-secure-boot

| Field | Value |
|---|---|
| name | sdk-bsp-secure-boot |
| owner | Axera BSP Team |
| kind | workflow (reference + diagnosis) |
| riskLevel | critical — eFuse 和密钥操作不可逆；错误产物可能砖化设备 |
| platforms | M57 架构（AX637 / AX637R）；可扩展至 AX620E、AX650 等 |
| reviewCycle | 每次 Secure Boot 特性、SDK 版本或密钥格式变更时 |

## Use case

构建、规划、验证并诊断 Axera SoC 的签名/加密启动链与 rootfs dm-verity。
通过 `routing.yaml` 内部路由自动识别当前 SDK 平台，叠加对应的
`platforms/<id>.md` 与 `reference/<id>/` 事实，无需用户切换 skill。

## Platform matrix

| 平台 id | 说明 | 自动检测触发条件 |
|---|---|---|
| `m57` | Axera M57 SDK/架构公共层（BootROM trace、FIT、配置、产物、Download、eFuse） | `SafetyIsland/mcal/` 存在 |
| `ax637` | AX637/AX637R SDK（RT-Thread、board 层、具体 `PLAT`） | `SafetyIsland/rt-thread/bsp/m57/configs_ax637*` 存在 |

新增平台：`routing.yaml` + `platforms/<id>.md` + `reference/<id>/` + evals 矩阵条目。

## Known risks

- eFuse Root Key / PKH / FEK 编程不可逆；PKH 与签名密钥不匹配将永久锁死设备。
- 签名私钥、AES Key、DTB 公钥、eFuse PKH 必须作为版本化集合管理，任意一项更换都需同步全套。
- 加密固件（`ENABLE_CIPHER`）需要 Root Key 和 FEK 预先正确烧写；错误顺序或跨芯片复用 FEK 会使设备无法启动。
- dm-verity 要求只读文件系统（EXT4/SQUASH），启用可写 UBI 时构建会主动报错。

## Sources

- `platforms/m57.md` — M57 架构信任链、源码路径、故障字段、串口日志关键字
- `platforms/m57.md` — M57/AX637 共用的 config、产物命名、Download/eFuse 规划
- `platforms/ax637.md` — AX637 SDK board 差异、RT-Thread 与具体 `PLAT` 路径
- `reference/ax637/_index.md` — **文档路由表**：声明 ax637 侧文档的实际来源（哪些复用 m57）
- `reference/ax637/09 - AX Security开发指南.md` — AX637 平台安全开发指南
- `reference/m57/08 - AX Security开发指南.md` — M57 通用版安全开发指南（与 ax637 版独立）
- `reference/m57/58 - AX EFUSE使用说明.md` — eFuse 编程流程（ax637 与 m57 共用）
- `reference/m57/M57-Secure-Boot-FAQ.md` — Q1-Q29 覆盖配置、密钥、Download、trace 解码、串口日志（ax637 与 m57 共用）
