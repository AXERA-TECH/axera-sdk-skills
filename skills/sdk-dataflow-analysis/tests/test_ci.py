"""Exercise independent assertions against valid and invalid diagnostic outputs."""

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class AssertionTests(unittest.TestCase):
    def baseline(self, case):
        oracle = yaml.safe_load((case / "answer/oracle.yaml").read_text())
        status = "incomplete" if case.name == "AXDF-009" else "normal" if case.name in {"AXDF-006", "AXDF-007"} else "failure"
        return {
            "status": status,
            "root_cause": oracle["root_cause"],
            "confidence": oracle["expected_confidence"],
            "evidence": [{"source": source, "quote": "\n".join(signatures)}
                         for source, signatures in oracle["evidence_signatures"].items()],
            "missing_information": ["serial.log", "syslog.log", "logctl.proc", "vin.proc", "venc.proc", "link.proc", "ivps_sched"] if status == "incomplete" else [],
        }

    def run_assertion(self, case, data, report=None):
        # Synthetic oracle-derived answers test the assertion code, not model quality.
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / "result.json").write_text(json.dumps(data, ensure_ascii=False))
            (work / "result.md").write_text(report if report is not None else data["root_cause"] + "\n" + json.dumps(data, ensure_ascii=False))
            return subprocess.run(["bash", str(case / "assert.sh")], cwd=work, capture_output=True, text=True)

    def test_frame_enlarge_evidence_accepts_serial_fps(self):
        case = ROOT / "evals/AXDF-007"
        row = next(line for line in (case / "input/serial.log").read_text().splitlines()
                   if "VENC: [0] fps 60." in line)
        good = self.baseline(case)
        good["evidence"] = [
            {"source": "input/serial.log", "quote": row},
            {"source": "input/ivps.proc", "quote": "RATIO  0  30.0 : 30.0"},
        ]
        result = self.run_assertion(case, good)
        self.assertEqual(result.returncode, 0, result.stderr)
        good["evidence"][0]["quote"] = row.replace("fps 60.", "fps 30.")
        self.assertNotEqual(self.run_assertion(case, good).returncode, 0)

    def test_ldc_evidence_accepts_native_proc_table(self):
        case = ROOT / "evals/AXDF-006"
        row = next(line for line in (case / "input/ivps.proc").read_text().splitlines()
                   if "0     -1    0     LDC" in line)
        good = self.baseline(case)
        good["evidence"] = [
            {"source": "input/ivps.proc", "quote": row},
            {"source": "input/venc.proc", "quote": "VENC CHN STATUS"},
        ]
        result = self.run_assertion(case, good)
        self.assertEqual(result.returncode, 0, result.stderr)
        good["evidence"][0]["quote"] = row.replace("LDC", "NONE")
        self.assertNotEqual(self.run_assertion(case, good).returncode, 0)

    def test_incomplete_gate_accepts_both_markers_and_requires_recapture(self):
        case = ROOT / "evals/AXDF-009"
        for marker in ("INCONCLUSIVE", "INCOMPLETE"):
            good = self.baseline(case)
            # The gate marker belongs in the report; JSON root_cause may use plain language.
            good["root_cause"] = good["root_cause"].replace("INCONCLUSIVE", "")
            report = marker + "\n" + good["root_cause"] + "\n" + json.dumps(good, ensure_ascii=False)
            result = self.run_assertion(case, good, report)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotEqual(self.run_assertion(case, good, report.replace(marker, "")).returncode, 0)
            wrong = copy.deepcopy(good)
            wrong["missing_information"].remove("serial.log")
            self.assertNotEqual(self.run_assertion(case, wrong, report).returncode, 0)

    def test_each_assertion_accepts_reference_and_rejects_bad_outputs(self):
        for case in sorted((ROOT / "evals").glob("AXDF-*")):
            with self.subTest(case=case.name):
                good = self.baseline(case)
                result = self.run_assertion(case, good)
                self.assertEqual(result.returncode, 0, result.stderr)
                wrong = copy.deepcopy(good)
                wrong["status"] = "normal" if good["status"] != "normal" else "failure"
                self.assertNotEqual(self.run_assertion(case, wrong).returncode, 0)
                wrong = copy.deepcopy(good)
                wrong["root_cause"] = "无法判断，请检查配置。"
                self.assertNotEqual(self.run_assertion(case, wrong).returncode, 0)
                wrong = copy.deepcopy(good)
                if good["status"] == "incomplete":
                    wrong["confidence"] = "high"
                else:
                    wrong["evidence"] = []
                self.assertNotEqual(self.run_assertion(case, wrong).returncode, 0)


if __name__ == "__main__":
    unittest.main()
