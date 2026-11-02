# M57 OTA FAQ

**主题**：M57 OTA · SWUpdate · A/B 分区 · 版本校验 · 回滚与恢复

**适用**：M57 平台，Linux / QNX 双系统。除特别注明外，结论为两种系统的共性；Linux 和 QNX 的实现差异按各节说明区分。

**技术依据**：[Linux OTA 知识库](Linux-OTA-知识库.md)、[QNX OTA 知识库](QNX-OTA-知识库.md)及 [M57 SDK OTA 使用说明](AX-SDK-OTA使用说明.md)。本文归纳排查方法，不证明某个 SDK 版本存在或已修复特定缺陷；实现需在目标 SDK 核实。

---

客户可直接引用的答案
----------

本节是面向客户和 AI 的“一问一答”版本。回答中的命令是取证模板，设备上的实际工具名称和分区路径必须以 `/dev/link`、板端版本及 Linux/QNX 环境为准；不要把示例中的设备编号直接写入脚本。

### OTA 显示 `SWUPDATE successful`，现在可以拔电或交付了吗？

不能。该提示只表示 SWUpdate 已完成本次镜像调度/写入，不表示新 slot 已被验证。正确闭环是：设备重启进入 target slot，`ota_check.lua` 完成功能验证，验证成功后才会 mark successful；验证失败则 mark unbootable，由 AB/SBL 回退到旧的 successful slot。交付判据是“重启后验证通过且 AB metadata 中 current slot=successful”，不能只看网页提示。

### 升级后设备启动失败或反复重启，怎样恢复？

先停止重复刷写，保留现场并读取三组信息：BCB 的 `stage/status`、AB metadata（active/successful/unbootable/tries）和实际启动 slot。若目标 slot 未通过验证，将该 slot 标记为 unbootable 后重启，AB/SBL 才会按 tries 和 successful 状态选择旧 slot；不要把 reset 当成强制 rollback 命令。若旧 slot 也不可启动，需进入板端恢复流程重新写入已知可启动的完整 SWU。

### `state=1`、`state=2`、`state=3` 分别代表什么？

在 `stage=OTA` 时，`status=state:slot:sync:enable_resume:enable_sync` 中：`state=2` 是写入或复制进行中，断电后不得信任 target slot；`state=1` 是安装完成、等待重启后的首次启动验证，**不是** successful；`state=3` 是失败清理路径，应将失败 slot 标记为 unbootable 并交给 AB/SBL fallback。`slot` 是 index `0/1`，不是字符串 `A/B`；`sync=1/2` 是内容同步/恢复标记，也不是 rollback 标记。

### 为什么写入前必须把 inactive slot 设为 unbootable？

这是掉电保护。`preinst()` 必须在任何镜像写入前保护 target slot，并写入 `state=2`，避免半写入镜像被启动；写入完成后 `postinst()` 只能 mark active，表示“下次允许尝试”，不能提前 mark successful。只有目标 slot 重启并通过 `ota_check.lua` 验证后才允许 mark successful。若现场发现顺序相反，应判定为升级状态机缺陷并先修复脚本顺序。

### 报 `Partition check failed` 或分区大小不一致，应该改哪里？

不要先改分区号。先确认三项是否来自同一版本：生成 SWU 使用的旧版本 AXP/layout、板端实际 layout、`/dev/link` 的语义映射。Linux 可查看 `/proc/mtd` 和 `/proc/ax_proc/emmc_partinfo`；QNX 可查看 `/proc/ax_proc/mtd`、`pted` 及 `/dev/link`。移除 TF/U 盘等可移动介质后重新生成与目标板匹配的 SWU。禁止在代码中写死 `/dev/mtdX`、`/dev/mmcblkXpY` 或 QNX 的设备编号。

### 差分包报 `rdiff_image` 缺失或 `RDIFF_BUFFER_SIZE` 断言失败，能否重试？

不能直接重试同一个包。重新确认板端 SWUpdate 构建启用了 rdiff handler，且生成包时 `OLD_AXP` 与 `rdiffbase` 指向该设备当前版本的同一 artifact；不匹配就改用完整包或重新生成差分包。QNX 还必须确认差分实现的 buffer 上限。重新升级前清理停留在 `state=2` 的目标 slot，并保存失败日志。

### 为什么 `0.3.10` 和 `0.13.0` 的版本比较会出错？

版本必须按数字段进行语义化比较：`0.3.10 < 0.13.0`，不能按字符串或字典序逐字符比较。升级前若 SWU 版本低于当前版本应拒绝安装，只有项目明确允许降级时才放行；同时统一 `_P1` 等后缀的解析规则，并在包生成和板端各做一次版本日志记录。

