"""Exercise the harness boundary: one copied assertion, no repository siblings."""
import hashlib
import json
import os
import shutil
import subprocess
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "evals/cases/axaudioaec-001"


class AssertionBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.work = self.base / "work"
        shutil.copytree(CASE / "fixtures", self.work)
        self.script = self.base / "assert.sh"
        shutil.copyfile(CASE / "assert.sh", self.script)
        self.out = self.work / "out"
        self.out.mkdir()
        # Synthetic verifier fixture, not a model evaluation or acoustic acceptance.
        self.diagnosis = {
            "schema_version": 1, "status": "pending_verification",
            "classification": "configuration", "summary": "AEC 未启用，待修正与复测",
            "evidence": [{"source": name, "observation": "VQE 开启但 AEC DISABLE"}
                         for name in ("proc.txt", "application.log")],
            "hypotheses": ["AEC 配置未启用"], "missing_evidence": ["修正后录音与读回"],
            "resolution_evidence": [],
            "actions": [{"change": "禁用设备后按该版本要求启用 AEC 并读回",
                         "reason": "AEC 关闭", "rollback": "恢复旧配置",
                         "expected": "读回显示开启", "falsifier": "读回仍关闭"}],
            "regression": [{"scenario": s, "status": "not_run", "criterion": "客户认可基线",
                            "evidence": "未执行板端复测"}
                           for s in ("far_only", "near_only", "double_talk", "silence", "trigger")]}
        measurements = {"status": "measured", "verification": "not_run", "input_errors": [],
                        "energy_reduction_proxy_db": None, "findings": [{"code": "AEC_DISABLED"}],
                        "proc_tables": [{"section": s} for s in (
                            "AI DEV ATTR", "AI DEV AEC ATTR", "AI DEV DUMP AND BYPASS", "AO DEV STATUS")],
                        "audio": {}}
        for role, point in (("mic", "vqeIn"), ("ref", "vqeRef"), ("output", "vqeOut")):
            raw = (self.work / f"AiCard0_Dev0_{point}.pcm").read_bytes()
            measurements["audio"][role] = {"sha256": hashlib.sha256(raw).hexdigest(),
                                           "samples": len(raw) // 2, "sample_rate": 16000}
        (self.out / "measurements.json").write_text(json.dumps(measurements))
        for name in ("diagnosis.md", "measurements.md"):
            (self.out / name).write_text("Synthetic verifier fixture. " * 10)

    def run_assertion(self):
        (self.out / "diagnosis.json").write_text(json.dumps(self.diagnosis))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env.pop("PYTHONPATH", None)
        return subprocess.run(["bash", str(self.script)], cwd=self.work,
                              env=env, capture_output=True, text=True)

    def test_copied_assertion_passes_without_repository_siblings(self):
        result = self.run_assertion()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: axaudioaec-001", result.stdout)
        self.assertIn("PASS: report structure", result.stdout)

    def test_clipping_case_requires_only_fault_round_and_preserves_measurement_gate(self):
        case = ROOT / "evals/cases/axaudioaec-004"
        self.work = self.base / "clipping"
        shutil.copytree(case / "fixtures", self.work)
        self.assertFalse(any(p.is_dir() for p in self.work.iterdir()))
        shutil.copyfile(case / "assert.sh", self.script)
        self.out = self.work / "out"
        self.out.mkdir()
        measurements = json.loads((self.base / "work/out/measurements.json").read_text())
        measurements["findings"] = [{"code": "FULL_SCALE_MIC"}]
        for role, point in (("mic", "vqeIn"), ("ref", "vqeRef"), ("output", "vqeOut")):
            raw = (self.work / f"AiCard0_Dev0_{point}.pcm").read_bytes()
            samples = [value for (value,) in struct.iter_unpack("<h", raw)]
            measurements["audio"][role] = {
                "sha256": hashlib.sha256(raw).hexdigest(), "samples": len(samples),
                "sample_rate": 16000,
                "rail_fraction": sum(x in (-32768, 32767) for x in samples) / len(samples)}
        self.diagnosis.update({
            "classification": "signal_path", "summary": "MIC 有满幅削顶特征，具体失真级待验证",
            "evidence": [
                {"source": "capture.txt", "observation": "目标播放档位下远端单讲"},
                {"source": "AiCard0_Dev0_vqeIn.pcm", "observation": "MIC 满幅样本比例约 1.374%"},
                {"source": "AiCard0_Dev0_vqeRef.pcm", "observation": "REF 未见满幅端点"}],
            "hypotheses": ["MIC 输入分支过载，具体增益级待查"],
            "missing_evidence": ["相邻模拟前级测点与 ALC 状态"],
            "actions": [{"change": "保持目标播放档位，单项降低 MIC 增益并补采",
                         "reason": "MIC 削顶", "rollback": "恢复旧增益",
                         "expected": "满幅比例下降", "falsifier": "满幅比例未下降"}]})
        for item in self.diagnosis["regression"]:
            item["criterion"] = "目标播放响度、弱近端拾音和回声满足客户要求"
        for name in ("diagnosis.md", "measurements.md"):
            (self.out / name).write_text("Verifier fixture, no hardware acceptance. " * 10)
        path = self.out / "measurements.json"
        path.write_text(json.dumps(measurements))
        result = self.run_assertion()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: axaudioaec-004", result.stdout)
        self.assertIn("PASS: report structure", result.stdout)
        measurements["audio"]["mic"]["rail_fraction"] = 0
        path.write_text(json.dumps(measurements))
        result = self.run_assertion()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AssertionError", result.stderr)

    def test_copied_assertion_preserves_case_and_report_gates(self):
        self.diagnosis["classification"] = "inconclusive"
        result = self.run_assertion()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AssertionError", result.stderr)
        self.diagnosis["classification"] = "configuration"
        # The case oracle accepts a list; the full validator requires strings.
        self.diagnosis["hypotheses"] = [123]
        result = self.run_assertion()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hypotheses must be nonempty text", result.stderr)


if __name__ == "__main__":
    unittest.main()
