# Skill Card: sdk-bsp-memory-partition

| Field | Value |
|---|---|
| name | sdk-bsp-memory-partition |
| owner | SDK Team |
| kind | workflow (reference) |
| riskLevel | high — partition changes and flashing can prevent boot or overwrite data |
| platforms | AX637 / AX637R (ONLY_NAND and ONLY_eMMC); M57 (NOR+NAND) |
| reviewCycle | Each SDK release and partition-schema change |

## Use case

Plan and verify DDR Linux/CMM allocations and FLASH partition layouts, including AB constraints, custom ACore partitions, and NAND adaptation.

## Platform matrix

| Platform id | Scope | Platform facts | Reference routing |
|---|---|---|---|
| `ax637` | AX637 / AX637R memory and FLASH partition | `platforms/ax637.md` | `reference/ax637/` |
| `m57` | M57 memory, FLASH partition (NOR+NAND / ONLY_NAND) | `platforms/m57.md` | `reference/m57/` |

## Known risks

- Demo DDR values are not universal; actual board memory and firmware reservations must be checked.
- NAND bad blocks and block alignment reduce usable capacity.
- BootROM depends on AB SBL sizes and fixed offsets.
- Partition metadata, generated XML/mtdparts, U-Boot definitions, and OTA configuration can diverge.

## Sources

- `platforms/ax637.md` — AX637 platform paths, DDR/CMM baseline, partition constraints (AB/custom ACore partitions), verification details, and reference documentation table
- `platforms/m57.md` — M57 platform paths, DDR/CMM baseline, Inline ECC configuration, partition constraints (NOR+NAND / ONLY_NAND), and reference documentation table
- `reference/ax637/Memory and Storage Allocation.md` — AX637 Memory 和存储空间分配/调整
- `reference/m57/Memory and Storage Allocation.md` — M57 Memory 和存储空间分配/调整
- `reference/m57/flash-scan-tuning.md` — M57 OSPI/QSPI Flash scan 调优
- `reference/m57/nand-filesystem-faq.md` — M57 NAND 访问与文件系统使用
- `build/platforms/axera/<platform>/partitions*.json`
- `boot/uboot/u-boot-2022.10/board/axera/common/m57/common.c`
- `scripts/axp_make.sh`
