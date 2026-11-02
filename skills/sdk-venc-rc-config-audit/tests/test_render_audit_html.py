import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render_audit_html
from render_audit_html import DEFAULT_OUTPUT_DIR, write_report


class RenderHtmlTest(unittest.TestCase):
    def test_writes_self_contained_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_report({
                "title": "测试报告",
                "conclusion": "正常",
                "summary": "H264 CBR",
                "channels": [{"id": 0, "codec": "H264", "width": 1280, "height": 720,
                              "rc": {"RcMode": "CBR", "SrcFr": 30, "DstFr": 30,
                                     "TargetBitRate": 1024},
                              "gop": {"gop": 60},
                              "status": {"recv_fps": 30, "out_fps": 30, "bitrate_kbps": 1024}}],
                "issues": [], "suggestions": ["保持当前配置"], "next_step": ""
            }, directory, "report.html")
            content = path.read_text(encoding="utf-8")
            self.assertEqual(path.name, "report.html")
            self.assertIn("测试报告", content)
            self.assertIn("RecvFps", content)
            self.assertIn("保持当前配置", content)
            self.assertIn('class="report state-ok"', content)
            self.assertIn('data-label="当前码率"', content)

    def test_uses_max_bitrate_for_cvbr_placeholder_target(self):
        content = __import__("render_audit_html").render({
            "channels": [{
                "id": 0,
                "codec": "H264",
                "rc": {
                    "RcMode": "CVBR",
                    "TargetBitRate": "-",
                    "MaxBitRate": 2048,
                },
            }],
            "issues": [{"level": "提示", "channel": 0, "field": "ltMaxBr", "message": "核对目标"}],
        })
        self.assertIn("2048 kbps", content)
        self.assertIn("state-warning", content)
        self.assertIn("需要关注", content)
        self.assertNotIn(">- kbps<", content)

    def test_renders_summary_as_separate_labeled_rows(self):
        content = __import__("render_audit_html").render({
            "summary": "通道 0：H264 CVBR，2048 kbps\n通道 1：H264 CBR，400 kbps\n帧率状态：两路均为 29.8 fps",
        })
        self.assertEqual(content.count('class="summary-item"'), 3)
        self.assertIn("<h3>通道 0</h3><p>H264 CVBR，2048 kbps</p>", content)
        self.assertIn("<h3>帧率状态</h3>", content)

    def test_accepts_structured_summary(self):
        content = __import__("render_audit_html").render({
            "summary": [{"label": "通道 0", "text": "CVBR 配置"}],
        })
        self.assertIn("<h3>通道 0</h3><p>CVBR 配置</p>", content)

    def test_marks_channel_adjustment_as_warning(self):
        content = __import__("render_audit_html").render({
            "channels": [{"id": 0, "assessment": "需调整"}],
        })
        self.assertIn('badge badge-warning">需调整</span>', content)

    def test_default_output_dir_is_skill_reports(self):
        self.assertEqual(DEFAULT_OUTPUT_DIR, ROOT / "reports")
        self.assertTrue(DEFAULT_OUTPUT_DIR.is_dir())


if __name__ == "__main__":
    unittest.main()
