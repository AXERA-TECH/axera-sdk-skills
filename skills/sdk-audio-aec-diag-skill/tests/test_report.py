import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import install
from validate_report import validate


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.report = {
            "schema_version": 1, "status": "needs_evidence", "classification": "inconclusive",
            "summary": "Reference identity is not established", "evidence": [],
            "hypotheses": ["Missing reference or a capture mismatch"],
            "actions": [{"change": "Capture synchronized reference", "reason": "Distinguish input faults",
                         "rollback": "Read only", "expected": "Reference follows playback",
                         "falsifier": "Valid reference with unchanged echo"}],
            "missing_evidence": ["Provide a capture with stage and time origin"],
            "regression": [{"scenario": s, "criterion": "Agreed product baseline",
                            "status": "not_run", "evidence": "No device available"}
                           for s in ("far_only", "near_only", "double_talk", "silence", "trigger")],
            "resolution_evidence": []}

    def resolved(self):
        data = copy.deepcopy(self.report)
        (self.base / "verification.txt").write_text("Synthetic verifier fixture; not a real board acceptance")
        data.update(status="resolved", classification="configuration", missing_evidence=[],
                    evidence=[{"source": "request.json#/config", "observation": "Mode changed and read back"}],
                    resolution_evidence=["verification.txt"])
        for item in data["regression"]:
            item.update(status="pass", evidence="verification.txt#" + item["scenario"])
        return data

    def test_incomplete_and_evidence_backed_structure(self):
        validate(self.report, self.base)
        validate(self.resolved(), self.base)

    def test_unverified_resolution_and_unrun_trigger_rejected(self):
        data = copy.deepcopy(self.report)
        data["status"] = "resolved"
        with self.assertRaises(ValueError):
            validate(data, self.base)
        data = self.resolved()
        data["regression"][-1].update(status="not_run", evidence="No restart test")
        with self.assertRaisesRegex(ValueError, "every listed"):
            validate(data, self.base)

    def test_failed_regression_and_suspected_sdk_not_resolved(self):
        for change in ("failure", "suspect", "gap"):
            data = self.resolved()
            if change == "failure":
                data["regression"][0]["status"] = "fail"
            elif change == "suspect":
                data["classification"] = "sdk_suspected"
            else:
                data["missing_evidence"] = ["Runtime mode still unknown"]
            with self.assertRaises(ValueError):
                validate(data, self.base)

    def test_missing_empty_escape_and_self_evidence_rejected(self):
        data = self.resolved()
        (self.base / "empty.txt").touch()
        (self.base / "diagnosis.json").write_text("{}")
        (self.base / "outside").symlink_to(Path(__file__).resolve())
        for name in ("absent.txt", "empty.txt", "../outside.txt", "outside", "diagnosis.json"):
            data["resolution_evidence"] = [name]
            with self.assertRaises(ValueError, msg=name):
                validate(data, self.base)

    def test_missing_fields_and_wrong_types(self):
        for field in self.report:
            data = copy.deepcopy(self.report)
            del data[field]
            with self.assertRaises(ValueError, msg=field):
                validate(data, self.base)
        for field, value in (("schema_version", True), ("actions", [None]), ("evidence", "text")):
            data = copy.deepcopy(self.report)
            data[field] = value
            with self.assertRaises(ValueError):
                validate(data, self.base)

    def test_installed_validator_cli_and_missing_output(self):
        target = install.install(self.base / "bundle")
        out = self.base / "out"
        out.mkdir()
        (out / "diagnosis.json").write_text(json.dumps(self.report))
        (out / "measurements.json").write_text('{"status":"needs_evidence"}')
        for name in ("diagnosis.md", "measurements.md"):
            (out / name).write_text("Synthetic report fixture")
        command = [sys.executable, str(target / "scripts/validate_report.py"), "--out", str(out)]
        passed = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        (out / "diagnosis.md").unlink()
        failed = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
