"""Verify case 003's independent inputs and the copied harness assertion."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze

CASE = ROOT / "evals/cases/axaudioaec-003"


class TimingCaseTests(unittest.TestCase):
    def request(self):
        return {
            "schema_version": 1, "scenario": "far_only",
            "text_evidence": ["proc.txt", "capture.txt", "config.txt", "application.log"],
            "audio": {role: {"path": f"AiCard0_Dev0_{point}.pcm", "format": "s16le",
                             "sample_rate": 16000, "channels": 1}
                      for role, point in (("mic", "vqeIn"), ("ref", "vqeRef"), ("output", "vqeOut"))},
            "delay": {"enabled": True, "same_run": True, "shared_timebase": True,
                      "capture_stage": "unknown", "parameter": {
                          "name": "ref_delay_ms", "value_ms": 20, "source": "application.log:3"}}}


    def test_stable_two_ms_vs_twenty_ms_configuration(self):
        measured = analyze.analyze(self.request(), CASE / "fixtures")
        self.assertFalse(measured["input_errors"])
        delay = measured["delay"]
        self.assertEqual(delay["status"], "estimated")
        self.assertEqual(delay["lag_samples"], 32)
        self.assertEqual(delay["lag_ms"], 2)
        self.assertGreaterEqual(sum(w["accepted"] for w in delay["windows"]), 3)
        self.assertEqual(delay["parameter_comparison"]["status"], "not_comparable")
        self.assertEqual(delay["capture_stage"], "unknown")
        self.assertNotIn("DELAY_PARAMETER_TOO_LARGE_CANDIDATE",
                         {item["code"] for item in measured["findings"]})

    def test_copied_assertion_passes_single_round_and_rejects_wrong_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            work = base / "work"
            shutil.copytree(CASE / "fixtures", work)
            assertion = base / "assert.sh"
            shutil.copyfile(CASE / "assert.sh", assertion)
            (work / "request.json").write_text(json.dumps(self.request()))
            result = subprocess.run([sys.executable, str(ROOT / "scripts/analyze.py"),
                                     "--input", str(work / "request.json"), "--out", str(work / "out")],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            diagnosis = {
                "schema_version": 1, "status": "pending_verification", "classification": "timing",
                "summary": "MIC 稳定晚于 REF 2 ms，应用 ref_delay_ms=20，参数映射及因果关系待确认",
                "evidence": [
                    {"source": "proc.txt:5", "observation": "AEC 已开启"},
                    {"source": "capture.txt:5", "observation": "同轮三路共同时基，未分别裁剪"},
                    {"source": "config.txt:11", "observation": "ref_delay_ms=20，未提供参数定义"},
                    {"source": "application.log:3", "observation": "ref_delay_ms 读回 20 ms"},
                    {"source": "out/measurements.json#delay", "observation": "时差稳定 2 ms，尚不能直接映射到配置"}],
                "hypotheses": ["延迟不匹配影响回声消除，其他因素尚待排查"],
                "actions": [{"change": "确认应用参考延迟定义和采集点补偿位置后，设计单变量对照并读回",
                             "reason": "参数映射待确认", "rollback": "恢复 20 ms",
                             "expected": "回声下降", "falsifier": "回声未改善"}],
                "missing_evidence": ["参数语义和采集位置说明，调整后配置读回及同条件三路录音"],
                "regression": [{"scenario": scenario, "status": "not_run",
                                "criterion": "回声和近端保真符合客户要求", "evidence": "尚未板端复测"}
                               for scenario in ("far_only", "near_only", "double_talk", "silence", "trigger")],
                "resolution_evidence": []}
            (work / "out/diagnosis.json").write_text(json.dumps(diagnosis, ensure_ascii=False))
            result = subprocess.run([sys.executable, str(ROOT / "scripts/render_report.py"),
                                     "--out", str(work / "out")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(["bash", str(assertion)], cwd=work, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: axaudioaec-003", result.stdout)
            diagnosis_path = work / "out/diagnosis.json"
            original = diagnosis_path.read_text()
            diagnosis_path.write_text(original.replace("ref_delay_ms 读回 20 ms", "ref_delay_ms 读回 10 ms"))
            result = subprocess.run(["bash", str(assertion)], cwd=work, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Use the 20 readback", result.stderr)
            diagnosis_path.write_text(original)
            path = work / "out/measurements.json"
            measured = json.loads(path.read_text())
            measured["delay"]["parameter_comparison"]["status"] = "configured_too_large_candidate"
            path.write_text(json.dumps(measured))
            result = subprocess.run(["bash", str(assertion)], cwd=work, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Do not invent parameter semantics", result.stderr)


if __name__ == "__main__":
    unittest.main()
