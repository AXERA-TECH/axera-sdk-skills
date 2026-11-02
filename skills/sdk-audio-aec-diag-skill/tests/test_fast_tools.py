import array
import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install
from measure_segments import measure
from render_report import render
import test_report


class FastToolsTests(unittest.TestCase):
    def test_segments_use_exact_samples_including_partial_frames(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            samples = [0] * 160 + [1000, -2000, 32767, -32768] + [0] * 160
            raw = array.array("h", samples)
            if sys.byteorder != "little":
                raw.byteswap()
            (base / "mic.pcm").write_bytes(raw.tobytes())
            request = {"schema_version": 1, "audio": {"mic": {
                "path": "mic.pcm", "format": "s16le", "sample_rate": 16000}}}
            result = measure(request, base, [(0, 160), (159, 163), (160, 164)])
            silent, partial, clipped = result["audio"]["mic"]["segments"]
            self.assertIsNone(silent["rms_dbfs"])
            self.assertEqual(silent["zero_fraction"], 1)
            expected_power = (1000**2 + 2000**2 + 32767**2) / 4
            self.assertEqual(partial["power"], expected_power)
            self.assertAlmostEqual(partial["rms_dbfs"], 10 * math.log10(expected_power / 32768**2))
            self.assertEqual(partial["end_sample"], 163)
            self.assertEqual(partial["source"], "mic.pcm#samples=159:163")
            self.assertEqual(partial["role"], "mic")
            self.assertEqual(clipped["rail_fraction"], .5)
            for ranges in ([(0, 999)], [(3, 3)], [(-1, 4)], [(True, 5)], [(0.1, 4)]):
                with self.assertRaises(ValueError):
                    measure(request, base, ranges)
            # Each role is validated, not truncated to a common length.
            (base / "short.pcm").write_bytes(b"\0\0")
            request["audio"]["ref"] = dict(request["audio"]["mic"], path="short.pcm")
            with self.assertRaisesRegex(ValueError, "exceeds ref"):
                measure(request, base, [(0, 160)])

    def report_fixture(self):
        fixture = test_report.ReportTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_render_preserves_all_diagnostic_content_and_does_not_mutate(self):
        data = self.report_fixture().report
        data["evidence"] = [{"source": "capture.txt:3", "observation": "观测|内容\n第二行",
                             "confidence": "unknown"}]
        data["additional_notes"] = {"unresolved": "仍需区分两种解释"}
        original = copy.deepcopy(data)
        markdown = render(data)

        def check(value):
            if isinstance(value, str):
                self.assertIn(value, markdown)
            elif isinstance(value, dict):
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        check(data)
        self.assertEqual(data, original)

    def test_installed_renderer_validates_before_write_and_never_overwrites(self):
        fixture = self.report_fixture()
        base, data = fixture.base, fixture.report
        skill = install.install(base / "bundle")
        out = base / "out"
        out.mkdir()
        source = json.dumps(data)
        (out / "diagnosis.json").write_text(source)
        (out / "measurements.json").write_text('{"status":"needs_evidence"}')
        (out / "measurements.md").write_text("No acoustic acceptance performed")
        command = [sys.executable, str(skill / "scripts/render_report.py"), "--out", str(out)]
        run = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((out / "diagnosis.json").read_text(), source)
        markdown = (out / "diagnosis.md").read_bytes()
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
        self.assertEqual((out / "diagnosis.md").read_bytes(), markdown)
        (out / "diagnosis.md").unlink()
        data["status"] = "resolved"
        (out / "diagnosis.json").write_text(json.dumps(data))
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
        self.assertFalse((out / "diagnosis.md").exists())

    def test_installed_segments_cli_records_exact_evidence_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            skill = install.install(base / "bundle")
            (base / "mic.pcm").write_bytes(b"\0\0" * 161)
            (base / "request.json").write_text(json.dumps({"schema_version": 1, "audio": {
                "mic": {"path": "mic.pcm", "format": "s16le", "sample_rate": 16000}}}))
            command = [sys.executable, str(skill / "scripts/measure_segments.py"),
                       "--input", str(base / "request.json"), "--range", "1:161",
                       "--out", str(base / "segments.json")]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result, json.loads((base / "segments.json").read_text()))
            self.assertEqual(result["audio"]["mic"]["segments"][0]["samples"], 160)
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
