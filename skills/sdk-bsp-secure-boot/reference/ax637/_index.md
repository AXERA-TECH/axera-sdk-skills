# reference/ax637 文档路由

本目录不重复维护与 M57 共用的文档。下表声明 ax637 平台在检索参考文档时的实际来源，
**读取时按"实际路径"列取文件，不要假设文档一定在本目录下**。

## 文档路由表

| 文档用途 | 实际路径 | 说明 |
|---|---|---|
| AX637 平台安全开发指南 | `reference/ax637/09 - AX Security开发指南.md` | 本目录本地维护；AX637 平台专用版本，含 TrustZone/OP-TEE 章节，与 M57 通用版内容不通用 |
| eFuse 使用说明 | `reference/m57/58 - AX EFUSE使用说明.md` | **复用 m57 目录**。eFuse 编程流程为 M57 架构层机制，AX637 沿用同一套 Root Key/PKH/FEK 规则 |
| Secure Boot FAQ | `reference/m57/M57-Secure-Boot-FAQ.md` | **复用 m57 目录**。Q1-Q29 覆盖信任链、config.mk、密钥、Download、BootROM trace 解码、各阶段串口日志关键字 |

## 为什么这样分

- **本目录本地维护**：仅当文档描述的是 AX637 board 层专有内容（board `config.mk` 路径、
  AX637 特有目录结构、AX637 版工具链）时才放在 `reference/ax637/`。
- **复用 `reference/m57/`**：描述 M57 架构层机制（BootROM 行为、eFuse 编程、
  FIT/签名格式、故障字段布局）的文档，AX637 与 M57 完全一致，不做副本，
  避免同一事实在两个目录各自修订而漂移。
- **注意**：`reference/m57/08 - AX Security开发指南.md` 与
  `reference/ax637/09 - AX Security开发指南.md` 是两份独立文档（前者为 M57 通用版，
  后者为 AX637 平台版），**不可互相替代**；回答 AX637 问题时读后者。

## 维护规则

1. 新增 ax637 文档前，先判断其内容是否属于 M57 架构层；是则只放 `reference/m57/`，
   并在此表登记一行。
2. 修改 `reference/m57/` 下的文档时，必须确认 AX637 侧同样适用；若 AX637 有差异，
   在 `platforms/ax637.md` 中说明差异，而不是复制文档。
3. 本表是 `platforms/ax637.md` §参考文档 与 `skill-card.md` §Sources 的事实来源；
   调整路径时三处需同步。