### 更换 Secure Boot key 后 OTA 包验签失败，怎样判断是哪把 key 不对？

按链路逐项核对：生成端签名 key → SWU 中的签名 → 板端 `public.key` → `swupdate.cfg`/验签配置。四者必须属于同一信任链；Secure Boot key 与 OTA key 是否分离以项目安全方案为准。先在不刷写的条件下验证 key 指纹和 SWU 验签日志，确认一致后再升级。签名失败时不得继续写入或把结果解释为分区问题。

### OTA 包损坏了 SPL 或启动镜像，失败后会自动回滚吗？

只有在目标 slot 被正确标记为不可启动且 AB metadata 保留旧 successful slot 时，AB/SBL 才能回退。损坏镜像应在验签/checksum 或首次启动验证阶段失败；测试时必须确认失败 slot 的 `unbootable`、旧 slot 的 `successful` 和 tries 变化，并保存 SBL/Main/Safety 日志。不要把“rootfs 写入完成”当作启动镜像可用。

### Linux 和 QNX 的擦除、设备路径可以互换吗？

不可以。Linux 使用最终 rootfs 中的 `ota_erash`，QNX 使用 `ota_erase`；两者的 handler、设备节点和文件系统实现不同。上层统一使用 `/dev/link`、`/dev/link/ota_*`，Linux 继续下钻 MTD/UBI/eMMC，QNX 继续下钻 ETFS/MTD、`/dev/emmc0.ms.N` 和 `slog2info`。QNX ETFS 不能按 Linux 裸 MTD 的 512 字节方式拆包写入，必须使用 QNX 适配镜像和 handler。

### `sync` 失败是不是 AB rollback 失败？

不是。AB rollback 只负责选择哪个 slot 启动，依据是 active/successful/unbootable/tries；`sync/recovery` 负责用 `copy_part.sh` 复制对侧分区内容，受 `enable_sync`、`enable_resume` 和 `sync` 字段控制。看到“回到旧 slot”先查 AB metadata；看到“对侧内容不一致/空间不足”再查 `/dev/link`、分区空间和 copy 日志。两类问题不能互相替代。

### 断电、断网或上传会话中断后，能否从 `state=2` 继续？

默认不能信任半写入目标 slot。保留 `state/status`、SWUpdate 日志和上传错误，按异常路径将 OTA 状态转入清理（`state=3`），确认目标 slot 不可启动后重新发起完整升级；只有项目明确实现并验证了 resume，才允许按 `enable_resume` 走恢复流程。QNX 取证使用 `slog2info`，Linux 使用系统/SWUpdate 日志。

### 客户只提供一句“升级失败”，最少需要回传什么？

请一次回传以下可复现证据：设备当前版本和目标版本；SWU 的 `sw-description`、兼容性/签名结果及 `OLD_AXP`/`rdiffbase`；完整 SWUpdate 日志；BCB `stage/status`；AB metadata 与实际启动 slot；`/dev/link` 和分区信息；擦除、写入、sync/copy 输出。Linux 另附 `/proc/mtd` 或 emmc 分区信息，QNX 另附 `/proc/ax_proc/mtd`、`pted`、`slog2info` 和 SBL/Main/Safety 日志。没有这些证据时只能给排查方向，不能确认根因。

以上“一问一答”给出的是默认行为；若项目通过 `custom_ota.sh`、平台 overlay 或定制 SBL 改写了行为，必须以最终 rootfs 和板端实现为准。

---

问题排查速查
------

下表按现象提供排查入口；可能原因需结合目标 SDK 和现场证据确认。

