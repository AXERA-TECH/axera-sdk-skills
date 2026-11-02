import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "scripts/install.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load skill installer")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

CORE_RESULTS = {
    "m57-routing": {"platform": "m57", "loaded_rules": ["platforms/m57.md"]},
    "ax637-routing": {"platform": "ax637", "loaded_rules": ["platforms/m57.md", "platforms/ax637.md"]},
    "ax637-boundary": {"platform": "ax637", "qnx_supported": False, "sync_m57_qnx_changes": False},
    "m57-rpzc": {
        "check_available_before_transmit": True,
        "receive_steps": ["RECEIVE_BUF", "CONSUME_PAYLOAD", "REPLY_ACK"],
        "reply_ack_only_if_requested": True,
        "reuse_sender_buffer_after_ack": True,
    },
}

GOOD_ANSWERS = {
    "m57-linux": "M57 Linux 要核对 CONFIG_AXERA_MBOX CONFIG_RPMSG_AXERA CONFIG_RPMSG_CHAR CONFIG_RPMSG_CTRL CONFIG_RPZC_SERVICE_RPMSG CONFIG_RPZC_CONTROLLER。目标 DTS 的 memory-region 和 mboxes 与 MCU 对端一致；用户态用 /dev/rpmsg_ctrlX 和 /dev/rpzc_ctrlN。物理地址仅是示例，不能直接照搬。",
    "m57-qnx": "M57 QNX 使用 kernel/osdrv/open_drv/ax_ipc/ 的 Ipc_cfg、Ipc_zc_cfg 核对 LocalAddr/RemoteAddr；RL_ADDR_ANY 需 NEED_NS。IPC_ZC_BUFFER_BY_DDR=0 对应 IRAM，切换 DDR 与 MCU 同步。IPC_GPIO_TRIGGER_IRQ_EN 控制通知方式。用 pidin syspage=asinfo 核对预留，用 sample_ipc_rpmsg 测试。",
    "m57-mcal": "SafetyIsland/mcal/mcal_drv/Ipc/ 和 SafetyIsland/rt-thread/bsp/m57/drivers/ipc/ 的两端配置要匹配。先检查 IpcEptLinkStatusCheck 和 IpcZcLinkStatusCheck，消费后 ACK。sample_ipc_test 与 sample_ipczc_test 是否可用取决于是否编入镜像；问题复盘来源是 reference/ax_ipc_FAQ.md。",
    "ax637-rpzc": "AX637 Linux 应查 endpoint 和 name service、BufferName、reserved-memory/共享内存与对端。CHECK_AVAIL 之前核对 IpcZcLinkStatusCheck；收到 ACK 后再复用，reset 时 reinit。不可直接照搬 M57 示例地址。",
    "ax637-rtos": "AX637 的 SafetyIsland/rt-thread/bsp/m57/drivers/ipc/ 下有 cfg/、rpmsg/、rpzc/。sample_ipc_test 与 sample_ipczc_test 是否可用需确认编入当前镜像。Linux 与对端 shared memory、endpoint 一致，不能直接照搬 M57 板级配置。",
}

# 拆分拼接，避免源码中出现完整内部域名，同时保持对内部站点链接的检查强度。
INTERNAL_URL = r"https?://[^\s`<>)]*" + "aixin" + r"-chip\.com"


