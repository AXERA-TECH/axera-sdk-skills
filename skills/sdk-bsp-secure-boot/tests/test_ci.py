"""Exercise bundle isolation and independent assertion failure paths."""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("install", ROOT / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class BundleTests(unittest.TestCase):
    def test_installed_reference_indexes_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = installer.install(Path(tmp) / "bundle")
            reference_roots = re.findall(r"(?m)^\s*reference_root:\s*(\S+)",
                                         (destination / "routing.yaml").read_text())
            self.assertTrue(reference_roots)
            for reference_root in reference_roots:
                index = destination / reference_root / "_index.md"
                with self.subTest(reference_root=reference_root):
                    self.assertTrue(index.is_file(), f"Missing reference index: {index}")
                    references = re.findall(r"`(reference/[^`]+\.md)`", index.read_text())
                    self.assertTrue(references)
                    for reference in references:
                        self.assertTrue((destination / reference).is_file(), reference)

    def test_installed_resource_references_resolve_after_workspace_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle"
            destination = installer.install(bundle)
            workspace = Path(tmp) / "workspace"
            shutil.copytree(bundle, workspace)
            deployed = workspace / destination.relative_to(bundle)
            for name in ("SKILL.md", "platforms/m57.md", "platforms/ax637.md"):
                text = (deployed / name).read_text()
                self.assertNotIn("<SKILL_ROOT>", text)
                references = re.findall(r"`([^`]+/platforms/(?:m57|ax637)\.md)`", text)
                self.assertTrue(references, name)
                for reference in references:
                    with self.subTest(document=name, reference=reference):
                        self.assertTrue((workspace / reference).is_file())
                        self.assertNotIn(str(bundle), reference)

    def test_runtime_projection_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle"
            destination = installer.install(bundle)
            manifest = json.loads((bundle / "manifest.json").read_text())
            actual = {str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()}
            self.assertEqual(actual, {x["path"] for x in manifest["files"]})
            import hashlib
            for item in manifest["files"]:
                self.assertEqual(hashlib.sha256((destination / item["path"]).read_bytes()).hexdigest(), item["sha256"])
            self.assertTrue({"SKILL.md", "routing.yaml", "platforms/m57.md", "platforms/ax637.md"} <= actual)
            self.assertFalse(any(p.split('/')[0] in {"evals", "tests", "ci", ".git"} for p in actual))
            with self.assertRaises(ValueError):
                installer.install(bundle)

    def test_symlink_and_missing_runtime_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_root = installer.ROOT
            try:
                installer.ROOT = Path(tmp) / "source"
                installer.ROOT.mkdir()
                for name in installer.RUNTIME_PATHS:
                    source = ROOT / name
                    target = installer.ROOT / name
                    if source.is_dir():
                        shutil.copytree(source, target)
                    else:
                        shutil.copy2(source, target)
                marker = installer.ROOT / "reference/leak"
                marker.symlink_to(ROOT / "evals")
                with self.assertRaises(ValueError):
                    installer.install(Path(tmp) / "linked")
                marker.unlink()
                (installer.ROOT / "routing.yaml").unlink()
                with self.assertRaises(ValueError):
                    installer.install(Path(tmp) / "missing")
            finally:
                installer.ROOT = original_root


class FixtureTests(unittest.TestCase):
    def test_explicit_platform_has_matching_fixture_config(self):
        for case in sorted((ROOT / "evals/cases").iterdir()):
            target = re.search(r"\b(?:ax637_)?demo_(?:nor_nand|only_nand|only_emmc)\b",
                               (case / "case.yaml").read_text())
            if target:
                with self.subTest(case=case.name):
                    config = case / "fixtures/build/platforms/axera" / target[0] / "config.mk"
                    self.assertTrue(config.is_file(), f"Prompt target missing from fixture: {target[0]}")

    def test_output_directory_survives_file_only_fixture_copy(self):
        # The harness copies files and creates their parents; empty dirs disappear.
        for case in sorted((ROOT / "evals/cases").iterdir()):
            with self.subTest(case=case.name), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                for source in (case / "fixtures").rglob("*"):
                    if source.is_file():
                        target = work / source.relative_to(case / "fixtures")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                self.assertTrue((work / "out").is_dir(), "Missing output directory")
                self.assertTrue(list((work / "out").glob("*")), "Output lookup has no files")
                self.assertFalse((work / "out/response.md").exists())
                self.assertFalse((work / "out/analysis.json").exists())


class AssertionTests(unittest.TestCase):
    def test_rsa_pss_accepts_equivalent_pkcs_padding_names(self):
        for name in ("acceptance-config-rsa-pss", "acceptance-ax637-rsa-pss"):
            case = ROOT / "evals/cases" / name
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                shutil.copytree(case / "fixtures", work, dirs_exist_ok=True)
                output = work / "out/response.md"
                def run(padding):
                    output.write_text(
                        f"SIGN_USE_RSA_PSS：FALSE 使用 {padding}；SBL 之后的后段支持 RSA-PSS，"
                        "SIGN_USE_RSA3072 控制位数。\n")
                    return subprocess.run(["bash", str(case / "assert.sh")], cwd=work, capture_output=True)
                for padding in ("PKCS#1-v1.5", "PKCS#1 v1.5", "**PKCS#1** **v1.5**"):
                    with self.subTest(padding=padding):
                        result = run(padding)
                        self.assertEqual(result.returncode, 0, result.stderr.decode())
                for padding in ("PKCS#1 v2.1", "RSA-PSS", "PKCS#1"):
                    with self.subTest(invalid_padding=padding):
                        self.assertNotEqual(run(padding).returncode, 0)

    def test_ax637_config_accepts_build_wording(self):
        case = ROOT / "evals/cases/acceptance-ax637-config-build"
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shutil.copytree(case / "fixtures", work, dirs_exist_ok=True)
            (work / "out").mkdir(exist_ok=True)
            output = work / "out/response.md"
            text = ("ax637_demo_only_nand：未烧写 eFuse。\n"
                    "SECURE_BOOT := TRUE\nSIGN_USE_RSA3072 := FALSE\n"
                    "ENABLE_CIPHER := FALSE\nROOTFS_DMVERITY := FALSE\nROOTFS_FS_TYPE := UBI\n"
                    "构建与产物清单说明。\n")
            output.write_text(text)
            def run():
                return subprocess.run(["bash", str(case / "assert.sh")], cwd=work, capture_output=True)
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            output.write_text(text.replace("构建与产物清单说明。", ""))
            self.assertNotEqual(run().returncode, 0)

    def test_ax637_diagnosis_accepts_ci_signature_failure_wording(self):
        case = ROOT / "evals/cases/acceptance-ax637-spl-rsa-failure"
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            shutil.copytree(case / "fixtures", work, dirs_exist_ok=True)
            (work / "out").mkdir(exist_ok=True)
            output = work / "out/response.md"
            analysis = work / "out/analysis.json"
            analysis.write_text(json.dumps({"verifier": "sbl", "image": "spl", "slot": 0,
                                            "error_code": -9, "rsa_signature_failed": True}))
            # CI #6 correctly diagnosed the failure with this wording.
            text = ("SBL 正在引导 slot 0 的 SPL 镜像。\n"
                    "SPL 镜像内容的 RSA 签名验签未通过（返回码 -9 代表签名校验失败）。\n"
                    "sha256sum build/out/<PLAT>/images/u-boot-spl_signed.img\n")
            output.write_text(text)
            def run():
                return subprocess.run(["bash", str(case / "assert.sh")], cwd=work, capture_output=True)
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            output.write_text(text.replace("RSA 签名验签未通过（返回码 -9 代表签名校验失败）", "-9 代表解密失败"))
            analysis.write_text(json.dumps({"verifier": "sbl", "image": "spl", "slot": 0,
                                            "error_code": -9, "rsa_signature_failed": False}))
            self.assertNotEqual(run().returncode, 0)

    def test_oracles_accept_valid_and_reject_invalid_outputs(self):
        for case in sorted((ROOT / "evals/cases").iterdir()):
            with self.subTest(case=case.name), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                shutil.copytree(case / "fixtures", work, dirs_exist_ok=True)
                source = (case / "assert.sh").read_text()
                match = re.search(r"oracle = json.loads\((.*)\)", source)
                if match:
                    import ast
                    oracle = json.loads(ast.literal_eval(match[1]))
                    text = '\n'.join(rule.get("contains", rule.get("contains_any", [" ".join(rule.get("command_tokens", []))])[0]) for rule in oracle["assertions"])
                else:
                    text = "请提供并确认平台和板型，然后确认 PLAT、eFuse、RSA、加密和 dm-verity。"
                (work / "out").mkdir(exist_ok=True)
                output = work / "out/response.md"
                output.write_text(text)
                analysis = work / "out/analysis.json"
                if oracle_routing := (oracle.get("routing") if match else None):
                    analysis.write_text(json.dumps(oracle_routing))
                if oracle_analysis := (oracle.get("analysis") if match else None):
                    analysis.write_text(json.dumps(oracle_analysis))
                def run():
                    return subprocess.run(["bash", str(case / "assert.sh")], cwd=work, capture_output=True)
                result = run()
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                if oracle_routing:
                    output.write_text(text + '\n请确认 PLAT（例如 ax637_demo_only_emmc）？')
                    self.assertEqual(run().returncode, 0)
                    output.write_text(text)
                    for wrong in ({"platform": "ax637", "selected_plat": None},
                                  {"platform": "m57", "selected_plat": "demo_only_nand"}):
                        analysis.write_text(json.dumps(wrong))
                        self.assertNotEqual(run().returncode, 0)
                    analysis.write_text(json.dumps(oracle_routing))
                if oracle_analysis:
                    for key, wrong in {"verifier": "spl", "image": "uboot", "slot": 1,
                                       "error_code": -8, "rsa_signature_failed": False}.items():
                        analysis.write_text(json.dumps({**oracle_analysis, key: wrong}))
                        self.assertNotEqual(run().returncode, 0)
                    for key, wrong in {"slot": False, "rsa_signature_failed": 1}.items():
                        analysis.write_text(json.dumps({**oracle_analysis, key: wrong}))
                        self.assertNotEqual(run().returncode, 0)
                    analysis.write_text(json.dumps(oracle_analysis))
                if case.name == "acceptance-configure-demo-only-nand":
                    for spelling in ("RSA 2048", "RSA2048", "RSA-2048"):
                        output.write_text(text.replace("RSA-2048", spelling))
                        self.assertEqual(run().returncode, 0)
                    output.write_text(text.replace("RSA-2048", "RSA 3072"))
                    self.assertNotEqual(run().returncode, 0)
                if match:
                    output.write_text("**" + text + "**")
                    self.assertEqual(run().returncode, 0)
                    for rule in oracle["assertions"]:
                        if "command_tokens" in rule:
                            command = " ".join(rule["command_tokens"])
                            reordered = "make --dry-run axp PLAT=demo_only_nand -C build"
                            output.write_text(text.replace(command, reordered))
                            self.assertEqual(run().returncode, 0)
                            output.write_text(text.replace(command, command.replace(" -n", "")))
                            self.assertNotEqual(run().returncode, 0)
                output.write_text("Unrelated response")
                self.assertNotEqual(run().returncode, 0)
                output.write_text(text)
                if match:
                    for rule in oracle["assertions"]:
                        if "not_contains" in rule:
                            output.write_text(text + '\n' + rule["not_contains"])
                            self.assertNotEqual(run().returncode, 0)
                    output.write_text(text)
                    (work / oracle["config"]).write_text("SECURE_BOOT := TRUE\n")
                    self.assertNotEqual(run().returncode, 0)
                else:
                    (work / "config.mk").write_text("SECURE_BOOT := TRUE\n")
                    self.assertNotEqual(run().returncode, 0)


if __name__ == "__main__":
    unittest.main()