| 类型 | 问题 | 环境 | 复现和解决方案 |
|---|---|---|---|
| OTA流程 | OTA 显示 SWUPDATE successful ，是否代表升级成功？ | Linux / QNX | 不代表。SWUpdate 只完成镜像写入；设备必须重启进入目标 slot，由 ota_check.lua 完成首次启动验证，验证通过后才能 mark successful。验证失败应 mark unbootable 并由 AB/SBL 选择 fallback。 |
| OTA流程 | 为什么写入前要将目标分区设为 unbootable？ | Linux / QNX | preinst() 在写入 inactive slot 前先保护目标 slot，避免断电或半写入镜像被启动；写入完成后 postinst() 只能设置 active，不能直接设置 successful。 |
| OTA流程 | OTA 状态中的 stage 、 state 、 slot 、 sync 如何解释？ | Linux / QNX | BCB 环境使用 stage=OTA 和 status=state:slot:sync:enable_resume:enable_sync 。 state=1 表示等待首次启动验证， state=2 表示写入/复制中， state=3 表示失败清理；slot 是 index（0/1），不能与 A/B 名称混用； sync=1/2 分别表示同步/恢复，不等同 AB successful/rollback。 |
| AB切换 | 升级故障包后反复重启或无法回滚，应该先查什么？ | Linux / QNX | 先分别读取 OTA state、AB metadata 和实际启动 slot；不要只看网页上的升级结果。确认目标 slot 的 tries、active/successful/unbootable 状态，再判断是 AB fallback 还是 OTA sync/recovery 问题。 |
| AB切换 | 为什么按 reset 后没有立即切回旧分区？ | Linux / QNX | AB 的切换由 SBL/AB metadata 的 tries 和 successful 状态决定，reset 本身不是强制 rollback 命令。检查目标 slot 是否被正确标记、tries 是否递减，以及 Safety/Main 两侧 slot 是否一致。 |
| 分区校验 | OTA 报 Partition check failed 或分区大小不一致怎么办？ | Linux | 检查生成 SWU 时的旧版本 AXP、当前板端 layout 和 /dev/link 映射；不要把 TF/U 盘等可移动介质分区纳入 OTA layout。分区号不固定，不能写死 /dev/mtdX 或 /dev/mmcblkXpY 。 |
| 分区校验 | QNX 出现 mtdparts 校验失败或分区配置与实际设备不一致怎么办？ | QNX | 使用 cat /proc/ax_proc/mtd 和 /dev/link 核对实际映射，检查 ETFS/MTD 启动顺序及分区表来源；QNX 设备节点和注册顺序不能按 Linux 的 mtd 编号推断。 |
| 差分升级 | 差分升级提示 rdiff_image 缺失或 RDIFF_BUFFER_SIZE 断言失败怎么办？ | Linux / QNX | 确认板端 SWUpdate 已启用对应 rdiff feature；生成差分包时 OLD_AXP 必须与 rdiffbase 对应，不能使用错误的旧版本或错误的 artifact。QNX 还需检查差分实现的 buffer 限制。 |
| 版本校验 | 降级检测未识别低版本，或 0.3.10 与 0.13.0 比较结果异常怎么办？ | Linux / QNX | 版本比较必须按语义化版本解析，不能按字符串/字典序逐字符比较；同时确认 _P1 等分支版本后缀的解析规则。升级前应拒绝低于当前版本的 SWU，除非显式允许降级。 |
| 签名安全 | 更换 Secure Boot key 后 OTA 包无法升级怎么办？ | Linux / QNX | OTA 包签名链必须端到端匹配：生成端签名 key、板端 public.key 、 swupdate.cfg 和 SWUpdate 验签配置必须一致。Secure Boot key 与 OTA key 是否分离也要按项目方案确认。 |
| 签名安全 | OTA 包包含损坏的 SPL/启动镜像时为什么会失败？ | Linux / QNX | 损坏的启动镜像应在验签、checksum 或首次启动验证阶段失败，不能当作普通 rootfs 写入成功处理。确认故障包只用于测试，失败后目标 slot 被标记为不可启动，并验证 fallback。 |
| 存储写入 | OTA 前擦除分区报 Lua handler 参数错误怎么办？ | Linux / QNX | 检查 sw-description-source 中 erase / whitelist / blacklist 的参数类型和 scripts 顺序；自定义 handler 必须返回非 0 时中止升级。Linux 使用 ota_erash ，QNX 使用 ota_erase ，不要混用文件名或实现。 |
| 存储写入 | NAND 写入遇到坏块、OTA 同步失败怎么办？ | Linux / QNX | 先确认启动阶段坏块扫描已执行，再检查底层 erase/write 返回值和坏块标记；同步失败属于存储复制问题，不要直接解释成 AB metadata 选择失败。QNX 需继续下钻 ETFS/ ax_mtd ，Linux 需检查 MTD/UBI。 |
| 存储写入 | OTA 后 AB 同步/失败恢复提示空间不足怎么办？ | Linux / QNX | 检查对侧分区可用空间、userdata/rootfs 分区大小和 copy_part.sh /恢复路径； enable_sync 与 enable_resume 是内容复制开关，不是 AB rollback 开关。 |
| QNX文件系统 | QNX ETFS 分区能否像 Linux 裸 MTD 一样按字节拆包写入？ | QNX | 不建议。ETFS 使用 data + spare(OOB) 组织文件， etfsctl 有 page + etfs_trans 粒度；SWUpdate 默认 512 字节分笔写可能破坏 ETFS 事务格式，应使用 QNX 适配的镜像和 handler。 |
| QNX启动 | QNX OTA 后 kernel/uboot 启动异常或 startup 卡住怎么办？ | QNX | 先区分镜像写入、AB 切换和启动阶段问题：检查 bcb / abc 工具、Main/Safety slot 一致性、ETFS 挂载和 SBL 日志。QNX 使用 /dev/emmc0.ms.N 等设备路径，不能套用 Linux 的节点名。 |
| 网络升级 | 下载镜像过程中断电、断网或重新上传 SWU 后状态异常怎么办？ | Linux / QNX | 检查 SWUpdate 网络连接超时、上传会话和 OTA state；中断后不能继续信任半写入目标 slot，应按 state=2 异常路径清理并重新发起完整升级。QNX 日志使用 slog2info ，与 Linux 网络超时日志表现不同。 |
| 性能稳定性 | OTA 刷写耗时过长、重启时间过长或触发外部 watchdog 怎么办？ | Linux / QNX | 分别统计下载、擦除、写入、sync/recovery、首次启动验证和 AB fallback 耗时；不要只看网页端总耗时。NAND/ETFS、IPC 写 R 核分区、umount busy 和 watchdog 都需要单独定位。 |
| 调试方法 | OTA 失败最少需要收集哪些证据？ | Linux / QNX | 至少交叉收集两类：SWU 生成输入和签名输出；BCB stage/status ；AB metadata 与实际启动 slot；SWUpdate 日志及 sw-description ； /dev/link 、分区 layout、擦除/复制工具输出。定位脚本时先确认最终版本来源：Linux 检查 Buildroot 与 rootfs overlay 覆盖链，QNX 检查 msp/sample/ota/swupdate 部署结果。 |

