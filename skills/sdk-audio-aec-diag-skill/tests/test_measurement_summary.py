"""Ensure compact rendering retains exact metrics and diagnostic limitations."""
import array
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze


class MeasurementSummaryTests(unittest.TestCase):
    def test_exact_audio_overview_without_expanding_frame_arrays(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = array.array("h", [0, 32767, -32768, 1200] * 8000)
            if sys.byteorder != "little":
                samples.byteswap()
            (root / "mic.pcm").write_bytes(samples.tobytes())
            result = analyze.analyze({"schema_version": 1, "audio": {
                "mic": {"path": "mic.pcm", "format": "s16le", "sample_rate": 16000}}}, root)
            before = copy.deepcopy(result)
            rendered = analyze.render(result)
            line = next(line for line in rendered.splitlines() if line.startswith("- mic: "))
            overview = json.loads(line[len("- mic: "):])
            expected = {key: value for key, value in result["audio"]["mic"].items()
                        if key not in {"frames", "sha256"}}
            self.assertEqual(overview, expected)
            self.assertNotIn('"start_sample":', rendered)
            self.assertEqual(result, before)
            self.assertGreater(len(result["audio"]["mic"]["frames"]), 100)

    def test_silence_errors_and_rejected_delay_windows_remain_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "silent.pcm").write_bytes(bytes(320))
            result = analyze.analyze({"schema_version": 1, "audio": {
                "ref": {"path": "silent.pcm", "format": "s16le", "sample_rate": 16000},
                "mic": {"path": "missing.pcm", "format": "s16le", "sample_rate": 16000}}}, root)
            # Rendering must retain rejected windows even when there is no usable estimate.
            window = {"time_seconds": 0.5, "accepted": False, "reason": "reference_silent_or_low_energy"}
            result["delay"] = {"status": "inconclusive", "windows": [window],
                               "reason": "No accepted windows"}
            rendered = analyze.render(result)
            line = next(line for line in rendered.splitlines() if line.startswith("- ref: "))
            overview = json.loads(line[len("- ref: "):])
            self.assertIsNone(overview["rms_dbfs"])
            self.assertIsNone(overview["peak_dbfs"])
            self.assertEqual(overview["zero_fraction"], 1)
            self.assertIn("missing.pcm", rendered)
            self.assertIn(json.dumps(window), rendered)
            for item in result["missing_evidence"]:
                self.assertIn(item, rendered)


if __name__ == "__main__":
    unittest.main()
