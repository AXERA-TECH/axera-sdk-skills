# M57 Linux OTA 知识库

适用于 M57 Linux 的 OTA 分层、部署与排查。整理日期：2026-10-08；SDK release 版本未确认，实现路径与命令需在目标工程核实。

AB 基础状态与 OTA 状态的区别见 [M57 OTA FAQ](M57-OTA-FAQ.md)；底层存储细节按目标 SDK 的 `get_part.sh`、`ota_erash`、`copy_part.sh` 及对应驱动实现继续下钻。

## 1. 核心结论

1. **OTA 是上层升级流程。** 它负责 SWU 包生成、inactive slot 写入、阶段脚本、首次启动验证、可选 sync/recovery。
2. **OTA 只借用 AB，不拥有 AB。** OTA 可以请求 mark unbootable / active / successful；slot 选择、tries、fallback 属于 AB/SBL。
3. **SWU 包生成主线在 `build/scripts/ota`。** 关键输入是 `ota_env.txt`、`sw-description-source`、AXP images、`ota.sh` 模板和 `swugenerator`。
4. **SWUpdate core 是运行时调度者。** `swupdate.sh` / `swupdate.cfg` / `Makefile` 准备运行和验签材料，`swupdate` binary 解析 SWU、验签、调度 scripts/images/handler。
5. **板端 OTA 状态在 BCB 环境中。** `stage=OTA` 表示进入 OTA；`status=state:slot:sync:enable_resume:enable_sync` 是 OTA 自己的阶段状态，不是 AB metadata。
6. **`preinst()` 先保护 target slot。** 写入前 target inactive slot 必须 mark unbootable，避免半写入 slot 被启动。
7. **`postinst()` 只能 mark active。** 安装完成后只能让 target slot 下次优先启动，不能 mark successful。
8. **OTA 成功必须经过首次启动验证。** `ota_check.lua` 验证通过后才能 mark successful；验证失败应 mark unbootable 并 reboot。
9. **sync/recovery 是分区内容复制，不是 AB 回滚。** AB 回滚看 slot metadata；sync/recovery 看 `/dev/link`、`copy_part.sh` 和底层介质操作。
10. **高层逻辑必须使用语义路径。** 不要写死 `/dev/mtdX`、`/dev/mmcblkXpY`，优先使用 `/dev/link` / `/dev/link/ota_*`。
11. **调试源码必须按 rootfs 覆盖顺序取最终版本。** Buildroot package 和 board `fs-overlay` 提供基础内容，`build/scripts/package_rootfs.sh` 随后复制 `build/scripts/init_scripts/`，同名文件会被覆盖；平台级 overlay 还可继续覆盖公共版本。

## 2. 职责域和边界

| 问题域 | 主要入口 | 负责什么 | 不负责什么 |
| --- | --- | --- | --- |
| SWU 包生成与签名 | `swu_make.sh`、`swugenerator`、`sw-description-source`、`swu_sign.py` | 变量替换、artifact 收集、签名、cpio/swu 生成 | 板端运行、首次启动验证、slot 选择 |
| SWUpdate 和平台适配脚本 | `swupdate.sh`、`swupdate.cfg`、`public.key`、`swupdate`、`sw-description`、`swupdate_handlers.lua`、`ota.sh`、`custom_ota.sh`、`ota_check.lua`、`ota_utils.lua` | 板端启动/验签、SWUpdate core 调度、自定义 handler、preinst/postinst、BCB 状态、首次启动验证 | AB 内部选择算法、底层介质差异 |
| sync/recovery | `ota_check.lua`、`copy_part.sh` | 成功后同步对侧分区、失败后恢复分区内容 | AB rollback |
| 存储抽象 | `/dev/link`、`get_part.sh`、`ota_erash`、`copy_part.sh` | 屏蔽 eMMC/NAND/NOR/safety flash 差异，提供语义路径和统一擦写复制入口 | 上层升级策略 |
| AB 依赖 | `abc` + `misc` / `misc_bak`、目标 SDK 的 AB 实现 | 提供 mark active/successful/unbootable 和 fallback 机制 | OTA 业务状态、sync/recovery |

`SWUpdate 和平台适配脚本` 内部不要混为一层：