---

Linux 实现速查
---------

下表仅列出可确认的 Linux 信息；QNX 部署、设备节点和日志工具见 [QNX OTA 知识库](QNX-OTA-知识库.md)。

| 项目 | Linux 实现 |
|---|---|
| OTA 脚本部署 | Buildroot package + build/scripts/init_scripts/ + platform overlay |
| 擦除工具 | ota_erash （以最终 rootfs 为准） |
| 分区/设备抽象 | /dev/link 、 /dev/link/ota_* ；底层可能是 /dev/mtdX 、 /dev/mmcblkXpY |
| 分区信息 | /proc/mtd 、 /proc/ax_proc/emmc_partinfo |
| 文件系统差异 | MTD/UBI/EXT/FIT |
| 日志与验证 | ota_check.lua 、系统日志 |

设计知识与 AI 排查规则
-------------

### 1. OTA 分层边界

| 层次 | 入口 | 负责内容 |
|---|---|---|
| SWU 生成与签名 | build/scripts/ota/swu_make.sh 、 swugenerator 、 sw-description-source | 变量替换、AXP artifact 收集、差分基线、签名和 SWU 封装 |
| SWUpdate core | swupdate 、 swupdate.sh 、 swupdate.cfg | 解析 SWU、验签、compatibility 检查、调度 scripts/images/handler |
| 平台 handler | swupdate_handlers.lua | erase 、 whitelist 、 blacklist 、 raw_fs 等平台注册的 type |
| OTA 状态脚本 | ota.sh 、 ota_check.lua 、 ota_utils.lua | BCB OTA 状态、preinst/postinst、首次启动验证、sync/recovery |
| 存储抽象 | /dev/link 、 get_part.sh 、 ota_erash / ota_erase 、 copy_part.sh | 分区映射、擦除、复制，屏蔽 MTD/eMMC/NAND/NOR/ETFS 差异 |
| AB/SBL | abc 、 bcb 、SBL AB 管理 | active、successful、unbootable、tries 和 fallback |

`swupdate.sh`、`swupdate` core、`swupdate_handlers.lua` 和 `ota.sh` 不是同一层。分析“包生成成功但板端不执行”时，必须沿 SWU 生成 → 板端验签 → core 调度 → handler → OTA 状态脚本逐层确认。

### 2. OTA 状态机和不可替代的证据

```text
SWUpdate 写入 inactive slot
-> preinst 保护 target slot，写入 state=2
-> postinst mark active，写入 state=1
-> reboot 进入 target slot
-> ota_check.lua 首次启动功能验证
-> success: mark successful + 可选 sync + 清理 OTA 状态
```

失败路径：

```text
写入/验证失败或状态异常
-> state=3
-> current/target slot mark unbootable
-> reboot
-> AB/SBL 按 metadata 选择 fallback
```

必须区分以下三类状态：

