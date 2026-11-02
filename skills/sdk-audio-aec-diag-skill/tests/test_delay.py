import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze
import install


class DelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.rate = 8000
        self.ref = np.random.default_rng(42).integers(-5000, 5001, self.rate * 6)

    def pcm(self, name, signal):
        (self.base / name).write_bytes(np.asarray(signal, dtype="<i2").tobytes())
        return {"path": name, "format": "s16le", "sample_rate": self.rate}

    def request(self, lag=100, ref=None, mic=None):
        ref = self.ref if ref is None else ref
        if mic is None:
            mic = np.zeros(len(ref))
            if lag >= 0:
                mic[lag:] = ref[:len(ref) - lag]
            else:
                mic[:lag] = ref[-lag:]
        return {"schema_version": 1, "scenario": "far_only",
                "audio": {"mic": self.pcm("mic.pcm", mic), "ref": self.pcm("ref.pcm", ref)},
                "delay": {"enabled": True, "same_run": True, "shared_timebase": True,
                          "capture_stage": "before_compensation", "max_lag_ms": 100}}

    def run_request(self, req):
        result = analyze.analyze(req, self.base)
        json.dumps(result, allow_nan=False)
        return result

    def parameter(self, req, current=100):
        req["delay"]["parameter"] = {"name": "synthetic_total_ref_delay", "value_ms": current,
            "source": "synthetic config readback", "semantics": "total_ref_delay",
            "semantics_source": "synthetic test: parameter delays reference by its value", "tolerance_ms": 2}

    def test_positive_lag_and_negative_polarity_with_noise(self):
        req = self.request()
        noise = np.random.default_rng(3).normal(0, 100, len(self.ref))
        mic = -np.r_[np.zeros(100), self.ref[:-100]] * .5 + noise + 300
        req["audio"]["mic"] = self.pcm("mic.pcm", mic)
        result = self.run_request(req)["delay"]
        self.assertEqual(result["status"], "estimated")
        self.assertEqual(result["lag_samples"], 100)
        self.assertEqual(result["lag_ms"], 12.5)
        self.assertTrue(all(w["signed_correlation"] < -.9 for w in result["windows"]))

    def test_negative_and_zero_lag(self):
        for lag in (-200, 0):
            result = self.run_request(self.request(lag))["delay"]
            self.assertEqual(result["status"], "estimated")
            self.assertEqual(result["lag_samples"], lag)

    def test_parameter_too_large_before_compensation(self):
        req = self.request()
        self.parameter(req)
        result = self.run_request(req)
        comp = result["delay"]["parameter_comparison"]
        self.assertEqual(comp["status"], "configured_too_large_candidate")
        self.assertEqual(comp["excess_ms"], 87.5)
        self.assertIn("DELAY_PARAMETER_TOO_LARGE_CANDIDATE", {f["code"] for f in result["findings"]})
        self.assertEqual(result["verification"], "not_run")

    def test_overcompensation_after_delay_and_small_parameter(self):
        req = self.request(-700)
        req["delay"]["capture_stage"] = "after_compensation"
        self.parameter(req)
        comp = self.run_request(req)["delay"]["parameter_comparison"]
        self.assertEqual(comp["status"], "configured_too_large_candidate")
        self.assertEqual(comp["measured_target_ms"], 12.5)
        req = self.request(100)
        self.parameter(req, 0)
        self.assertEqual(self.run_request(req)["delay"]["parameter_comparison"]["status"], "configured_too_small_candidate")

    def test_unknown_mapping_and_special_values_not_compared(self):
        for change in ({"semantics": "buffer_component"}, {"semantics_source": "unknown"}, {"value_ms": -1}):
            req = self.request()
            self.parameter(req)
            req["delay"]["parameter"].update(change)
            self.assertEqual(self.run_request(req)["delay"]["parameter_comparison"]["status"], "not_comparable")
        req = self.request()
        self.parameter(req)
        req["delay"]["capture_stage"] = "unknown"
        self.assertEqual(self.run_request(req)["delay"]["parameter_comparison"]["status"], "not_comparable")

    def test_unknown_timebase_or_scenario_is_provisional(self):
        for field in ("same_run", "shared_timebase", "scenario"):
            req = self.request()
            self.parameter(req)
            if field == "scenario":
                req["scenario"] = "unknown"
            else:
                req["delay"].pop(field)
            result = self.run_request(req)["delay"]
            self.assertEqual(result["status"], "provisional")
            self.assertIsNone(result["lag_ms"])
            self.assertEqual(result["file_relative_median_ms"], 12.5)
            self.assertEqual(result["parameter_comparison"]["status"], "not_comparable")

    def test_silence_and_periodic_signal_rejected(self):
        for signal in (np.zeros(len(self.ref)), 4000 * np.sin(2 * np.pi * 400 * np.arange(len(self.ref)) / self.rate)):
            result = self.run_request(self.request(ref=signal))["delay"]
            self.assertEqual(result["status"], "inconclusive")
            self.assertIsNone(result["lag_ms"])
            self.assertTrue(all(not w["accepted"] for w in result["windows"]))

    def test_unrelated_signals_rejected(self):
        mic = np.random.default_rng(7).integers(-5000, 5001, len(self.ref))
        result = self.run_request(self.request(mic=mic))["delay"]
        self.assertEqual(result["status"], "inconclusive")

    def test_clipped_capture_rejected(self):
        result = self.run_request(self.request(ref=np.where(self.ref > 0, 32767, -32768)))["delay"]
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(result["windows"][0]["reason"], "digital_full_scale")

    def test_boundary_and_changing_lag_not_reported_stable(self):
        self.assertEqual(self.run_request(self.request(800))["delay"]["status"], "inconclusive")
        mic = self.ref.copy()
        split = len(mic) // 2
        mic[split:] = self.ref[split - 200:-200]
        result = self.run_request(self.request(mic=mic))["delay"]
        self.assertIn(result["status"], ("unstable", "inconclusive"))
        self.assertIsNone(result["lag_ms"])

    def test_mismatch_short_and_double_talk_rejected(self):
        req = self.request()
        req["audio"]["ref"]["sample_rate"] = 16000
        self.assertEqual(self.run_request(req)["delay"]["status"], "unavailable")
        req = self.request(ref=self.ref[:8000])
        self.assertEqual(self.run_request(req)["delay"]["status"], "unavailable")
        req = self.request()
        req["scenario"] = "double_talk"
        self.assertEqual(self.run_request(req)["delay"]["status"], "unavailable")

    def test_missing_numpy_is_explicit_and_base_analysis_survives(self):
        req = self.request()
        with patch.dict(sys.modules, {"numpy": None}):
            result = self.run_request(req)
        self.assertEqual(result["delay"]["status"], "unavailable")
        self.assertIn("NumPy", result["delay"]["reason"])
        self.assertIn("mic", result["audio"])

    def test_bad_delay_metadata(self):
        for options in ([], {"enabled": "true"}, {"max_lag_ms": 0}, {"window_ms": 10000},
                        {"parameter": {"value_ms": float("nan")}}, {"capture_stage": "guess"}):
            with self.assertRaises(ValueError):
                analyze.analyze({"schema_version": 1, "delay": options}, self.base)

    def test_installed_cli_computes_delay(self):
        req = self.request()
        self.parameter(req)
        request = self.base / "request.json"
        request.write_text(json.dumps(req))
        runtime = install.install(self.base / "bundle")
        out = self.base / "out"
        run = subprocess.run([sys.executable, str(runtime / "scripts/analyze.py"), "--input", str(request), "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads((out / "measurements.json").read_text())
        self.assertEqual(result["delay"]["lag_ms"], 12.5)
        self.assertEqual(result["delay"]["parameter_comparison"]["status"], "configured_too_large_candidate")
        self.assertIn("configured_too_large_candidate", (out / "measurements.md").read_text())


if __name__ == "__main__":
    unittest.main()
