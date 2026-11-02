# sdk-bsp-memory-partition

面向 AX637/AX637R 与 M57 平台的 DDR 内存与 FLASH 分区规划、定制与校验 Skill。

- **AX637 / AX637R**：ONLY_NAND、ONLY_eMMC、AB 约束、自定义 ACore 分区
- **M57**：NOR+NAND 双 Flash、Inline ECC、NAND 适配与 mtd scan 调优

## 目录结构

| 路径 | 说明 |
|---|---|
| `SKILL.md` | Skill 主体：用途、触发时机、执行步骤与安全约束 |
| `skill-card.md` | Skill 元信息卡片、平台矩阵、已知风险 |
| `routing.yaml` | 工作区自动检测规则与平台路由 |
| `platforms/ax637.md` | AX637/AX637R 平台事实：路径、DDR/CMM 基线、分区约束、参考文档表 |
| `platforms/m57.md` | M57 平台事实：路径、DDR/CMM 基线、Inline ECC、分区约束、参考文档表 |
| `reference/ax637/` | AX637 参考文档（Memory 与存储空间分配等） |
| `reference/m57/` | M57 参考文档（Memory 分配、Flash scan 调优、NAND FAQ 等) |
| `evals/` | 平台评测样例 |

## 使用方式

1. 由 Skill 触发器自动选中，或用户显式传入 `platform=ax637` / `platform=m57`。
2. 路由按 `routing.yaml` 匹配当前 workspace（如 `board-AX637`、`SafetyIsland/rt-thread` 或 `SafetyIsland/mcal`；不按随包的 board 目录名判断）。
3. 加载对应 `platforms/<id>.md`，按 `SKILL.md` 中步骤执行 DDR/分区调整与校验。
4. 未识别到平台时执行 `fallback: ask`，不做臆测。

## 适用场景

- 修改 Linux/CMM 内存大小或地址
- 调整、新增、删除或审计 `partitions.json` / mtdparts
- 扩容 `rootfs`，比较 ONLY_NAND / ONLY_eMMC / NOR+NAND 布局
- 排查 AXDL 或 OTA 打包后的分区不一致
- M57 NAND mtd scan 参数与 Flash 控制器调优

## 安全提示

分区改动可能导致设备无法启动或数据丢失。改动前请备份原 JSON 与打包产物，展示 diff 并在确认后再刷写；不要随意修改 AB SBL、MCU boot 分区或 BootROM 依赖的偏移。

## 开发与维护
