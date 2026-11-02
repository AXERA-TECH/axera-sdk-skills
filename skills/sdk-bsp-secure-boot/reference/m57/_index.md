# reference/m57 文档路由

M57 平台参考文档均在本目录维护。下表路径相对技能根目录，读取时按实际路径定位；
AX637 平台先查 `reference/ax637/_index.md`，其安全开发指南与 M57 版本不可互相替代。

## 文档路由表

| 文档用途 | 实际路径 | 说明 |
|---|---|---|
| M57 安全开发指南 | `reference/m57/08 - AX Security开发指南.md` | M57 平台安全启动、签名、固件加密和 dm-verity 开发资料 |
| eFuse 使用说明 | `reference/m57/58 - AX EFUSE使用说明.md` | Root Key、PKH、FEK、bondoption 与烧写工具接口；AX637 复用 |
| Secure Boot FAQ | `reference/m57/M57-Secure-Boot-FAQ.md` | 配置组合、密钥、公钥同步、Download 与各阶段故障定位；AX637 复用 |

只读咨询优先使用 `platforms/m57.md` 的摘要，尚缺具体事实时再按本表查阅。
eFuse 写入前仍须确认目标、现有状态及密钥配套，索引不替代安全确认。
