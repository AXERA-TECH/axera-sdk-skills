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


class AssertionTests(unittest.TestCase):
    def test_ci_equivalent_wording(self):
        examples = [
            ("ax637-mem-002",
             "在 config.mk 设置 LINUX_MEMORY_SZ，重新编译 U-Boot 并打包。\n"
             "DTS 的 memory 由 ft_system_fixup_memory 启动时生成，通过 /proc/meminfo 验证。",
             "启动时生成", "固定写死且不会更新"),
            ("ax637-mem-001",
             "Linux 384 MiB，CMM 640 MiB；ATF 预留使 Linux 实际可用量更小。\n"
             "需确认真实 DDR 容量和地址映射，不能将文档示例当作已验证的部署值。",
             "需确认真实 DDR 容量和地址映射，不能将文档示例当作已验证的部署值。",
             "文档示例就是已验证的部署值。"),
            ("m57-part-003",
             "partitions.json：分区从偏移地址 `0` 开始紧密向后排布。\n"
             "AXDL 写入 metadata，U-Boot 读取 mtdparts。",
             "分区从偏移地址 `0` 开始紧密向后排布", "分区起始位置未知"),
            ("ax637-mem-002",
             "修改 config.mk 的 LINUX_MEMORY_SZ，重新编译 U-Boot 并生成打包文件。\n"
             "ft_system_fixup_memory 动态生成 memory 节点，通过 /proc/meminfo 验证。",
             "重新编译 U-Boot 并生成打包文件", "无需编译或打包"),
        ]
        for name, text, correct, incorrect in examples:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                case = ROOT / "evals/cases" / name
                shutil.copytree(case / "fixtures", work, dirs_exist_ok=True)
                (work / "out").mkdir()
                output = work / "out/response.md"
                output.write_text(text)
                def run():
                    return subprocess.run(["bash", str(case / "assert.sh")], cwd=work, capture_output=True)
                result = run()
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                output.write_text(text.replace(correct, incorrect))
                self.assertNotEqual(run().returncode, 0)

    def test_oracles_accept_valid_and_reject_invalid_outputs(self):
        import ast
        for case in sorted((ROOT / "evals/cases").iterdir()):
            with self.subTest(case=case.name), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                shutil.copytree(case / "fixtures", work, dirs_exist_ok=True)
                source = (case / "assert.sh").read_text()
                match = re.search(r"oracle = json.loads\((.*)\)", source)
                oracle = json.loads(ast.literal_eval(match[1]))
                text = '\n'.join(rule.get("contains", rule.get("contains_any", [""])[0]) for rule in oracle["assertions"])
                (work / "out").mkdir()
                output = work / "out/response.md"
                output.write_text(text)
                analysis = work / "out/analysis.json"
                if oracle["structured"] is not None:
                    analysis.write_text(json.dumps(oracle["structured"]))
                def run():
                    return subprocess.run(["bash", str(case / "assert.sh")], cwd=work, capture_output=True)
                result = run()
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                output.write_text("**" + text + "**")
                self.assertEqual(run().returncode, 0)
                output.write_text("Unrelated response")
                self.assertNotEqual(run().returncode, 0)
                output.write_text(text)
                if oracle["structured"] is not None:
                    wrong = dict(oracle["structured"])
                    key = next(iter(wrong))
                    wrong[key] = "wrong"
                    analysis.write_text(json.dumps(wrong))
                    self.assertNotEqual(run().returncode, 0)
                    analysis.write_text(json.dumps(oracle["structured"]))
                    # JSON booleans must not pass as integer calculation results.
                    for key, expected in oracle["structured"].items():
                        if isinstance(expected, bool):
                            wrong = dict(oracle["structured"])
                            wrong[key] = int(expected)
                            analysis.write_text(json.dumps(wrong))
                            self.assertNotEqual(run().returncode, 0)
                            analysis.write_text(json.dumps(oracle["structured"]))
                created_config = work / "config.mk"
                created_config.write_text("LINUX_MEMORY_SZ := 0x20000000\n")
                self.assertNotEqual(run().returncode, 0)
                created_config.unlink()
                path = work / next(iter(oracle["files"]))
                path.write_text("Changed fixture\n")
                self.assertNotEqual(run().returncode, 0)


if __name__ == "__main__":
    unittest.main()
