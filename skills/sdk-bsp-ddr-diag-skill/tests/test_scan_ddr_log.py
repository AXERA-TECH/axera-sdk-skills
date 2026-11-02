import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SKILL_DIR = ".axap/opencode/skills/marketplace/sdk-bsp-ddr-diag-skill"


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


installer = module("install")


def scan(logfile):
    result = subprocess.run(
        ["sh", str(ROOT / "scripts" / "scan_ddr_log.sh"), str(logfile)],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout


class ScanScriptTests(unittest.TestCase):
    def test_usage_without_logfile(self):
        result = subprocess.run(["sh", str(ROOT / "scripts/scan_ddr_log.sh")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("用法", result.stdout)

    def test_missing_logfile_exits_2(self):
        returncode, _ = scan(FIXTURES / "no-such.log")
        self.assertEqual(returncode, 2)

    def test_training_fail_branch(self):
        returncode, out = scan(FIXTURES / "DDR3_FAIL_1.log")
        self.assertEqual(returncode, 0)
        self.assertIn("检测到 Training 阶段失败", out)
        self.assertIn("FAQ-006 / FAQ-007", out)

    def test_training_fail_anchors_extracted_from_log(self):
        # 文件名为 LPDDR2，但内容实际是 DDR3 fallback 日志，锚点必须如实提取
        _, out = scan(FIXTURES / "LPDDR2_FAIL_1.log")
        self.assertIn("dram type is DDR3", out)
        self.assertIn("2133Mbps", out)

    def test_pass_logs_report_no_failure(self):
        for name in ("DDR2_PASS.log", "DDR3_PASS.log", "LPDDR2_PASS.log", "LPDDR3_PASS.log"):
            with self.subTest(log=name):
                _, out = scan(FIXTURES / name)
                self.assertIn("未发现明确的 DDR 初始化/训练失败关键字", out)
                self.assertNotIn("检测到 Training 阶段失败", out)
                self.assertNotIn("检测到 BIST 测试失败", out)

    def test_pass_log_anchors(self):
        _, out = scan(FIXTURES / "DDR2_PASS.log")
        self.assertIn("dram type is DDR2", out)
        self.assertIn("1333Mbps", out)
        _, out = scan(FIXTURES / "LPDDR3_PASS.log")
        self.assertIn("dram type is LPDDR3", out)
        self.assertIn("2133Mbps", out)

    def test_dfi_timeout_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "dfi.log"
            log.write_text("ddr init start...\ndfi polling  timeout ......!\npolling read eye training timeout!\n", encoding="utf-8")
            _, out = scan(log)
            self.assertIn("检测到 DFI 轮询超时", out)
            self.assertIn("FAQ-DDR-005", out)

    def test_bist_fail_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "bist.log"
            log.write_text("ddr init start...\nread eye training pass!\nbist fail\n", encoding="utf-8")
            _, out = scan(log)
            self.assertIn("检测到 BIST 测试失败", out)
            self.assertIn("FAQ-008 / FAQ-009", out)


class InstallTests(unittest.TestCase):
    def install(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        bundle = Path(temp.name) / "bundle"
        installer.install(bundle)
        return bundle, bundle / SKILL_DIR

    def test_bundle_includes_runtime_files_only(self):
        bundle, skill = self.install()
        self.assertTrue((skill / "SKILL.md").is_file())
        self.assertTrue((skill / "agents/openai.yaml").is_file())
        self.assertTrue((skill / "reference/eval_contract.md").is_file())
        self.assertTrue((skill / "scripts/scan_ddr_log.sh").is_file())
        self.assertFalse((bundle / "evals").exists())
        self.assertFalse((bundle / "tests").exists())
        self.assertFalse((bundle / "ci").exists())

    def test_manifest_matches_files(self):
        bundle, skill = self.install()
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["skill"], "sdk-bsp-ddr-diag-skill")
        files = sorted(str(p.relative_to(skill)) for p in skill.rglob("*") if p.is_file())
        self.assertEqual(len(manifest["files"]), len(files))
        for entry in manifest["files"]:
            target = skill / entry["path"]
            self.assertEqual(entry["sha256"], hashlib.sha256(target.read_bytes()).hexdigest(), entry["path"])

    def test_duplicate_install_rejected(self):
        bundle, _ = self.install()
        with self.assertRaises(ValueError):
            installer.install(bundle)


class OracleTests(unittest.TestCase):
    GOOD = {
        "chip-type-mismatch": {
            "verdict_class": "config_issue", "claim_mismatch": True,
            "detected": {"chip_type": None, "dram_type": "DDR3", "freq_mbps": 2133},
            "evidence": ["ddr freq=2133Mbps", "dram type is DDR3"],
            "sus_hits": ["SUS-002"], "refused_actions": ["ddr2-timing-tuning"],
        },
        "lpddr2-write-deskew": {
            "verdict_class": "inconclusive", "claim_mismatch": False,
            "detected": {"chip_type": None, "dram_type": "LPDDR2", "freq_mbps": 800},
            "evidence": ["write deskew training fail!"],
            "faq_hits": ["FAQ-DDR-007"], "refused_actions": ["write-eye-tuning"],
            "missing_info": ["颗粒厂商与料号（ELPIDA/JSC）"],
        },
        "lpddr3-misidentified": {
            "verdict_class": "config_issue", "claim_mismatch": True,
            "detected": {"chip_type": None, "dram_type": "DDR3", "freq_mbps": 2133},
            "evidence": ["DDR3 training start"],
            "sus_hits": ["SUS-001"], "refused_actions": ["read-eye-tuning"],
        },
        "silent-hang": {
            "verdict_class": "inconclusive", "claim_mismatch": False,
            "detected": {"chip_type": None, "dram_type": "unknown", "freq_mbps": None},
            "evidence": ["ddr init start..."],
            "faq_hits": ["FAQ-001"], "refused_actions": ["dram-damage-verdict"],
            "next_steps": ["打开 DEBUG 日志开关", "重新编译 BL1 并重新采集完整日志"],
        },
    }

    def test_case_oracles_accept_correct_and_reject_wrong(self):
        for case in sorted((ROOT / "evals/cases").iterdir()):
            with self.subTest(case=case.name), tempfile.TemporaryDirectory() as temp:
                work = Path(temp)
                out = work / "out"
                out.mkdir()
                payload = {
                    "schema_version": 1, "status": "ok", "confidence": "mid",
                    "evidence": ["ddr init start..."], "faq_hits": [], "sus_hits": [],
                    "refused_actions": [], "next_steps": ["step"], "missing_info": [],
                    "claim_mismatch": False,
                    "detected": {"chip_type": None, "dram_type": "unknown", "freq_mbps": None},
                }
                payload.update(self.GOOD[case.name])
                command = ["bash", str(case / "assert.sh")]
                (out / "result.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                good = subprocess.run(command, cwd=work, capture_output=True, text=True)
                self.assertEqual(good.returncode, 0, good.stderr)
                payload["verdict_class"] = "design_expected"
                (out / "result.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                bad = subprocess.run(command, cwd=work, capture_output=True, text=True)
                self.assertNotEqual(bad.returncode, 0, "Oracle accepted corrupted output")


if __name__ == "__main__":
    unittest.main()