- `swupdate.sh`：启动包装和参数入口。
- `swupdate` binary / SWUpdate core：解析 SWU、验签、检查 compatibility、调度 scripts/images、按 type 调用 handler。
- `swupdate_handlers.lua`：平台自定义 handler，只处理平台注册的 type，例如 `erase`、`blacklist`、`whitelist`、`raw_fs`。
- `ota.sh` / `ota_check.lua` / `ota_utils.lua`：OTA 阶段状态推进和跨重启验证，不是 SWUpdate core。

Agent 判断顺序：

1. 先判断问题属于 SWU 包生成与签名、SWUpdate 和平台适配脚本、sync/recovery、存储抽象、AB 依赖中的哪一域，再细分到运行/验签、core 调度、handler、preinst/postinst/ota_check。
2. 涉及 slot 选择、tries、fallback 时转目标 SDK 的 AB 实现。
3. 涉及 MTD、eMMC、safety flash、raw flash 读写时，按 `get_part.sh`、`ota_erash`、`copy_part.sh` 和底层驱动实现继续下钻。
4. OTA state、AB metadata、RomCode 临时状态必须分开看，不能互相替代。

## 3. OTA 状态和设计约束

### 3.1 OTA 只在固定时机调用 AB

| OTA 阶段 | AB 操作 | 目的 | 约束 |
| --- | --- | --- | --- |
| `preinst()` | target inactive slot mark unbootable | 防止半写入 slot 被启动 | 不能删除或后移到写入之后 |
| `postinst()` | target slot mark active | 下次启动优先尝试新 slot | 不能 mark successful |
| 首次启动验证成功 | current slot mark successful | 新 slot 成为可信目标 | 必须有验证依据 |
| 首次启动验证失败 | current slot mark unbootable | 失败 slot 不再参与选择 | fallback 由 AB/SBL 选择 |

修改这些时机前必须说明：断电、半写入、验证失败、唯一 successful slot、AB fallback 的后果，并区分这是 OTA 调用时机变化还是 AB 机制变化。

### 3.2 OTA 状态不是 AB metadata

OTA 状态保存在 BCB 环境中：

```text
stage=OTA
status=state:slot:sync:enable_resume:enable_sync
```

| 字段 | 语义 | 关键约束 |
| --- | --- | --- |
| `stage` | 是否处于 OTA 流程。 | 非 `OTA` 时 `ota_check.lua` 应退出。 |
| `state=2` | preinst 后写入中，或 sync/recovery copy 中。 | 断电后按异常处理，不能信任 target slot。 |
| `state=1` | 安装完成，等待首次启动验证。 | target active，但还不是 successful。 |
| `state=3` | 失败/回滚清理路径。 | 应 mark unbootable，并借用 AB fallback。 |
| `slot` | 本次 OTA target slot index。 | 与 slot name `A/B` 不可混用。 |
| `sync=0` | 未进入 sync/recovery copy。 | 默认状态。 |
| `sync=1` | 成功路径的分区同步标记。 | 不等同 AB successful。 |
| `sync=2` | 失败路径的分区恢复标记。 | 不等同 AB rollback。 |
| `enable_resume` | 失败后是否恢复对侧内容。 | `swu_make.sh` 默认 `1`。 |
| `enable_sync` | 成功后是否同步对侧内容。 | `swu_make.sh` 默认 `0`。 |

Agent 规则：

- OTA state 不能替代 AB metadata；AB metadata 也不能替代 OTA stage/state。
- `slot` index (`0/1`) 与 slot name (`A/B`) 是常见 bug 源；调用 `OtaUtils.set_ota_*()` 前确认入参语义。

### 3.3 可信来源和实现索引

本表同时作为实现入口索引；需要源码细节时按问题类型读取，不要把实现细节塞回本文。

