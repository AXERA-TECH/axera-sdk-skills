# sdk-bsp-secure-boot

Axera SoC Secure Boot skill 包。覆盖签名/加密启动链、eFuse（PKH / Root Key / FEK）规划、
FIT 镜像生产、dm-verity、密钥替换以及各阶段失败诊断。通过内部路由自动适配当前工作区
所在的 SDK 平台（当前支持 `m57`、`ax637`），无需用户手动切换 skill。

> Skill 元数据与执行指令见 [`SKILL.md`](SKILL.md)；风险/来源摘要见 [`skill-card.md`](skill-card.md)。

## 适用场景

- 使能或验证 `SECURE_BOOT`、固件加密、rootfs dm-verity
- 生成/替换签名或加密镜像；替换 RSA 密钥并同步 U-Boot DTB 公钥
- 规划 eFuse Root Key / PKH / FEK 写入顺序
- 诊断签名、解密、FIT 或 dm-verity 启动失败

**不适用**：与安全启动无关的 eFuse 编程、TEE 应用开发或普通镜像构建。

## 目录结构

```
sdk-bsp-secure-boot/
├── SKILL.md              # Skill 主体：when to use / routing / instructions / safety
├── skill-card.md         # 元数据卡片：owner / riskLevel / 平台矩阵 / 来源
├── routing.yaml          # 平台识别与加载规则（先具体 board，后架构层）
├── platforms/
│   ├── m57.md            # M57 架构公共层（信任链、config、产物、Download、eFuse、fault.c）
│   └── ax637.md          # AX637/AX637R board 差异（RTT、PLAT 命名；extends m57）
├── reference/
│   ├── m57/              # M57 通用安全开发指南、eFuse 说明、Secure Boot FAQ
│   └── ax637/            # AX637 平台文档；_index.md 声明哪些复用 m57
└── evals/
    ├── m57/tasks.yaml
    └── ax637/tasks.yaml
```

## 平台矩阵

| 平台 id | 说明 | 自动检测触发条件 | 主文档 |
|---|---|---|---|
| `m57`   | Axera M57 SDK / 架构公共层 | `SafetyIsland/mcal/` 存在 | `platforms/m57.md`, `reference/m57/` |
| `ax637` | AX637 / AX637R SDK（extends `m57`） | `SafetyIsland/rt-thread/bsp/m57/configs_ax637*` 存在 | `platforms/ax637.md`, `reference/ax637/` |

路由匹配顺序由 `routing.yaml` 从上到下决定，具体 board/SDK 条目必须排在通用架构条目之前。
不得用 `mach-axera/m57`、`m57-keys.dtsi`、`SafetyIsland/sbl` 等 M57/AX637 共用路径区分平台。

## 使用流程

1. **触发 skill**：由主 agent 依据用户请求匹配到 `sdk-bsp-secure-boot`。
2. **平台识别**：
   - 若参数含 `platform=<id>`，直接使用；
   - 否则按 `routing.yaml` 检测；命中带 `extends` 的平台先加载父平台再叠加子平台；
   - 无匹配则执行 `fallback: ask`，停止并要求确认平台。
3. **一句话汇报**识别到的平台（display 名 + 命中路径 / 来源），便于用户纠正。
4. **加载 `platforms/<id>.md`**；仅在具体步骤需要时打开 `reference/<id>/_index.md`
   声明的对应文档路径（部分复用 m57，不要跨平台猜路径）。
5. **确认目标**：在开始修改前一次性收集板型、`PLAT`/启动介质、eFuse 状态、
   RSA 位数、是否加密、是否 dm-verity；缺失则询问，不替用户补默认值。
6. **按 `SKILL.md` §Instructions** 顺序执行：密钥离线准备 → eFuse 规划 →
   config.mk 配置 → 各组件构建（imgsign / image-signing / FIT）→
   替换 DTB 验签公钥 → dm-verity → 分阶段使能与诊断。

## 关键风险（详见 `SKILL.md` §Safety、`skill-card.md` §Known risks）

- eFuse Root Key / PKH / FEK 编程不可逆；PKH 与签名密钥不匹配将永久锁死设备。
- 私钥、AES Key、FEK、Root Key 永不入源码 / 日志 / 工单。
- 未验证 Root Key / FEK 前不启用 `ENABLE_CIPHER`；rootfs 可写时不启用 dm-verity。
- PKH、DTB 公钥、签名私钥、镜像必须构成一致的版本化集合。

## 新增平台

1. 在 `routing.yaml` 追加 `platforms:` 条目（`detect` 条件必须是该 SDK 独有的源码路径，
   避免命中 build/out 或与其它平台共用的通用路径），必要时用 `extends` 指向父平台。
2. 新建 `platforms/<id>.md`，覆盖信任链、config、产物、Download / eFuse、故障定位。
3. 建立 `reference/<id>/`，并写 `_index.md` 声明各文档实际来源（本地维护或复用其他平台）。
4. 在 `evals/<id>/tasks.yaml` 补充该平台的评测用例。
5. 更新 `SKILL.md` 与 `skill-card.md` 的平台矩阵。

## 开发与维护