1. **OTA state**：BCB 中的 `stage/status`，描述 OTA 流程阶段；
2. **AB metadata**：描述 slot 的 active、successful、unbootable、tries；
3. **RomCode/SBL 临时状态**：描述启动阶段的实际选择和跨域同步。

三者不能互相替代。`state=1` 只表示等待验证，不表示 successful；`sync=1/2` 只表示分区内容同步/恢复，不表示 AB rollback。

### 3. AI 问题归因顺序

收到 OTA 问题时按以下顺序判断，避免从单条日志直接猜测根因：

1. **包生成/签名**：检查 `ota_env.txt`、AXP、`OLD_AXP`、`sw-description-source`、签名输出和 `rdiffbase`；
2. **SWUpdate 执行**：检查 compatibility、验签、scripts/images 顺序、handler type 和 handler 返回值；
3. **写入前保护**：确认 `preinst()` 是否先 mark target unbootable 并写入 `state=2`；
4. **安装完成状态**：确认 `postinst()` 是否只 mark active 并写入 `state=1`，没有提前 mark successful；
5. **首次启动验证**：确认 `ota_check.lua` 是否实际执行、验证脚本是否存在、验证失败是否 mark unbootable；
6. **AB fallback**：仅在确认 OTA 状态后，再检查 active/successful/unbootable、tries、current slot 以及 Main/Safety slot 是否一致；
7. **sync/recovery**：若现象是对侧分区内容不一致，再检查 `enable_sync`、`enable_resume`、`sync` 和 `copy_part.sh`；
8. **存储介质**：最后下钻 `/dev/link`、layout、MTD/eMMC/NAND/NOR/ETFS 和 erase/copy 具体实现。

最小证据应至少交叉验证两类：`stage/status`、AB metadata/current slot、SWUpdate log/`sw-description`、SWU 生成输入、`/dev/link` 和存储工具输出。

### 4. 常见设计约束

* `preinst()` 必须在任何镜像写入前保护 target slot；调整顺序必须评估断电、半写入和唯一 successful slot 风险。
* `postinst()` 只能 mark active；successful 必须由目标 slot 首次启动验证产生。
* `sw-description-source` 的 scripts 顺序属于状态机：`erase`/白名单/黑名单、自定义脚本和 `ota.sh` 不能随意调换。
* 高层代码使用 `/dev/link` 和 `/dev/link/ota_*`，不得写死 `/dev/mtdX`、`/dev/mmcblkXpY` 或 QNX 的具体设备编号。
* AB rollback 处理 slot 选择；OTA sync/recovery 处理分区内容复制，二者的失败不能混为一谈。
* rootfs 中同名 OTA 文件必须按最终覆盖链判断：Linux 检查 Buildroot package、`build/scripts/init_scripts/` 和 platform overlay；QNX 检查 `msp/sample/ota/Makefile` 和 `msp/sample/ota/swupdate/` 的最终部署结果。
* QNX ETFS 不是普通 Linux 裸 MTD，不能按 512 字节随意拆包写入；需遵守 page + `etfs_trans` 粒度和 QNX handler 约束。

### 5. UT 和回归用例设计入口

OTA UT 应按“问题域 + 状态迁移 + 边界契约”设计，每个 case 明确 initial BCB status、current slot、AB metadata mock、event 和 expected action。至少覆盖：

* SWU 签名失败、差分基线不匹配、type/handler 不匹配、handler 返回非 0；
* `preinst()` 的 A→B/B→A、分区失败、状态写失败、target unbootable 失败；
* `postinst()` mark active 成功/失败、`state=1` 成功/失败，以及禁止 mark successful；
* `ota_check.lua` 的非 OTA stage、state=1 成功/失败、state=2 异常、state=3 清理和 slot 不一致；
* sync/recovery 开关、`sync=1/2`、copy 成功/失败、source/target link 缺失；
* MTD/eMMC/pted layout、erase 分支、UBI/EXT/FIT/custom/whole-copy；
* slot name `A/B` 与 slot index `0/1` 混用，以及 Linux/QNX 设备路径差异。

维护规则
----

1. 新增问答优先合并到已有问题类型，明确现象、适用环境和可验证的排查步骤。
2. 解决方案必须注明适用系统；Linux 和 QNX 行为不同的条目不得写成无条件通用结论。
3. 缺少实现和日志证据时，只给排查入口，不把可能原因写成已确认根因。
4. 修改 `preinst()`、`postinst()`、`ota_check.lua`、AB 操作时机或存储抽象前，必须同步评估断电、半写入、fallback 和跨系统差异。