class BundleTests(unittest.TestCase):
    def test_runtime_bundle_excludes_eval_answers(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "bundle"
            skill = installer.install(bundle)
            actual = {str(path.relative_to(skill)) for path in skill.rglob("*") if path.is_file()}
            expected = {"SKILL.md", "routing.yaml"}
            expected.update(str(path.relative_to(ROOT)) for name in ("platforms", "reference")
                            for path in (ROOT / name).rglob("*") if path.is_file())
            self.assertEqual(actual, expected)
            self.assertFalse(any(path.startswith(("evals/", "tests/", "ci/", "scripts/")) for path in actual))
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["skill"], "sdk-bsp-rpmsg")
            self.assertEqual({file["path"] for file in manifest["files"]}, actual)
            for file in manifest["files"]:
                self.assertEqual(file["sha256"], hashlib.sha256((skill / file["path"]).read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                installer.install(bundle)

    def test_runtime_sources_must_exist_and_not_be_links(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(installer, "ROOT", Path(temp)):
            with self.assertRaises(ValueError):
                installer.install(Path(temp) / "bundle")
            for name in ("SKILL.md", "routing.yaml"):
                (Path(temp) / name).write_text(name, encoding="utf-8")
            for name in ("platforms", "reference"):
                (Path(temp) / name).mkdir()
            (Path(temp) / "platforms/link").symlink_to(Path(temp) / "SKILL.md")
            with self.assertRaises(ValueError):
                installer.install(Path(temp) / "bundle")


    def test_indexed_references_exist_and_docx_are_valid_archives(self):
        index = (ROOT / "reference/_index.md").read_text(encoding="utf-8")
        import re
        references = re.findall(r"`(reference/[^`]+)`", index)
        self.assertGreaterEqual(len(references), 7)
        for relative in references:
            with self.subTest(reference=relative):
                target = ROOT / relative
                self.assertTrue(target.is_file(), relative)
                if target.suffix == ".docx":
                    with zipfile.ZipFile(target) as archive:
                        self.assertIsNone(archive.testzip())
                        self.assertIn("word/document.xml", archive.namelist())


class FaqReferenceTests(unittest.TestCase):
    def test_faq_preserves_nine_problem_sections_and_platform_scope(self):
        text = (ROOT / "reference/ax_ipc_FAQ.md").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^## 问题(\d+)：", text, re.M),
                         [str(number) for number in range(1, 10)])
        for term in ("M57 IPC&IPCZC问题复盘", "v18", "2026-08-12", "AX637 不支持 QNX",
                     "未实现", "-5001", "previous recv data not treated", "MEM_BARRIER"):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_faq_routes_use_local_reference_without_internal_urls(self):
        for relative in ("README.md", "skill-card.md", "SKILL.md",
                         "platforms/m57.md", "reference/_index.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("ax_ipc_FAQ.md", text)
                self.assertNotRegex(text, INTERNAL_URL)
                self.assertNotIn("已删除的本地", text)
        for path in (ROOT / "reference").rglob("*.md"):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotRegex(path.read_text(encoding="utf-8"), INTERNAL_URL)

    def test_installed_faq_and_all_nine_images_are_available_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "bundle"
            skill = installer.install(bundle)
            faq = skill / "reference/ax_ipc_FAQ.md"
            images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", faq.read_text(encoding="utf-8"))
            self.assertEqual(len(images), 9)
            self.assertEqual(len(set(images)), 9)
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            packaged = {item["path"] for item in manifest["files"]}
            self.assertIn("reference/ax_ipc_FAQ.md", packaged)
            for image in images:
                with self.subTest(image=image):
                    self.assertNotIn("://", image)
                    path = (faq.parent / image).resolve()
                    self.assertTrue(path.is_relative_to(skill.resolve()))
                    self.assertIn(str(path.relative_to(skill)), packaged)
                    self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))


class SuiteLayoutTests(unittest.TestCase):
    def test_core_fixtures_initialize_empty_output_directory_without_answers(self):
        for name, expected in CORE_RESULTS.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temp:
                case = ROOT / "evals/cases" / name
                workspace = Path(temp) / "workspace"
                shutil.copytree(case / "fixtures", workspace)
                out = workspace / "out"
                self.assertEqual({path.name for path in out.iterdir()}, {".gitkeep"})
                self.assertEqual((out / ".gitkeep").read_bytes(), b"")
                command = ["bash", str(case / "assert.sh")]
                missing = subprocess.run(command, cwd=workspace, capture_output=True, text=True)
                self.assertNotEqual(missing.returncode, 0, "Empty output directory bypassed the oracle")
                (out / "result.json").write_text(json.dumps(expected), encoding="utf-8")
                completed = subprocess.run(command, cwd=workspace, capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_automatic_case_directories_match_suite_exactly(self):
        suite = (ROOT / "evals/suite.yaml").read_text(encoding="utf-8")
        registered = re.findall(r"^\s+path:\s+(cases/[^\s]+)\s*$", suite, re.M)
        actual = {str(path.relative_to(ROOT / "evals"))
                  for path in (ROOT / "evals/cases").iterdir() if path.is_dir()}
        self.assertEqual(len(registered), len(set(registered)), "Duplicate case paths in suite")
        self.assertEqual(actual, set(registered), "Unregistered or missing automatic case directories")
        for relative in registered:
            self.assertTrue((ROOT / "evals" / relative / "case.yaml").is_file(), relative)


class CoreResultTests(unittest.TestCase):
    def run_oracle(self, name, contents):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "out"
            out.mkdir()
            (out / "answer.md").write_text("人工说明，不应被核心 oracle 读取。", encoding="utf-8")
            if contents is not None:
                (out / "result.json").write_text(contents, encoding="utf-8")
            return subprocess.run(["bash", str(ROOT / "evals/cases" / name / "assert.sh")],
                                  cwd=temp, capture_output=True, text=True)

    def assert_oracle_failure(self, name, result, exists=True, kinds=("AssertionError",)):
        self.assertNotEqual(result.returncode, 0, "Oracle accepted an invalid core result")
        records = [json.loads(line.removeprefix("RPMSG_DIAG:"))
                   for line in result.stderr.splitlines() if line.startswith("RPMSG_DIAG:")]
        self.assertEqual(len(records), 1, result.stderr)
        record = records[0]
        self.assertEqual(record["case"], name)
        self.assertEqual(record["phase"], "oracle")
        self.assertIn(record["kind"], kinds, result.stderr)
        self.assertIs(record["answer_exists"], exists)
        self.assertNotIn("Traceback", result.stderr)
        return record

    def test_core_oracles_accept_json_with_free_explanations_and_formatting(self):
        for name, expected in CORE_RESULTS.items():
            variants = (
                json.dumps(expected),
                json.dumps({**expected, "explanation": "已按目标平台核对结构化结论。"},
                           ensure_ascii=False, indent=2),
                json.dumps({"explanation": "这段中文说明可以自由表述，不作为断言依据。",
                            **dict(reversed(list(expected.items())))},
                           ensure_ascii=False, indent=4),
                json.dumps({**expected, "explanation": "采用另一种解释和字段排列。"},
                           ensure_ascii=False, sort_keys=True),
            )
            for contents in variants:
                with self.subTest(case=name, contents=contents):
                    result = self.run_oracle(name, contents)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_core_oracles_reject_wrong_platforms(self):
        for name in ("m57-routing", "ax637-routing", "ax637-boundary"):
            with self.subTest(case=name):
                wrong = "ax637" if name == "m57-routing" else "m57"
                contents = json.dumps({**CORE_RESULTS[name], "platform": wrong})
                self.assert_oracle_failure(name, self.run_oracle(name, contents))

    def test_core_routing_requires_exact_ordered_rules(self):
        variants = {
            "m57-routing": (
                [], ["platforms/ax637.md"], ["platforms/m57.md", "platforms/qnx.md"],
                "platforms/m57.md", None,
            ),
            "ax637-routing": (
                ["platforms/ax637.md", "platforms/m57.md"], ["platforms/ax637.md"],
                ["platforms/m57.md"], ["platforms/m57.md", "platforms/ax637.md", "platforms/qnx.md"],
                "platforms/m57.md,platforms/ax637.md", None,
            ),
        }
        for name, rules in variants.items():
            for loaded_rules in rules:
                with self.subTest(case=name, loaded_rules=loaded_rules):
                    contents = json.dumps({**CORE_RESULTS[name], "loaded_rules": loaded_rules})
                    self.assert_oracle_failure(name, self.run_oracle(name, contents))
            with self.subTest(case=name, loaded_rules="missing"):
                contents = json.dumps({"platform": CORE_RESULTS[name]["platform"]})
                self.assert_oracle_failure(name, self.run_oracle(name, contents))

    def test_core_boolean_fields_require_real_json_booleans(self):
        for name in ("ax637-boundary", "m57-rpzc"):
            for field, expected in CORE_RESULTS[name].items():
                if type(expected) is not bool:
                    continue
                for value in (not expected, str(expected).lower(), int(expected), None):
                    with self.subTest(case=name, field=field, value=value):
                        contents = json.dumps({**CORE_RESULTS[name], field: value})
                        self.assert_oracle_failure(name, self.run_oracle(name, contents))
                with self.subTest(case=name, field=field, value="missing"):
                    contents = json.dumps({key: value for key, value in CORE_RESULTS[name].items() if key != field})
                    self.assert_oracle_failure(name, self.run_oracle(name, contents))

    def test_core_rpzc_requires_receive_consume_ack_order(self):
        name = "m57-rpzc"
        for steps in (
            ["RECEIVE_BUF", "REPLY_ACK", "CONSUME_PAYLOAD"],
            ["REPLY_ACK", "CONSUME_PAYLOAD", "RECEIVE_BUF"],
            ["RECEIVE_BUF", "REPLY_ACK"], [], "RECEIVE_BUF CONSUME_PAYLOAD REPLY_ACK", None,
        ):
            with self.subTest(receive_steps=steps):
                contents = json.dumps({**CORE_RESULTS[name], "receive_steps": steps})
                self.assert_oracle_failure(name, self.run_oracle(name, contents))
        with self.subTest(receive_steps="missing"):
            contents = json.dumps({key: value for key, value in CORE_RESULTS[name].items() if key != "receive_steps"})
            self.assert_oracle_failure(name, self.run_oracle(name, contents))

    def test_core_oracles_reject_missing_malformed_and_markdown_json(self):
        for name, expected in CORE_RESULTS.items():
            for contents, exists, kinds in (
                (None, False, ("FileNotFoundError",)),
                ("{not valid JSON", True, ("JSONDecodeError", "AssertionError")),
                ("[]", True, ("AssertionError",)),
                ("null", True, ("AssertionError",)),
                ("{}", True, ("AssertionError",)),
                ("```json\n" + json.dumps(expected) + "\n```\n", True, ("JSONDecodeError", "AssertionError")),
            ):
                with self.subTest(case=name, contents=contents):
                    record = self.assert_oracle_failure(name, self.run_oracle(name, contents), exists, kinds)
                    if not exists:
                        self.assertEqual(record["first_lines"], [])
                        self.assertEqual(record["evidence"], [])

    def test_core_diagnostics_read_result_json_instead_of_answer_markdown(self):
        name = "ax637-boundary"
        contents = json.dumps({**CORE_RESULTS[name], "qnx_supported": True}, indent=2)
        result = self.run_oracle(name, contents)
        record = self.assert_oracle_failure(name, result)
        self.assertEqual(record["check"], "AX637_BOUNDARY_QNX")
        self.assertEqual(record["first_lines"], contents.splitlines()[:2])
        self.assertTrue(any('"qnx_supported": true' in line for line in record["evidence"]), result.stderr)
        self.assertNotIn("人工说明", result.stderr)

    def test_core_json_diagnostics_redact_full_lines_before_cropping(self):
        name = "m57-routing"
        contents = json.dumps({"explanation": "x" * 300 + " token=do-not-print ghp_abc123",
                               **CORE_RESULTS[name], "platform": "ax637"}, indent=2)
        result = self.run_oracle(name, contents)
        record = self.assert_oracle_failure(name, result)
        self.assertEqual(record["first_lines"][1], "<REDACTED>")
        self.assertNotIn("do-not-print", result.stderr)
        self.assertNotIn("ghp_abc123", result.stderr)
        self.assertTrue(all(len(line) <= 240 for line in record["first_lines"] + record["evidence"]))


class EvalTests(unittest.TestCase):
    def test_case_oracles_accept_valid_answers_and_reject_missing_platform_facts(self):
        cases = ROOT / "tests/manual"
        self.assertTrue(set(CORE_RESULTS).isdisjoint(GOOD_ANSWERS))
        self.assertEqual({path.name for path in (ROOT / "evals/cases").iterdir() if path.is_dir()}, set(CORE_RESULTS))
        self.assertEqual({path.name for path in cases.iterdir() if path.is_dir()}, set(GOOD_ANSWERS))
        for name, answer in GOOD_ANSWERS.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / "out"
                out.mkdir()
                output = out / "answer.md"
                command = ["bash", str(cases / name / "assert.sh")]
                output.write_text(answer, encoding="utf-8")
                good = subprocess.run(command, cwd=temp, capture_output=True, text=True)
                self.assertEqual(good.returncode, 0, good.stderr)
                output.write_text("Unsupported platform; no further checks needed.", encoding="utf-8")
                bad = subprocess.run(command, cwd=temp, capture_output=True, text=True)
                self.assertNotEqual(bad.returncode, 0, "Oracle accepted irrelevant answer")
                self.assertIn("RPMSG_ASSERT:", bad.stderr, "Oracle failure lacks a diagnostic code")

    def test_mcal_oracle_requires_local_faq_instead_of_wiki_page_id(self):
        for source in ("reference/ax_ipc_FAQ.md", "Wiki 211674096", ""):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / "out"
                out.mkdir()
                answer = GOOD_ANSWERS["m57-mcal"].replace("reference/ax_ipc_FAQ.md", source)
                (out / "answer.md").write_text(answer, encoding="utf-8")
                result = subprocess.run(["bash", str(ROOT / "tests/manual/m57-mcal/assert.sh")],
                                        cwd=temp, capture_output=True, text=True)
                if source == "reference/ax_ipc_FAQ.md":
                    self.assertEqual(result.returncode, 0, result.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("M57_MCAL_MISSING_FAQ_SOURCE", result.stderr)

    def test_oracles_accept_equivalent_platform_guidance(self):
        variants = {
            "m57-linux": GOOD_ANSWERS["m57-linux"].replace(
                "目标 DTS", "当前板卡设备树").replace(
                "物理地址仅是示例，不能直接照搬。", "示例物理地址不得照抄，应核对当前板卡的实际地址。"),
            "m57-mcal": GOOD_ANSWERS["m57-mcal"].replace(
                "SafetyIsland/mcal/mcal_drv/Ipc/", "`SafetyIsland/mcal/mcal_drv/Ipc`").replace(
                "SafetyIsland/rt-thread/bsp/m57/drivers/ipc/", "`SafetyIsland/rt-thread/bsp/m57/drivers/ipc`"),
            "ax637-rtos": GOOD_ANSWERS["ax637-rtos"].replace(
                "不能直接照搬 M57 板级配置。", "M57 的板级地址不得照抄，应核对当前板卡的资源。"),
        }
        for name, answer in variants.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / "out"
                out.mkdir()
                (out / "answer.md").write_text(answer, encoding="utf-8")
                result = subprocess.run(["bash", str(ROOT / "tests/manual" / name / "assert.sh")],
                                        cwd=temp, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_linux_controller_devices_accept_indices_but_reject_other_nodes(self):
        variants = (
            (GOOD_ANSWERS["m57-linux"], True),
            (GOOD_ANSWERS["m57-linux"].replace("/dev/rpzc_ctrlN", "/dev/rpzc_ctrl0"), True),
            (GOOD_ANSWERS["m57-linux"].replace("/dev/rpmsg_ctrlX", "/dev/rpmsg_ctrl0").replace(
                "/dev/rpzc_ctrlN", "/dev/rpzc_ctrl12"), True),
            (GOOD_ANSWERS["m57-linux"].replace("/dev/rpzc_ctrlN", "/dev/rpzc-buffer0"), False),
            (GOOD_ANSWERS["m57-linux"].replace("/dev/rpzc_ctrlN", "/dev/rpzc_ctrl0_bad"), False),
            (GOOD_ANSWERS["m57-linux"].replace("/dev/rpzc_ctrlN", ""), False),
        )
        for answer, accepted in variants:
            with self.subTest(accepted=accepted, answer=answer), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / "out"
                out.mkdir()
                (out / "answer.md").write_text(answer, encoding="utf-8")
                result = subprocess.run(["bash", str(ROOT / "tests/manual/m57-linux/assert.sh")],
                                        cwd=temp, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_mcal_image_availability_accepts_documented_build_wording(self):
        original = "是否可用取决于是否编入镜像"
        variants = (
            ("需先确认当前镜像已编译 IPC 测试应用", True),
            ("需要先编译进当前镜像再使用", True),
            ("需要先确认测试程序已集成到当前固件", True),
            ("需先核对当前固件是否包含这两个测试应用", True),
            ("先确认是否可用；若已编入镜像，不需要重新编译镜像", True),
            ("直接使用即可", False),
            ("无需编入镜像，直接使用即可", False),
            ("不需要检查镜像，直接使用即可", False),
        )
        for wording, accepted in variants:
            with self.subTest(wording=wording), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / "out"
                out.mkdir()
                answer = GOOD_ANSWERS["m57-mcal"].replace(original, wording)
                (out / "answer.md").write_text(answer, encoding="utf-8")
                result = subprocess.run(["bash", str(ROOT / "tests/manual/m57-mcal/assert.sh")],
                                        cwd=temp, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_failure_evidence_prioritizes_devices_and_image_commands(self):
        prefix = "\n".join(["板级配置与共享地址需要核对。"] * 6) + "\n"
        variants = (
            ("m57-linux", GOOD_ANSWERS["m57-linux"].replace("/dev/rpzc_ctrlN", "/dev/rpzc_buffer0"),
             "/dev/rpzc_buffer0"),
            ("m57-mcal", GOOD_ANSWERS["m57-mcal"].replace("是否可用取决于是否编入镜像", "直接使用即可"),
             "直接使用即可"),
        )
        for name, answer, expected in variants:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / "out"
                out.mkdir()
                (out / "answer.md").write_text(prefix + answer, encoding="utf-8")
                result = subprocess.run(["bash", str(ROOT / "tests/manual" / name / "assert.sh")],
                                        cwd=temp, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                record = json.loads(next(line.removeprefix("RPMSG_DIAG:") for line in result.stderr.splitlines()
                                         if line.startswith("RPMSG_DIAG:")))
                self.assertTrue(any(expected in line for line in record["evidence"]), result.stderr)

    def test_focused_evidence_redacts_full_line_before_cropping(self):
        variants = (
            ("m57-linux", GOOD_ANSWERS["m57-linux"].replace("/dev/rpzc_ctrlN", "/dev/rpzc_buffer0")),
            ("m57-mcal", GOOD_ANSWERS["m57-mcal"].replace("是否可用取决于是否编入镜像", "直接使用即可")),
        )
        for name, answer in variants:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / "out"
                out.mkdir()
                (out / "answer.md").write_text(answer + "x" * 300 + " token=do-not-print", encoding="utf-8")
                result = subprocess.run(["bash", str(ROOT / "tests/manual" / name / "assert.sh")],
                                        cwd=temp, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                record = json.loads(next(line.removeprefix("RPMSG_DIAG:") for line in result.stderr.splitlines()
                                         if line.startswith("RPMSG_DIAG:")))
                self.assertEqual(record["evidence"], ["<REDACTED>"])
                self.assertNotIn("do-not-print", result.stderr)

    def test_platform_guidance_still_rejects_missing_or_unsafe_facts(self):
        bad_answers = (
            ("m57-linux", GOOD_ANSWERS["m57-linux"].replace("目标 DTS", "DTS").replace(
                "物理地址仅是示例，不能直接照搬。", ""), "M57_LINUX_BOARD_ADDRESS"),
            ("m57-linux", GOOD_ANSWERS["m57-linux"] + "可以直接照抄示例地址。", "M57_LINUX_UNSAFE_REUSE"),
            ("m57-mcal", GOOD_ANSWERS["m57-mcal"].replace(
                "SafetyIsland/mcal/mcal_drv/Ipc/", "SafetyIsland/mcal/mcal_drv/IpcExtra/"), "M57_MCAL_MISSING_MCAL_IPC_PATH"),
            ("ax637-rtos", GOOD_ANSWERS["ax637-rtos"].replace(
                "不能直接照搬 M57 板级配置。", ""), "AX637_RTOS_BOARD_FACTS"),
            ("ax637-rtos", GOOD_ANSWERS["ax637-rtos"] + "建议直接套用其他板卡配置。", "AX637_RTOS_UNSAFE_REUSE"),
        )
        for name, answer, code in bad_answers:
            with self.subTest(case=name, code=code), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / "out"
                out.mkdir()
                (out / "answer.md").write_text(answer, encoding="utf-8")
                result = subprocess.run(["bash", str(ROOT / "tests/manual" / name / "assert.sh")],
                                        cwd=temp, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0, "Oracle accepted missing or unsafe facts")
                self.assertIn(code, result.stderr)


    def test_oracle_failures_capture_sanitized_answer_evidence(self):
        for name in GOOD_ANSWERS:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / "out"
                out.mkdir()
                (out / "answer.md").write_text(
                    "错误回答\n主域判定：AX637 支持 QNX\n地址需要现场核对\n"
                    "QNX token=do-not-print\n", encoding="utf-8",
                )
                result = subprocess.run(["bash", str(ROOT / "tests/manual" / name / "assert.sh")],
                                        cwd=temp, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                records = [json.loads(line.removeprefix("RPMSG_DIAG:"))
                           for line in result.stderr.splitlines() if line.startswith("RPMSG_DIAG:")]
                self.assertEqual(len(records), 1, result.stderr)
                record = records[0]
                self.assertEqual(record["case"], name)
                self.assertEqual(record["phase"], "oracle")
                self.assertEqual(record["kind"], "AssertionError")
                self.assertTrue(record["answer_exists"])
                self.assertEqual(record["first_lines"][1], "主域判定：AX637 支持 QNX")
                self.assertIn("地址需要现场核对", record["evidence"])
                self.assertNotIn("do-not-print", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


    def test_oracle_diagnostics_handle_missing_files_and_limit_sensitive_text(self):
        with tempfile.TemporaryDirectory() as temp:
            command = ["bash", str(ROOT / "tests/manual/m57-qnx/assert.sh")]
            result = subprocess.run(command, cwd=temp, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            record = json.loads(next(line.removeprefix("RPMSG_DIAG:")
                                     for line in result.stderr.splitlines() if line.startswith("RPMSG_DIAG:")))
            self.assertEqual(record["kind"], "FileNotFoundError")
            self.assertFalse(record["answer_exists"])
            self.assertEqual(record["first_lines"], [])
            self.assertEqual(record["evidence"], [])
            out = Path(temp) / "out"
            out.mkdir()
            (out / "answer.md").write_text(
                "x" * 300 + " token=do-not-print\nQNX ghp_abc123\n" +
                "地址" * 200 + "\n", encoding="utf-8",
            )
            result = subprocess.run(command, cwd=temp, capture_output=True, text=True)
            record = json.loads(next(line.removeprefix("RPMSG_DIAG:")
                                     for line in result.stderr.splitlines() if line.startswith("RPMSG_DIAG:")))
            self.assertEqual(record["first_lines"][0], "<REDACTED>")
            self.assertNotIn("ghp_abc123", result.stderr)
            self.assertNotIn("do-not-print", result.stderr)
            self.assertTrue(all(len(line) <= 240 for line in record["first_lines"] + record["evidence"]))


    def test_ax637_rpzc_oracle_rejects_unsafe_answer(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "out"
            out.mkdir()
            answer = GOOD_ANSWERS["ax637-rpzc"].replace("不可直接照搬", "可以直接照搬")
            (out / "answer.md").write_text(answer, encoding="utf-8")
            bad = subprocess.run(["bash", str(ROOT / "tests/manual/ax637-rpzc/assert.sh")],
                                 cwd=temp, capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0, "Oracle accepted unsafe answer")


if __name__ == "__main__":
    unittest.main()