| 主题 | 入口 | 必须记住的约束 |
| --- | --- | --- |
| SWU 包生成 | `build/scripts/ota/swu_make.sh`、`build/scripts/ota/swugenerator` | 读取 `ota_env.txt`，解包 AXP，生成 config，替换 `ota.sh`，调用 `swugenerator`。 |
| SWU 内容 | `build/scripts/ota/config/*/sw-description-source` | A/B image、device、handler、script 必须对称且匹配；rdiff/delta 时 `OLD_AXP` 解包后的 `old_*` artifact 必须匹配 `rdiffbase`。 |
| 运行入口 | `rootfs/buildroot-2024.02.2/package/swupdate/swupdate.sh`、`rootfs/buildroot-2024.02.2/board/axera/m57/fs-overlay/etc/swupdate.cfg` | 加载 `conf.d`，选择 `swupdate` binary，拼接 webserver/suricatta/extra 参数。 |
| SWUpdate 基础安装 | `rootfs/buildroot-2024.02.2/package/swupdate/swupdate.mk`、`rootfs/buildroot-2024.02.2/board/axera/m57/fs-overlay/` | 安装 SWUpdate binary/wrapper/handler，并提供 `swupdate.cfg`、`ota_check.lua`、`ota_erash` 等基础文件；不是所有板端文件的最终源码。 |
| 签名实现 | `build/scripts/ota/swugenerator/swu_sign.py`、`build/scripts/ota/swugenerator/main.py` | 生成签名并封装到 SWU。 |
| SWUpdate core | `swupdate`、`sw-description` | 解析 SWU、验签、检查 compatibility、调度 scripts/images、按 type 调用内置/custom handler。 |
| OTA 阶段脚本 | `build/scripts/ota/ota.sh`、`build/scripts/init_scripts/rootfs_overlay/usr/lib/swupdate/ota_utils.lua`、`rootfs/buildroot-2024.02.2/board/axera/m57/fs-overlay/usr/lib/swupdate/ota_check.lua` | 模板替换、BCB/ABC/RomCode 封装、首次启动验证和 sync/recovery；读取前必须再检查下述覆盖顺序。 |
| 最终 rootfs 公共覆盖 | `build/scripts/init_scripts/initd/`、`build/scripts/init_scripts/rootfs_overlay/`、`build/scripts/package_rootfs.sh` | 覆盖基础 rootfs 中的同名启动脚本、`ota_utils.lua`、`get_part.sh`、`copy_part.sh` 等文件。 |
| 项目钩子 | `custom_ota.sh` | preinst/postinst/postfailure 自定义逻辑不应替代基础状态机。 |
| 自定义 handler | `swupdate_handlers.lua` | `erase` / `blacklist` / `whitelist` 只应在 `preinst` 生效；`raw_fs` 先 erase 再链到内置 `raw`；返回非 0 会中止升级。 |
| 分区 layout | `get_part.sh` | 从 `/proc/ax_proc/mtd`、`/proc/ax_proc/emmc_partinfo` 或 `pted` 生成 layout。 |
| 擦除 | `ota_erash` | 分派 MTD/eMMC/file/whitelist/blacklist 擦除清理。 |
| 复制 | `copy_part.sh` | 识别 UBI、EXT、FIT、自定义 image header；否则 fallback 整体复制。 |

`sw-description-source` 中 scripts 顺序也是状态机约束；当前样例是 `erase` / `whitelist` / `blacklist` -> `custom_ota.sh` -> `ota.sh`，调整顺序必须评估 preinst 状态写入和失败路径。

rootfs 中 OTA 文件的来源不是单层目录。判断板端最终内容时必须按打包顺序检查：

```text
Buildroot package + board fs-overlay
  -> build/scripts/init_scripts/initd
  -> build/scripts/init_scripts/rootfs_overlay
  -> build/scripts/init_scripts/platform/<PLATFORM>
  -> build/platforms/**/<PLATFORM>/rootfs_overlay
  -> final rootfs image
```

`build/scripts/package_rootfs.sh` 先把 `initd/S*` 复制到 `/etc/init.d/`，再以 `cp -rpf` 覆盖 `rootfs_overlay`，最后应用两层 platform overlay。因此：

- `build/scripts/init_scripts/rootfs_overlay/usr/lib/swupdate/ota_utils.lua`、`get_part.sh`、`copy_part.sh` 是当前公共打包链中的高优先级来源，会覆盖 Buildroot board `fs-overlay` 中的同名文件。
- `build/scripts/init_scripts/initd/S79ota_check` 会覆盖 Buildroot board `fs-overlay/etc/init.d/S79ota_check`。
- `ota_check.lua` 当前仍来自 Buildroot board `fs-overlay`，但平台 overlay 若提供同路径文件，最终仍以平台版本为准。
- `swupdate.sh`、`swupdate_handlers.lua` 和 SWUpdate binary 主要由 Buildroot package 安装；除非后续 overlay 提供同路径文件，否则沿用 package 版本。
- 调试不能只打开 `rootfs/buildroot-2024.02.2/board/axera/m57/fs-overlay` 中的文件；应先查同名覆盖源，必要时直接核对最终解包 rootfs。

