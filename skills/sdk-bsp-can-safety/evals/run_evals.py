#!/usr/bin/env python3
"""Validate M57 SDK source paths and public APIs referenced by the CAN skill.

本脚本在 M57 仓库侧运行（skill 目录位于 agent_rules submodule 内），
校验 skill 引用的 SDK 源码、手册路径和公开 API 是否存在。
本检查需要完整 M57 SDK 及原有 agent_rules 目录布局，独立技能包不能直接执行。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parent
# agent_rules/common/skills/domain/bsp/<skill> -> M57 workspace
WORKSPACE = SKILL.parents[5]

SOURCE_PATHS = [
    "SafetyIsland/mcal/mcal_drv/Can/inc/Can.h",
    "SafetyIsland/mcal/mcal_drv/Can/src/Can.c",
    "SafetyIsland/mcal/mcal_drv/Can/src/Can_Flexcan.c",
    "SafetyIsland/mcal/mcal_drv/Can/src/Can_Irq.c",
    "SafetyIsland/mcal/mcal_drv/CanIf/inc/CanIf_Cbk.h",
    "SafetyIsland/mcal/mcal_drv/CanIf/src/CanIf_Cbk.c",
    "SafetyIsland/mcal/plugins/Can/config/Can.xdm",
    "SafetyIsland/mcal/mcal_config/generated/include/Can_Cfg.h",
    "SafetyIsland/mcal/mcal_config/generated/src/Can_PBcfg.c",
    "SafetyIsland/mcal/plugins/Can/Doc/AXERA-M57 MCAL CAN UM.docx",
]


def main():
    failures = []
    for relative in SOURCE_PATHS:
        if not (WORKSPACE / relative).exists():
            failures.append(f"source path missing: {relative}")

    api_text = (WORKSPACE / "SafetyIsland/mcal/mcal_drv/Can/inc/Can.h").read_text(
        encoding="utf-8", errors="ignore"
    )
    canif_text = (WORKSPACE / "SafetyIsland/mcal/mcal_drv/CanIf/inc/CanIf_Cbk.h").read_text(
        encoding="utf-8", errors="ignore"
    )
    for api in (
        "Can_Init", "Can_DeInit", "Can_SetControllerMode", "Can_Write",
        "Can_GetControllerErrorState", "Can_GetControllerTxErrorCounter",
        "Can_GetControllerRxErrorCounter", "Can_MainFunction_Read",
        "Can_MainFunction_Write", "Can_MainFunction_BusOff", "Can_MainFunction_Mode",
    ):
        if not re.search(rf"\b{re.escape(api)}\b", api_text):
            failures.append(f"API missing from Can.h: {api}")
    for callback in ("CanIf_TxConfirmation", "CanIf_RxIndication", "CanIf_ControllerBusOff"):
        if callback not in canif_text:
            failures.append(f"callback missing from CanIf_Cbk.h: {callback}")

    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[PASS] SDK source paths and public APIs referenced by the skill")
    return 0


if __name__ == "__main__":
    sys.exit(main())
