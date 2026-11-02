import copy
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load("installer", "scripts/install.py")
oracle = load("oracle", "evals/assert_result.py")
CASES = json.loads((ROOT / "evals/evals.json").read_text())["evals"]


def input_text(case):
    return "\n".join([case["prompt"]] + [(ROOT / "evals" / path).read_text() for path in case["files"]])


def recommendation(target, operation, reason="Inspect or validate against captured evidence."):
    return {"target": target, "operation": operation, "reason": reason}


def results():
    samples = {}
    for case in CASES:
        samples[case["id"]] = {
            "schema_version": 1, "phase": "In-Handover", "confidence": "supported",
            "diagnosis": "Diagnostic conclusion.", "analysis": "Evidence, causal chain and next action.",
            "evidence": [line for line in input_text(case).splitlines() if line.strip()],
            "recommendations": [], "rejected_actions": [], "limitations": "Implementation or trace still requires validation.",
        }
    samples[1].update(phase="Pre-Handover",
                      i2c_plan={"rtos_channels": [1], "linux_channels": [0], "claim_bitmap": 2,
                                "dummy_status_bits": 8, "preserve_arbitration": True},
                      recommendations=[recommendation("rtos_i2c_claim_mask", "configure"), recommendation("AX_DUMMY_SW6_ADDR", "validate")],
                      rejected_actions=["bypass_i2c_arbitration"])
    return samples


class InstallTests(unittest.TestCase):
    def test_runtime_references_and_hashes_without_eval_answers(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "bundle"
            installed = installer.install(bundle)
            self.assertEqual(installed.name, "sdk-bsp-fast-boot-skill")
            actual = {str(p.relative_to(installed)) for p in installed.rglob("*") if p.is_file()}
            expected = {"SKILL.md", "agents/openai.yaml"} | {str(p.relative_to(ROOT)) for p in (ROOT / "references").rglob("*") if p.is_file()}
            self.assertEqual(actual, expected)
            self.assertEqual(len(actual), 6)
            self.assertFalse(any(p.is_symlink() for p in bundle.rglob("*")))
            manifest = json.loads((bundle / "manifest.json").read_text())
            self.assertEqual(manifest["skill"], "sdk-bsp-fast-boot-skill")
            self.assertEqual({e["path"] for e in manifest["files"]}, expected)
            for entry in manifest["files"]:
                self.assertEqual(entry["sha256"], hashlib.sha256((installed / entry["path"]).read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                installer.install(bundle)

    def test_missing_reference_and_nested_symlink_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "SKILL.md").write_text("skill")
            (root / "agents").mkdir()
            (root / "agents/openai.yaml").write_text("interface: {}")
            old_root = installer.ROOT
            try:
                installer.ROOT = root
                with self.assertRaises(ValueError):
                    installer.install(root / "bundle")
                self.assertFalse((root / "bundle").exists())
                (root / "references").mkdir()
                (root / "references/outside.md").symlink_to(ROOT / "SKILL.md")
                with self.assertRaises(ValueError):
                    installer.install(root / "bundle")
                self.assertFalse((root / "bundle").exists())
            finally:
                installer.ROOT = old_root


class EvalTests(unittest.TestCase):

    def test_accept_good_and_reject_wrong_diagnosis_decisions(self):
        samples = results()
        broken = copy.deepcopy(samples)
        broken[1]["i2c_plan"]["dummy_status_bits"] = 2
        for case in CASES:
            cid = case["id"]
            with self.subTest(case=cid):
                oracle.validate(cid, samples[cid], input_text(case))
                with self.assertRaises(AssertionError):
                    oracle.validate(cid, broken[cid], input_text(case))

    def test_fabricated_evidence_and_unsafe_alternatives_are_rejected(self):
        for case in CASES:
            sample = results()[case["id"]]
            with self.subTest(case=case["id"]):
                sample["evidence"].append("Fabricated: release completed and board was tested.")
                with self.assertRaises(AssertionError):
                    oracle.validate(case["id"], sample, input_text(case))
                sample = results()[case["id"]]
                sample["rejected_actions"] = []
                with self.assertRaises(AssertionError):
                    oracle.validate(case["id"], sample, input_text(case))

    def test_assertions_run_without_sibling_evaluator(self):
        samples = results()
        with tempfile.TemporaryDirectory() as temp:
            for case in CASES:
                with self.subTest(case=case["id"]):
                    source = ROOT / "evals/cases" / case["name"]
                    workspace = Path(temp) / case["name"]
                    shutil.copytree(source / "fixtures", workspace)
                    shutil.copy2(source / "assert.sh", workspace / "assert.sh")
                    (workspace / "out").mkdir()
                    output = workspace / "out/result.json"
                    output.write_text(json.dumps(samples[case["id"]]))
                    result = subprocess.run(["bash", "assert.sh"], cwd=workspace, text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output.write_text('{}')
                    result = subprocess.run(["bash", "assert.sh"], cwd=workspace, text=True, capture_output=True)
                    self.assertNotEqual(result.returncode, 0)

    def test_path_traversal_in_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / "request.json").write_text(json.dumps({"task": "offline", "attachments": ["../outside.log"]}))
            import os
            cwd = Path.cwd()
            try:
                os.chdir(workspace)
                with self.assertRaises(AssertionError):
                    oracle.load_input()
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