### 3.4 成功闭环必须跨重启

```text
SWUpdate writes inactive slot
  -> postinst mark active + state=1
  -> reboot into target slot
  -> ota_check functional verification
  -> success: mark successful + optional sync + clear OTA state
```

失败闭环：

```text
boot into target slot
  -> verification failed or state abnormal
  -> state=3
  -> current/target slot mark unbootable
  -> reboot
  -> AB/SBL selects fallback according to AB metadata
```

注意：

- “SWUpdate 写完”不是 OTA 成功；“能启动到用户态”也不是 OTA 成功。
- 当前实现中找不到 `axera_test.lua` / `axera_test.sh` 时验证默认通过；需要强验证的项目必须提供验证脚本。
- 如果 SWUpdate 写入阶段失败或断电，可能停留在 `state=2`；当前 `postfailure()` 不承载核心恢复逻辑，后续由 `ota_check.lua` 将异常状态转入 `state=3` 并借用 AB fallback。

### 3.5 sync/recovery 不是 AB rollback

| 项目 | AB rollback | OTA sync/recovery |
| --- | --- | --- |
| 归属 | AB/SBL/metadata | OTA 平台脚本 |
| 对象 | slot 状态 | 分区内容 |
| 触发 | slot 不可用、tries、successful fallback | `enable_sync` / `enable_resume` / `sync` 字段 |
| 动作 | 选择 old successful slot | `axera_AB_sync()` -> `axera_AB_copy()` -> `copy_part.sh` |

约束：

- “回到旧 slot”优先看 AB metadata。
- “对侧分区内容不一致”优先看 sync/recovery。
- `copy_part.sh` 失败不要直接解释成 AB metadata 选择失败。

### 3.6 高层必须使用语义路径

OTA 上层应使用：

```text
/dev/link/<part>
/dev/link/ota_<part>
/dev/link/ota_<part>_a
/dev/link/ota_<part>_b
```

新增介质或分区时，必须同时检查分区 `_a/_b`、`/dev/link/ota_*_a/b`、`get_part.sh`、`ota_erash`、`copy_part.sh`、`abc` / `bcb` 对 `misc` / `misc_bak` 的访问路径。

### 3.7 设计动机和平台约束

这些不是普通实现细节；代码里能看到动作，但不一定能看出为什么：

- SWUpdate 写入完成不等于 OTA 成功：写入只证明 SWU 被调度执行过，不能证明 target slot 重启后可长期运行；successful 必须由目标 slot 的首次启动验证给出。
- `preinst()` 先写 `state=2` 并保护 target slot，是掉电/半写入保护；遗留的“升级进行中”状态应被保守转失败路径，而不是启动半成品 slot。
- `postinst()` 只 mark active，是把新 slot 置为“允许尝试”；active 不能被解释成可信、可同步或可作为 fallback。
- sync/recovery copy 与 SWUpdate 写分区有同样的半成品风险；copy 前后也要保持 target slot 保护和 `state/sync` 证据。
- SWU 生成签名、板端 `public.key` / `swupdate.cfg`、SWUpdate core 验签、`swupdate_handlers.lua` 注册和 `sw-description` type 必须端到端匹配；任一环断开都可能表现为“包能生成但板端不执行/handler 不被调用”。
- `sw-description-source` 的 scripts/images 顺序是状态机的一部分；随意移动 erase/whitelist/blacklist、自定义脚本、`ota.sh`，会改变写入前保护、失败退出和 handler 生效时机。
- `/dev/link` / `/dev/link/ota_*` 是平台存储抽象契约；新增介质/分区时优先补映射和工具适配，不应让 OTA 上层直接感知 eMMC/NAND/NOR/safety flash 的物理名字。

## 4. Debug 入口规则

OTA debug 不另起一套模型，必须按第 2 节五个问题域归因；前文状态语义和调用契约就是主要排查依据。

最小证据按现象取，不要一次性全采：

