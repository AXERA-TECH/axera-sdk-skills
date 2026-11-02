import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AssertionTests(unittest.TestCase):
    def result(self, case):
        result = {
            "platform": "unknown", "status": "needs_input", "component": None,
            "event": None, "missing_services": [], "questions": ["请提供首次异常前后的完整日志？"],
            "conclusion": "输入不足，先补带时间戳的日志上下文。", "next_steps": [],
            "evidence": [{"file": "client.md", "quote": "heartbeat timeout"}],
        }
        if case == "fusa-linux-mask":
            result.update(platform="linux", status="diagnosed", component="ISP_PIPE",
                          event={"domain": 0, "module": 45, "event": 17}, questions=[],
                          conclusion="ISP 帧 ID 校验事件，不能只凭 event 17 归为心跳超时。",
                          next_steps=["先确认 ECM/FCU 上报通路与 ISP 自检证据。"],
                          evidence=[{"file": "client.md", "quote": "error_mask: 0x002D0011"}])
        elif case == "fusa-qnx-services":
            result.update(platform="qnx", status="diagnosed", component="FCU", questions=[],
                          missing_services=["fcu_drv"], conclusion="fcu_drv 当前缺失，/proc/ax_diag 已存在。历史故障原因待确认。",
                          next_steps=["保留日志，排查 fcu_drv 退出或未启动的原因，再按既有流程恢复。",
                                      "确认 /dev/fcu 返回并验证 FCU 类上报。"],
                          evidence=[{"file": "client.md", "quote": "QNX_HIT"}])
        return result

    def check_result(self, case, result):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            shutil.copy2(ROOT / "evals/cases" / case / "fixtures/client.md", work / "client.md")
            (work / "out").mkdir()
            (work / "out/result.json").write_text(json.dumps(result, ensure_ascii=False))
            (work / "out/result.md").write_text(result["conclusion"] + "\n" + "\n".join(result["next_steps"]))
            return subprocess.run(["bash", str(ROOT / "evals/cases" / case / "assert.sh")],
                                  cwd=work, capture_output=True, text=True)

    def test_supported_conclusions_pass(self):
        for case in ("fusa-linux-mask", "fusa-qnx-services", "fusa-input-gate"):
            with self.subTest(case=case):
                process = self.check_result(case, self.result(case))
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_wrong_module_is_rejected(self):
        result = self.result("fusa-linux-mask")
        result["event"]["module"] = 0
        self.assertNotEqual(self.check_result("fusa-linux-mask", result).returncode, 0)

    def test_missing_fcu_diagnosis_is_rejected(self):
        result = self.result("fusa-qnx-services")
        result["missing_services"] = []
        self.assertNotEqual(self.check_result("fusa-qnx-services", result).returncode, 0)

    def test_guessed_platform_or_attribution_is_rejected(self):
        for field, value in (("platform", "qnx"), ("component", "AXDIAG"),
                             ("event", {"domain": 0, "module": 0, "event": 17})):
            result = self.result("fusa-input-gate")
            result[field] = value
            self.assertNotEqual(self.check_result("fusa-input-gate", result).returncode, 0)

    def test_equivalent_symbol_and_unspecified_event_module_pass(self):
        for case, component in (("fusa-linux-mask", "ISP_PIPE_ISP_PIPE_FRAME_ID_CHECK"),
                                ("fusa-linux-mask", "AX_MAIN_BSP_ISP_PIPE_ISP_PIPE_FRAME_ID_CHECK"),
                                ("fusa-qnx-services", None),
                                ("fusa-qnx-services", "AX_MCAL_CDD_FCU_SAFETY")):
            result = self.result(case)
            result["component"] = component
            process = self.check_result(case, result)
            self.assertEqual(process.returncode, 0, process.stderr)

    def test_multiple_questions_and_readonly_platform_probe_pass(self):
        result = self.result("fusa-input-gate")
        result["questions"] = ["请提供 SDK 路径以确认平台？", "请提供完整日志？"]
        result["next_steps"] = ["用于判定平台：ls -d /sys/devices/platform/axdiag /proc/ax_diag"]
        process = self.check_result("fusa-input-gate", result)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_early_build_or_configuration_change_is_rejected(self):
        for command in ("make all", "echo 1 > /sys/class/fusa/fcu/reset"):
            result = self.result("fusa-input-gate")
            result["next_steps"] = [command]
            self.assertNotEqual(self.check_result("fusa-input-gate", result).returncode, 0)

    def test_invented_evidence_is_rejected(self):
        result = self.result("fusa-linux-mask")
        result["evidence"][0]["quote"] = "not present in this input"
        self.assertNotEqual(self.check_result("fusa-linux-mask", result).returncode, 0)

    def test_wrapped_evidence_quote_passes(self):
        result = self.result("fusa-input-gate")
        client = (ROOT / "evals/cases/fusa-input-gate/fixtures/client.md").read_text()
        result["evidence"][0]["quote"] = client[client.index("客户只发了这一句话。"):].replace("\n", "")
        process = self.check_result("fusa-input-gate", result)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_remaining_root_cause_uncertainty_is_allowed(self):
        for case in ("fusa-linux-mask", "fusa-qnx-services", "fusa-input-gate"):
            result = self.result(case)
            result["status"] = "inconclusive"
            process = self.check_result(case, result)
            self.assertEqual(process.returncode, 0, process.stderr)

    def test_fixtures_track_original_inputs_with_neutral_workspace_paths(self):
        cases = {"fusa-linux-mask": "FUSA-002", "fusa-qnx-services": "FUSA-007", "fusa-input-gate": "FUSA-005"}
        for case, source in cases.items():
            text = (ROOT / "evals/cases" / case / "fixtures/client.md").read_text()
            for path in (ROOT / "evals" / source / "input").iterdir():
                original = path.read_text()
                self.assertIn(original.rstrip("\n"), text)


if __name__ == "__main__":
    unittest.main()
