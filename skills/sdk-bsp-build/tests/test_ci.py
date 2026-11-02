import copy
import importlib.util
import json
import os
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


def command(module, targets, parallel=None):
    return {"cwd": oracle.SDK + "/" + module, "project": oracle.PROJECT,
            "targets": targets, "parallel": parallel}


def results():
    base = {"schema_version": 1, "sdk_root": oracle.SDK, "project": oracle.PROJECT,
            "workflow": "module", "status": "planned", "analysis": "执行前确认工程，实际构建后检查退出状态。",
            "prerequisites": ["project_confirmed_by_plist"]}
    samples = {i: copy.deepcopy(base) for i in range(1, 6)}
    samples[1].update(workflow="inspection", project=None, prerequisites=[],
                      commands=[dict(command("build", ["plist"]), project=None)])
    samples[2].update(workflow="full", commands=[command("build", ["clean", "all", "install", "axp"], 64)])
    samples[3]["commands"] = [command("boot/bl1", ["clean", "all", "install"], 64)]
    samples[4]["commands"] = [command("kernel/linux", ["clean", "all", "install"], 64)]
    samples[5].update(workflow="fast AXP", full_build_project=oracle.PROJECT,
                      prerequisites=["project_confirmed_by_plist", "full_build_succeeded_for_same_project"],
                      commands=[command("build/projects/" + oracle.PROJECT, ["clean", "all", "install", "axp"])])
    return samples


class HelperTests(unittest.TestCase):
    def run_helper(self, *args):
        return subprocess.run(["bash", str(ROOT / "scripts/find-latest-axp.sh"), *map(str, args)],
                              text=True, capture_output=True)

    def test_errors(self):
        self.assertEqual(self.run_helper().returncode, 2)
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.run_helper(Path(temp) / "missing").returncode, 1)
            self.assertEqual(self.run_helper(temp).returncode, 1)

    def test_mtime_nested_and_spaced_paths(self):
        with tempfile.TemporaryDirectory(prefix="bsp test ") as temp:
            root = Path(temp)
            old = root / "zzz-old.axp"
            newest = root / "nested space" / "aaa-current.axp"
            newest.parent.mkdir()
            old.write_bytes(b"old")
            newest.write_bytes(b"current")
            (root / "ignore.txt").write_bytes(b"not an axp")
            os.utime(old, (1000, 1000))
            os.utime(newest, (2000, 2000))
            result = self.run_helper(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.splitlines()
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[0].endswith(str(newest)))
            self.assertIn("7 bytes", lines[0])
            self.assertTrue(lines[1].endswith(str(old)))


class InstallTests(unittest.TestCase):
    def test_exact_projection_and_hashes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "bundle"
            installed = installer.install(bundle)
            actual = {str(p.relative_to(installed)) for p in installed.rglob("*") if p.is_file()}
            self.assertEqual(actual, set(installer.RUNTIME_PATHS))
            self.assertFalse(any(p.is_symlink() for p in bundle.rglob("*")))
            manifest = json.loads((bundle / "manifest.json").read_text())
            for entry in manifest["files"]:
                self.assertEqual(entry["sha256"], hashlib.sha256((installed / entry["path"]).read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                installer.install(bundle)

    def test_reject_symlink_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old_root = installer.ROOT
            try:
                installer.ROOT = root
                (root / "SKILL.md").symlink_to(ROOT / "SKILL.md")
                with self.assertRaises(ValueError):
                    installer.install(root / "bundle")
                self.assertFalse((root / "bundle").exists())
            finally:
                installer.ROOT = old_root


class EvalTests(unittest.TestCase):

    def test_each_assertion_accepts_good_and_rejects_wrong_decision(self):
        samples = results()
        broken = copy.deepcopy(samples)
        broken[1]["commands"][0]["cwd"] += "/out/AX615_fastnor/images"
        broken[2]["prerequisites"] = []
        broken[3]["commands"][0]["parallel"] = 32
        broken[4]["commands"][0]["cwd"] = oracle.SDK + "/boot/bl1"
        broken[5]["commands"][0]["parallel"] = 64
        for cid, sample in samples.items():
            with self.subTest(case=cid):
                oracle.validate(cid, sample)
                with self.assertRaises(AssertionError):
                    oracle.validate(cid, broken[cid])

    def test_generated_shell_assertions_execute_independently(self):
        cases = json.loads((ROOT / "evals/evals.json").read_text())["evals"]
        samples = results()
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / "out").mkdir()
            for case in cases:
                with self.subTest(case=case["id"]):
                    # Copy only assert.sh, like a harness with no sibling evaluator files.
                    wrapper = ROOT / "evals/cases" / case["name"] / "assert.sh"
                    (workspace / "assert.sh").write_bytes(wrapper.read_bytes())
                    (workspace / "out/result.json").write_text(json.dumps(samples[case["id"]]))
                    result = subprocess.run(["bash", "assert.sh"], cwd=workspace, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    (workspace / "out/result.json").write_text('{}')
                    result = subprocess.run(["bash", "assert.sh"], cwd=workspace, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)

    def test_fast_axp_requires_successful_full_build_for_same_project(self):
        sample = results()[5]
        sample["prerequisites"].remove("full_build_succeeded_for_same_project")
        with self.assertRaises(AssertionError):
            oracle.validate(5, sample)
        sample = results()[5]
        sample["full_build_project"] = "AX615_emmc"
        with self.assertRaises(AssertionError):
            oracle.validate(5, sample)

    def test_discovery_does_not_invent_projects_or_modules(self):
        for field, value in [("projects", ["invented"]), ("modules", ["invented"])]:
            sample = results()[1]
            sample[field] = value
            with self.assertRaises(AssertionError):
                oracle.validate(1, sample)

    def test_plans_must_not_claim_success(self):
        for cid, sample in results().items():
            sample["status"] = "success"
            with self.assertRaises(AssertionError):
                oracle.validate(cid, sample)


if __name__ == "__main__":
    unittest.main()
