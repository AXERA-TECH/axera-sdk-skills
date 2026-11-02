import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from render_hsk_html import DEFAULT_OUTPUT_DIR, render, write_report

FIXTURE = ROOT / "tests" / "fixtures" / "hsk_proc_single_sample.txt"
SAMPLE = FIXTURE.read_text(encoding="utf-8")


def offline_samples():
    """S2 推进 fixture 里 grp0/chn2/flt5 的输出、但不动 venc chn2 -> link_dispatch_drop。"""
    lines = SAMPLE.splitlines()
    lines[95] = lines[95].replace("VGP    2003984    0     0     2003984    2003984",
                                  "VGP    2004084    0     0     2004084    2004084")
    return ("===== SAMPLE 1 =====\n" + SAMPLE +
            "===== SAMPLE 2 =====\n" + "\n".join(lines) + "\n")


class RenderHskHtmlTest(unittest.TestCase):
    def test_writes_self_contained_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_report({"title": "测试报告", "conclusion": "形态待确认",
                                 "summary": "HSK形态：一对一",
                                 "next_step": "补采第二轮"},
                                output_dir=directory, filename="report.html")
            content = path.read_text(encoding="utf-8")
            self.assertEqual(path.name, "report.html")
            self.assertIn("测试报告", content)
            self.assertNotIn("寄存器采集", content)
            self.assertIn("补采第二轮", content)
            self.assertNotIn("<script", content)

    def test_renders_parsed_proc_facts(self):
        parsed = __import__("parse_hsk_proc").parse(SAMPLE)
        content = render({"conclusion": "见下"}, parsed, "fixture.txt")
        self.assertIn("一对一", content)
        self.assertIn("二对一", content)
        self.assertIn('data-label="握手高度"', content)
        self.assertIn("未采集 link_table_kernel", content)
        self.assertIn("只有一轮采样", content)

    def test_defaults_to_concise_and_renders_coverage_only_in_detail(self):
        # 默认简洁：只给结论、问题与证据表；解析范围等支撑材料留到 --detail。
        parsed = __import__("parse_hsk_proc").parse(SAMPLE)
        concise = render({"conclusion": "见下"}, parsed)
        self.assertIn("简洁", concise)
        self.assertNotIn("<h2>解析范围</h2>", concise)
        detail = render({"conclusion": "见下"}, parsed, detail=True)
        self.assertIn("详细", detail)
        self.assertIn("<h2>解析范围</h2>", detail)
        # 详细模式也只附分析 JSON：解析结果已经渲染成表，整份内联会让页面多出上百 KB。
        self.assertIn("查看分析 JSON", detail)
        self.assertNotIn("&quot;samples&quot;", detail)

    def test_renders_no_none_literals(self):
        # fixture 没有 kernel 表，拓扑表里应如实标注 Engine 未采集，而不是留空。
        parsed = __import__("parse_hsk_proc").parse(SAMPLE)
        content = render({}, parsed)
        self.assertNotIn(">None<", content)

    def test_warns_when_single_sample_cannot_confirm_stall(self):
        parsed = __import__("parse_hsk_proc").parse(SAMPLE)
        content = render({}, parsed)
        self.assertIn("持续卡死结论需要第二次采样确认", content)

    def test_issue_level_controls_report_state(self):
        parsed = __import__("parse_hsk_proc").parse(SAMPLE)
        content = render({}, parsed)
        # fixture 只有 `提示` 级问题（缺少 link_table_kernel），整体状态是需关注。
        self.assertIn('class="report state-warning"', content)
        self.assertIn("需要关注", content)

    def test_accepts_structured_summary(self):
        content = render({"summary": [{"label": "HSK形态", "text": "一对二"}]}, None)
        self.assertIn("<h3>HSK形态</h3><p>一对二</p>", content)

    def test_renders_without_parse(self):
        content = render({"conclusion": "仅结论文本"})
        self.assertIn("未提供 proc 文本", content)
        self.assertIn('class="report state-ok"', content)

    def test_escapes_analysis_content(self):
        content = render({"title": "<img src=x onerror=alert(1)>"}, None)
        self.assertNotIn("<img src=x", content)
        self.assertIn("&lt;img src=x", content)

    def test_renders_offline_link_section(self):
        parsed = __import__("parse_hsk_proc").parse(offline_samples())
        content = render({}, parsed)
        self.assertIn("<h3>Offline 链路</h3>", content)
        self.assertIn('<span class="snapshot-label">Offline 链路</span>', content)
        # 静态快照只渲染最新一轮，不再按轮次各来一份；两次采集只为 S1 → S2 差值服务。
        self.assertEqual(content.count("<h3>HSK 形态</h3>"), 1)
        self.assertNotIn("SAMPLE 1 · ", content)
        self.assertIn("两次采集只为「跨采样差值」服务", content)
        self.assertIn("2 轮 · SAMPLE 1 / SAMPLE 2", content)
        # fixture 的 SW_Offline 链路应判成 link_dispatch_drop 并带上 danger 级徽标。
        self.assertIn('badge-danger">link_dispatch_drop</span>', content)
        self.assertIn("IVPS 0/2", content)
        # 帧率配置要出现在上下游单元格里，低 OutFps 才能和配置区分开。
        self.assertIn("抽帧 RATIO", content)
        self.assertIn("码控 CBR", content)

    def test_offline_section_empty_without_proc(self):
        # 与其他章节一致：无 proc 时保留章节与空态，但不出现任何判定表。
        content = render({})
        self.assertIn("<h2>支撑快照</h2>", content)
        self.assertNotIn("数据流判定", content)

    def test_default_output_dir_is_skill_reports(self):
        self.assertEqual(DEFAULT_OUTPUT_DIR, ROOT / "reports")
        self.assertTrue(DEFAULT_OUTPUT_DIR.is_dir())


if __name__ == "__main__":
    unittest.main()
