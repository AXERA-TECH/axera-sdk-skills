"""Exercise evaluator assertions with synthetic model answers."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AssertionTests(unittest.TestCase):
    def check_answer(self, case_id, answer, expected_pass):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            output.mkdir()
            (output / "result.md").write_text(answer, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(ROOT / "evals" / "cases" / case_id / "assert.sh")],
                cwd=directory, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode == 0, expected_pass, result.stderr)

    def test_platform_answers(self):
        for case_id, os_name in (
            ("can-001-m57-linux-mcal", "Linux"),
            ("can-002-m57-qnx-mcal", "QNX"),
        ):
            answer = (
                "结论：支持\n判断依据：M57 " + os_name + " Safety AUTOSAR MCAL CAN。\n"
                "本场景不属于 AX637/AX637R 排除项。\n"
            )
            with self.subTest(case=case_id, scenario="exclusions"):
                self.check_answer(case_id, answer, True)
            with self.subTest(case=case_id, scenario="wrong OS reason"):
                self.check_answer(case_id, answer + "因为" + os_name + "所以不支持。\n", False)
            with self.subTest(case=case_id, scenario="wrong conclusion"):
                self.check_answer(case_id, answer.replace("结论：支持", "结论：不支持"), False)

    def test_inconclusive_answers(self):
        case_id = "can-004-m57-busoff-inconclusive"
        answer = "结论：证据不足\n待补：日志、生成配置、错误计数。\n"
        for suffix in ("", "根因：证据不足\n", "根因： 无法确认\n"):
            with self.subTest(suffix=suffix):
                self.check_answer(case_id, answer + suffix, True)
        for suffix in ("根因： 终端电阻异常\n", "根因是终端电阻异常\n"):
            with self.subTest(suffix=suffix):
                self.check_answer(case_id, answer + suffix, False)
        self.check_answer(case_id, answer.replace("结论：证据不足", "结论：支持"), False)
        self.check_answer(case_id, "结论：证据不足\n待补：日志。\n", False)


if __name__ == "__main__":
    unittest.main()
