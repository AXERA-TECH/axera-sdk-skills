#!/usr/bin/env python3
"""Self-contained structure tests for the sdk-bsp-can-safety skill.

从原 evals/run_evals.py 迁入不依赖 M57 SDK 的检查；SDK 路径与 API 校验
保留在 M57 仓库侧的 evals/run_evals.py 执行。
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT
EVALS = ROOT / "evals"

REQUIRED_SKILL_SECTIONS = [
    *(f"## S{i}：" for i in range(7)),
    "## 输出格式",
    "## 源码位置",
    "## 核心知识",
    "## 信息收集清单",
    "## 常见问题排查表",
    "## 限制与约束",
    "## Sources",
]

FAQ_NAME = "M57 CAN 常见问题解决思路.md"
EB_CONFIG_NAME = "M57 MCAL CAN EB 配置说明.md"
REQUIRED_REFS = {"平台范围.md", "代码地图-mcal.md", FAQ_NAME, EB_CONFIG_NAME}

# 平台门用例的 evidence 签名 + 证据不足反向防御用例
CASE_IDS = {
    "can-001-m57-linux-mcal": ("Chip: M57", "Main project OS: Linux", "Safety CAN framework: AUTOSAR MCAL CAN"),
    "can-002-m57-qnx-mcal": ("Chip: M57", "Main project OS: QNX", "Safety CAN framework: AUTOSAR MCAL CAN"),
    "can-003-ax637r-reject": ("Chip: AX637R", "Safety CAN framework: RTT RTOS CAN"),
    "can-004-m57-busoff-inconclusive": ("Chip: M57", "Symptom: CAN Bus-Off"),
}


class SkillStructureTests(unittest.TestCase):
    def test_skill_frontmatter_and_sections(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: sdk-bsp-can-safety", text)
        for section in REQUIRED_SKILL_SECTIONS:
            self.assertIn(section, text, "SKILL.md missing section: " + section)

    def test_reference_whitelist(self):
        refs = {path.name for path in (SKILL / "references").iterdir() if path.is_file()}
        self.assertEqual(sorted(refs), sorted(REQUIRED_REFS))

    def test_faq_sections(self):
        text = (SKILL / "references" / FAQ_NAME).read_text(encoding="utf-8")
        for section in ("CAN Bus-Off", "CAN 中断处理时间过长", "CAN TX 失败", "RX Enhanced FIFO"):
            self.assertIn(section, text, "FAQ missing section: " + section)

    def test_eb_config_sections(self):
        text = (SKILL / "references" / EB_CONFIG_NAME).read_text(encoding="utf-8")
        for section in (
            "CAN MB 数量说明", "CAN RX MB / Enhance FIFO", "CAN FD 采样点说明",
            "CAN RX 过滤说明", "CAN RX DMA 说明",
        ):
            self.assertIn(section, text, "EB config reference missing section: " + section)

    def test_code_map_evidence_routes(self):
        text = (SKILL / "references" / "代码地图-mcal.md").read_text(encoding="utf-8")
        for evidence in (
            "CanBusoffProcessing", "CanAutoBusOffRecovery", "Can_MainFunction_BusOff",
            "CanIf_ControllerBusOff", "Can_Write", "CanControllerFdISO",
            "CanRxFiFo", "CanFiFoOverflowNotif", "Can_pEnhanceFiFoOvfNotif",
            "MBDSR0/1/2", "CanControllerPropSeg", "CanHwFilter",
            "CanEnhanceFiFoDmaEnable", "CAN_*_ERFIFO_DMA_ENABLE",
        ):
            self.assertIn(evidence, text, "code map missing evidence route: " + evidence)

    def test_eval_json_contract(self):
        data = json.loads((EVALS / "evals.json").read_text(encoding="utf-8"))
        allowed = {
            "m57-qnx-safety-mcal", "m57-linux-safety-mcal",
            "reject-ax637-rtt", "reject-ax637r-rtt", "reject-m57-baremetal",
        }
        self.assertEqual({item["id"] for item in data["evals"]}, allowed)
        for item in data["evals"]:
            for key in ("id", "prompt", "expected", "source"):
                self.assertTrue(item.get(key), "eval case incomplete: " + str(item.get("id")))

    def test_trigger_evals_contract(self):
        items = json.loads((EVALS / "trigger-evals.json").read_text(encoding="utf-8"))
        queries = [item.get("query") for item in items]
        self.assertEqual(len(queries), len(set(queries)), "duplicate trigger queries")
        positive = 0
        for item in items:
            for key in ("query", "should_trigger", "source"):
                self.assertIsNotNone(item.get(key), "trigger case incomplete: " + str(item.get("query")))
            self.assertIsInstance(item["should_trigger"], bool)
            positive += bool(item["should_trigger"])
        self.assertTrue(0 < positive < len(items), "trigger cases must mix positive and negative")

    def test_golden_case_layout(self):
        actual = sorted(path.name for path in (EVALS / "cases").iterdir() if path.is_dir())
        self.assertEqual(actual, sorted(CASE_IDS), "unexpected case directories")
        for case_id, signatures in CASE_IDS.items():
            case_dir = EVALS / "cases" / case_id
            self.assertTrue((case_dir / "case.yaml").is_file(), case_id + " missing case.yaml")
            self.assertTrue((case_dir / "assert.sh").is_file(), case_id + " missing assert.sh")
            evidence = (case_dir / "fixtures" / "evidence.txt").read_text(encoding="utf-8")
            for signature in signatures:
                self.assertIn(signature, evidence, case_id + " evidence missing: " + signature)
            case_text = (case_dir / "case.yaml").read_text(encoding="utf-8")
            self.assertIn("sdk-bsp-can-safety", case_text, case_id + " prompt must target the skill")
            self.assertIn("out/result.md", case_text, case_id + " must declare output contract")
            self.assertIn("evidence.txt", case_text, case_id + " prompt must read evidence")

    def test_install_projection_excludes_evals(self):
        runtime = ("SKILL.md", "agents", "references")
        for item in runtime:
            self.assertTrue((SKILL / item).exists(), "runtime path missing: " + item)
        self.assertTrue((SKILL / "scripts" / "install.py").is_file())
        installed = SKILL / "installed-bundle"
        self.assertFalse(installed.exists(), "installed-bundle must not be committed")


if __name__ == "__main__":
    unittest.main()
