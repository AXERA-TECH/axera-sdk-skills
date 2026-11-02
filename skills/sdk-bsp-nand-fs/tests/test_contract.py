import copy
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("skill_install", ROOT / "scripts/install.py")
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bundle = self.base / "bundle"

    def test_runtime_projection_and_manifest(self):
        destination = installer.install(self.bundle)
        self.assertEqual(destination, self.bundle / ".axap/opencode/skills/marketplace/sdk-bsp-nand-fs")
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        self.assertEqual(manifest["skill"], "sdk-bsp-nand-fs")
        expected = set()
        for name in installer.RUNTIME_PATHS:
            source = ROOT / name
            for path in source.rglob("*") if source.is_dir() else [source]:
                if path.is_file():
                    expected.add(str(path.relative_to(ROOT)))
        actual = {str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file()}
        self.assertEqual(actual, expected)
        self.assertEqual({entry["path"] for entry in manifest["files"]}, expected)
        self.assertEqual(len(manifest["files"]), len(expected))
        for entry in manifest["files"]:
            self.assertFalse(Path(entry["path"]).is_absolute())
            self.assertNotIn("..", Path(entry["path"]).parts)
            data = (destination / entry["path"]).read_bytes()
            self.assertEqual(data, (ROOT / entry["path"]).read_bytes())
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
        for name in ("evals", "tests", "ci", ".gitea", "scripts", ".git"):
            self.assertFalse((destination / name).exists())

    def test_refuses_existing_bundle(self):
        self.bundle.mkdir()
        sentinel = self.bundle / "keep"
        sentinel.write_text("unchanged")
        with self.assertRaises(ValueError):
            installer.install(self.bundle)
        self.assertEqual(sentinel.read_text(), "unchanged")

    def test_refuses_destination_symlink(self):
        self.bundle.symlink_to(self.base / "missing", target_is_directory=True)
        with self.assertRaises(ValueError):
            installer.install(self.bundle)
        self.assertFalse((self.base / "missing").exists())

    def copy_runtime(self):
        source = self.base / "source"
        source.mkdir()
        for name in installer.RUNTIME_PATHS:
            original = ROOT / name
            if original.is_dir():
                shutil.copytree(original, source / name)
            else:
                shutil.copy2(original, source / name)
        return source

    def test_refuses_nested_symlink(self):
        source = self.copy_runtime()
        (source / "reference/leak").symlink_to(ROOT / "evals", target_is_directory=True)
        with patch.object(installer, "ROOT", source), self.assertRaises(ValueError):
            installer.install(self.bundle)
        self.assertFalse(self.bundle.exists())

    def test_refuses_top_level_symlink(self):
        source = self.copy_runtime()
        (source / "platforms").rename(source / "saved-platforms")
        (source / "platforms").symlink_to(source / "saved-platforms", target_is_directory=True)
        with patch.object(installer, "ROOT", source), self.assertRaises(ValueError):
            installer.install(self.bundle)
        self.assertFalse(self.bundle.exists())

    def test_missing_runtime_input(self):
        source = self.copy_runtime()
        (source / "routing.yaml").unlink()
        with patch.object(installer, "ROOT", source), self.assertRaises(ValueError):
            installer.install(self.bundle)
        self.assertFalse(self.bundle.exists())

    def test_cli_install(self):
        result = subprocess.run(
            ["python3", "-I", str(ROOT / "scripts/install.py"), "--out", str(self.bundle)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(Path(result.stdout.strip()).is_dir())


class ContractTests(unittest.TestCase):
    def test_skill_name(self):
        text = (ROOT / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertRegex(frontmatter, r"(?m)^name: sdk-bsp-nand-fs$")
        self.assertRegex(frontmatter, r"(?m)^description: .+$")

    def test_skill_local_links(self):
        for target in re.findall(r"\]\(([^)]+)\)", (ROOT / "SKILL.md").read_text()):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            with self.subTest(target=target):
                self.assertTrue((ROOT / unquote(parsed.path)).is_file(), target)

    def test_shell_syntax(self):
        cases = [path for path in (ROOT / "evals/cases").iterdir() if path.is_dir()]
        self.assertTrue(cases)
        scripts = [case / "assert.sh" for case in cases]
        for script in scripts:
            with self.subTest(path=script):
                self.assertTrue(script.is_file())
                result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_python_syntax(self):
        for folder in ("scripts", "tests"):
            for path in (ROOT / folder).glob("*.py"):
                with self.subTest(path=path):
                    compile(path.read_bytes(), str(path), "exec")


class AssertionTests(unittest.TestCase):
    CASES = {
        "m57-linux": ("m57", "linux", ["SafetyIsland/mcal/source.txt"]),
        "m57-qnx": ("m57", "qnx", ["SafetyIsland/mcal/source.txt"]),
        "ax637-priority": ("ax637", "linux", ["SafetyIsland/rt-thread/bsp/m57/configs_ax637/source.txt"]),
        "unknown-platform": ("unknown", "unknown", []),
    }

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def prepare_case(self, case_id):
        case = ROOT / "evals/cases" / case_id
        workspace = self.base / case_id
        shutil.copytree(case / "fixtures", workspace)
        (workspace / "out").mkdir()
        platform, environment, route = self.CASES[case_id]
        data = {
            "schema_version": 1,
            "platform": platform,
            "environment": environment,
            "status": "needs_evidence",
            "route_evidence": route,
            "first_error": (workspace / "logs/evidence.txt").read_text().splitlines()[0],
            "evidence": ["logs/evidence.txt"],
            "missing_information": ["flash_model", "geometry", "partition_layout"],
            "write_allowed": False,
            "diagnosis": "证据不足，先核对最早错误所在设备层，不能确认根因。",
            "next_steps": ["只读收集 Flash 型号、geometry 和分区布局。"],
        }
        if platform == "unknown":
            data["questions"] = ["请确认平台、运行环境、Flash 型号和目标分区。"]
        return workspace, data

    def run_assertion(self, case_id, workspace):
        return subprocess.run(
            ["bash", str(ROOT / "evals/cases" / case_id / "assert.sh")],
            cwd=workspace, capture_output=True, text=True,
        )

    def write_result(self, workspace, data):
        (workspace / "out/result.json").write_text(json.dumps(data, ensure_ascii=False))

    def test_accepts_valid_results(self):
        for case_id in self.CASES:
            with self.subTest(case=case_id):
                workspace, data = self.prepare_case(case_id)
                self.write_result(workspace, data)
                result = self.run_assertion(case_id, workspace)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_invalid_contract_fields(self):
        changes = {
            "schema_version": True,
            "platform": "invented",
            "environment": "invented",
            "status": "solved",
            "first_error": "mount: final error only",
            "evidence": ["logs/missing.txt"],
            "missing_information": [],
            "write_allowed": True,
            "diagnosis": "",
            "next_steps": [],
        }
        for case_id in self.CASES:
            workspace, original = self.prepare_case(case_id)
            for field, value in changes.items():
                with self.subTest(case=case_id, field=field):
                    data = copy.deepcopy(original)
                    data[field] = value
                    self.write_result(workspace, data)
                    self.assertNotEqual(self.run_assertion(case_id, workspace).returncode, 0)
            for field in original:
                with self.subTest(case=case_id, missing=field):
                    data = copy.deepcopy(original)
                    del data[field]
                    self.write_result(workspace, data)
                    self.assertNotEqual(self.run_assertion(case_id, workspace).returncode, 0)
            with self.subTest(case=case_id, field="route_evidence"):
                data = copy.deepcopy(original)
                data["route_evidence"] = ["SafetyIsland/mcal/source.txt"] if case_id in (
                    "ax637-priority", "unknown-platform"
                ) else []
                self.write_result(workspace, data)
                self.assertNotEqual(self.run_assertion(case_id, workspace).returncode, 0)

    def test_rejects_missing_or_invalid_json(self):
        for case_id in self.CASES:
            workspace, _ = self.prepare_case(case_id)
            with self.subTest(case=case_id, output="missing"):
                self.assertNotEqual(self.run_assertion(case_id, workspace).returncode, 0)
            for payload in ("{broken", "[]", "null"):
                with self.subTest(case=case_id, output=payload):
                    (workspace / "out/result.json").write_text(payload)
                    self.assertNotEqual(self.run_assertion(case_id, workspace).returncode, 0)

    def test_allows_framework_runtime_files(self):
        workspace, data = self.prepare_case("ax637-priority")
        runtime = workspace / ".axap/opencode"
        runtime.mkdir(parents=True)
        (runtime / "runtime.json").write_text("{}")
        self.write_result(workspace, data)
        result = self.run_assertion("ax637-priority", workspace)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_modified_evidence(self):
        for case_id in self.CASES:
            with self.subTest(case=case_id):
                workspace, data = self.prepare_case(case_id)
                self.write_result(workspace, data)
                (workspace / "logs/evidence.txt").write_text("fabricated evidence\n")
                self.assertNotEqual(self.run_assertion(case_id, workspace).returncode, 0)


if __name__ == "__main__":
    unittest.main()