| 证据 | 用途 |
| --- | --- |
| SWU 生成输入 | 看 `ota_env.txt`、AXP artifact、`sw-description-source`、签名输出，判断包生成/签名/模板替换。 |
| BCB OTA state | 看 `stage/status`，判断 OTA 阶段、`state=1/2/3`、target slot index。 |
| AB metadata + current slot | 判断 active/successful/unbootable、fallback 和实际启动 slot。 |
| SWUpdate log + `sw-description` | 判断验签、compatibility、scripts/images 调度、handler 调用和返回值。 |
| `/dev/link` + storage 工具输出 | 判断语义路径、分区映射、擦除、写入、sync/recovery。 |

Debug 规则：

- 先判问题域：SWU 包生成与签名、SWUpdate 和平台适配脚本、sync/recovery、存储抽象、AB 依赖。
- 定位板端脚本前先按 rootfs 覆盖顺序确认最终来源；同名文件优先检查 `build/scripts/init_scripts/` 和 platform overlay，不能默认 Buildroot `fs-overlay` 就是最终版本。
- 涉及 slot 选择、tries、fallback、successful/unbootable 解释时转目标 SDK 的 AB 实现。
- 涉及 `/dev/link`、MTD、eMMC、safety flash、介质差异时，按 `get_part.sh`、`ota_erash`、`copy_part.sh` 和底层驱动实现继续下钻。
- 不要只凭单一状态下结论；OTA state、AB metadata、current slot、SWUpdate log 至少交叉验证两类。

## 5. UT 生成入口规则

OTA UT 不按源码文件生成，而按“问题域 + 状态迁移 + 边界契约”生成；每个 case 写清 initial BCB status、current slot、AB metadata mock、event、expected action。

必须覆盖：

- SWU 包生成/签名失败、rdiff/delta base 不匹配、`sw-description-source` type 与 handler 不匹配、handler 返回非 0 中止升级。
- `preinst()`：partition pass/fail、A->B、B->A、status 写失败、target unbootable 失败、stage 写失败。
- `postinst()`：mark active 成功/失败、`state=1` 成功/失败、不能 mark successful。
- `ota_check.lua`：not in stage、`state=1` success/fail、`state=2` abnormal、`state=3` cleanup、slot 不一致。
- sync/recovery：disabled/enabled、`sync=1/2`、copy 成功/失败、source/target link 缺失。
- storage abstraction：MTD/eMMC/pted layout、erase 分支、UBI/EXT/FIT/custom/whole-copy。
- slot 参数：slot name `A/B` 与 slot index `0/1` 混用。

断言和 mock 边界：

- 断言 `preinst()` 写入前保护 target slot、`postinst()` 只 mark active、`ota_check` 验证成功才 mark successful、验证失败 mark unbootable 并 reboot。
- 断言 sync/recovery 失败不被误写成 AB metadata 选择失败，高层不写死 `/dev/mtdX` 或 `/dev/mmcblkXpY`。
- 可以 fake `abc` / `bcb`、`devmem`、`/proc/ax_proc/hwinfo/boot-slot`、`/dev/link`、SWUpdate 运行/验签结果、handler 结果、storage 工具结果。
- 不要 fake 掉 OTA state 推进、`state` / `slot` / `sync` 语义、AB 操作时机、sync/recovery 与 AB fallback 的职责边界。

## 6. Agent 硬约束

1. OTA 只借用 AB；slot 选择、tries、fallback、successful/unbootable 解释转目标 SDK 的 AB 实现。
2. `preinst()` 必须在写入前保护 target slot 为 unbootable；`postinst()` 不能 mark successful。
3. OTA state、AB metadata、current slot、RomCode 临时状态不能互相替代。
4. AB rollback 不是 OTA sync/recovery；`copy_part.sh` 失败不要解释成 AB metadata 选择失败。
5. 高层禁止写死 `/dev/mtdX` 或 `/dev/mmcblkXpY`；优先使用 `/dev/link` / `/dev/link/ota_*`，底层介质细节按存储工具和驱动实现继续下钻。
6. 禁止混淆 `swupdate.sh`、`swupdate` core、`swupdate_handlers.lua`，也禁止混用 slot name `A/B` 与 slot index `0/1`。
7. 禁止跳过 rootfs 覆盖链直接以 Buildroot `fs-overlay` 中的同名脚本判断最终行为；公共 `init_scripts` 和 platform overlay 优先级更高。
