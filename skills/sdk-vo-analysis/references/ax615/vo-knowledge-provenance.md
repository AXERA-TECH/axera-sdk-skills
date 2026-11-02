# VO 知识来源分级与使用边界

> 本文件说明 sdk-vo-analysis 内化知识的**来源分级**与**可信度边界**，替代历史上的源码映射文件。
> **硬约束**：分析全流程不主动访问 skill 目录以外的路径，也不访问任何外部源码树（**用户显式提供的
> 文件，如客户日志、proc 采集、代码片段、屏规格书，允许读取并作为客户环境证据；不主动读取凭据/
> 密钥文件**）；一切知识结论取自本 skill 的 references 与知识库检索。**新增任何知识引用路径必须经用户显式要求。**

## 0. 来源分级（按可信度排序）

| 级别 | 来源 | 可引用的内容 | 版本标注 |
|---|---|---|---|
| A | **公开头文件**：`ax_vo_api.h`、`ax_global_type.h` | 结构体/枚举/错误码/宏的名称与定义、**公开头文件行号** | SDK 发布包版本（内化对应 V3.14.0） |
| B | **官方 sample** | sample 文件名、sample 参数、调用顺序、内置时序表（19 组，见 [sample-vo-timings.json](sample-vo-timings.json)） | SDK 发布包版本 |
| C | **知识库文档**（AX VO API 文档 / AX VO 开发指南 / 软件错误码文档 / FAQ） | 文档名与章节语义、错误码表、proc 字段说明 | 文档随 SDK 版本发布 |
| D | **已验证时序表**（54 组，见 [vo-timing-table.json](vo-timing-table.json)） | 条目名与参数取值 | **SDK V3.14.0 实现行为，需按版本核验** |
| E | **实现行为摘要**（见 [vo-sdk-behavior-notes.md](vo-sdk-behavior-notes.md)） | 经**已授权源码核验**后转换为行为约束的结论（当前内化版本行为），不含路径/文件名/内部符号/行号 | 每条均带固定标注 **SDK V3.14.0 实现行为，需按版本核验** |

## 1. 各级证据的使用规则

- **A/B 级可直接对客户出示**：头文件名、行号、sample 文件名、sample 参数均可引用。
- **C 级引用文档名与章节**；检索不到时明示"知识库未命中"，不得编造文档内容。
- **D/E 级只作为行为判据**：引用时沿用固定版本标注，说明"基于 SDK V3.14.0；版本不同需重新核验"。
- **E 级禁止展开为源码细节**：不得出现实现文件路径、文件名、内部函数/变量/符号名或源码行号；
  需要更细证据时转 B/C 级或请客户抓取 proc/dmesg。
- **A 级不含能力/可用性结论**：公开头文件只确认**名称与语义**（如预设模式名、字段、错误码）。
  「某预设模式/某组合在目标 SDK 上是否真的可用」属**实现行为**，按 E 级表述
  （「已授权源码核验的 SDK 行为约束」／「当前内化版本行为」）并须实机核验；
  不得由"头文件里有该名字"推出"天然可用"或"由 SDK 保证"，预设模式同样要经过当前 SDK 的
  离散 PCLK 与接口/芯片能力校验。

- **版本路由**：引用 D/E 级资料前，先按 [version-routing.md](version-routing.md) 判定 `same/different/unknown/conflict`；目标版本不同或未知时不得把 V3.14.0 行为摘要作为已确认的目标版本事实。**"无提交/无差异记录"不等于行为保证**，只能表述为"已收录记录未发现相关差异，目标环境需核验"。
- **证据分层**：各级来源用于**事实确认**（该行为/字段/能力是否如此）；本次故障的**根因确认**需要客户现场证据（代码/返回值/proc/dmesg/复现）与事实连成因果链，**文档与内化副本不能单独证明本次因果**；修复建议经实机复现才算**修复验证**。

## 2. 内化副本清单（本 skill 自包含）

| 文件 | 内容 | 级别 |
|---|---|---|
| [sdk-inline/ax_vo_api.h](sdk-inline/ax_vo_api.h)、[sdk-inline/ax_global_type.h](sdk-inline/ax_global_type.h) | 公开头文件逐字内化副本（脱敏版权头，行号与原文对齐） | A |
| [vo-api-inline.md](vo-api-inline.md) | 头文件关键段落速查（错误码、结构体、CSC 矩阵、色域） | A |
| [sample-vo-timings.json](sample-vo-timings.json) | 官方 sample 内置 19 组时序 + 与 54 组表的差异说明 | B |
| [vo-timing-table.json](vo-timing-table.json) | 54 组已验证时序表（条目名保留原 key） | D |
| [vo-pclk-table.json](vo-pclk-table.json) | PCLK 5×16 离散档位表（完整枚举） | D/E |
| [vo-sdk-behavior-notes.md](vo-sdk-behavior-notes.md) | 版本化实现行为摘要（每条带固定标注） | E |
| [vo-python-binding.md](vo-python-binding.md) | 客户可见 Python 运行时常量/模块/包装名调用约定摘要 | B/E |
| [version-manifest.json](version-manifest.json)、[version-routing.md](version-routing.md) | 内化版本单一机器源、版本探测优先级与证据降级规则 | A-E |
| [vo-constraints.md](vo-constraints.md)、[troubleshooting-playbook.md](troubleshooting-playbook.md) | 速查约束与排查剧本（结论均为上述来源的派生） | A-E |

## 3. 冲突处理原则

- 两个时序表（sample 19 组 / 已验证 54 组）**独立保存、不静默合并**；差异在
  [sample-vo-timings.json](sample-vo-timings.json) 的 `conflicts` 段逐条说明
  （例：1920x1080@50 BT656 DDR 存在两种水平 porch 分配，htotal 与刷新率一致）。
- 文档（C）与表数据（B/D）冲突时如实呈现双方，说明取舍理由与客户可执行的验证步骤。

## 4. 运行时边界

- 脚本只读取本 skill `references/` 下的内化副本与用户显式传入的文件；**不主动访问 skill 目录以外的路径，也不访问任何外部源码树**；用户显式提供的文件（客户日志/代码/规格书等）可读，但**不主动读取凭据/密钥文件**。
- 客户侧采集路径（proc、dmesg）由客户提供，属于客户环境事实，不受本边界限制。
