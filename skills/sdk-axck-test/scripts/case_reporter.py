import json
import os
import sys
import time


class CaseReporter:
    """Standardized real-time structured case reporter for CLI and session output.

    Prints per-case details including:
    - Case Name / Index
    - Test Step & Method (步骤与方法)
    - Inputs (parameters, menu command, HTTP payload)
    - Outputs (console return line, JSON response data)
    - Verification Gates (期望值 vs 实际值, /proc gate, FPS, HTTP 200, biz code 0)
    - Result (PASS / FAIL / SKIP)
    - Duration / Latency (ms or s)
    """

    def __init__(self, stream=sys.stdout):
        self.stream = stream
        self.cases = []

    def report_case(
        self,
        suite_name,
        case_name,
        inputs,
        outputs,
        gates,
        status,
        duration,
        step_method=None,
        memory_info=None,
        error_msg=None,
    ):
        """Record and immediately format-print a case test result."""
        case_data = {
            "suite": suite_name,
            "case": case_name,
            "step_method": step_method,
            "inputs": inputs,
            "outputs": outputs,
            "memory": memory_info,
            "gates": gates,
            "status": status,
            "duration": round(duration, 3),
            "error": error_msg,
            "timestamp": time.time(),
        }
        self.cases.append(case_data)

        # Print structured human-readable block immediately
        status_tag = (
            f"[\033[32mPASS\033[0m]"
            if status == "PASS"
            else f"[\033[31mFAIL\033[0m]"
        )

        lines = [
            f"\n{'=' * 80}",
            f"{status_tag} [{suite_name.upper()}] Case: {case_name} (耗时: {case_data['duration']}s)",
            f"{'-' * 80}",
        ]
        if step_method:
            lines.append(f"  • 步骤与方法 (Step & Method) : {step_method}")
        lines.extend([
            f"  • 输入参数 (Inputs)          : {self._format_dict(inputs)}",
            f"  • 响应回显 (Outputs)         : {self._format_dict(outputs)}",
        ])
        if memory_info:
            lines.append(f"  • 内存监控 (Memory Health)   : {self._format_memory(memory_info)}")
        lines.append(f"  • 门限判断 (Gates)           : {self._format_gates(gates)}")
        if error_msg:
            lines.append(f"  • 失败原因 (Error)           : {error_msg}")
        lines.append(f"{'=' * 80}")

        self.stream.write("\n".join(lines) + "\n")
        self.stream.flush()

    def _format_memory(self, mem):
        if not mem or not isinstance(mem, dict):
            return "N/A"
        # mem may contain: cmm_used_kb, cmm_total_kb, cmm_usage_pct, delta_cmm_kb, os_avail_kb, vm_rss_kb, delta_rss_kb
        cmm_used_mb = mem.get("cmm_used_kb", 0) / 1024.0
        cmm_total_mb = mem.get("cmm_total_kb", 0) / 1024.0
        pct = mem.get("cmm_usage_pct", 0.0)
        delta_cmm = mem.get("delta_cmm_kb", 0)
        os_avail_mb = mem.get("os_avail_kb", 0) / 1024.0
        vm_rss_mb = mem.get("vm_rss_kb", 0) / 1024.0
        delta_rss = mem.get("delta_rss_kb", 0)

        delta_cmm_str = f"+{delta_cmm}KB" if delta_cmm >= 0 else f"{delta_cmm}KB"
        delta_rss_str = f"+{delta_rss}KB" if delta_rss >= 0 else f"{delta_rss}KB"

        # Color highlight if leakage or high usage
        cmm_color = "\033[33m" if pct > 85.0 else ""
        end_color = "\033[0m" if pct > 85.0 else ""

        return (
            f"{cmm_color}CMM: {cmm_used_mb:.1f}MB/{cmm_total_mb:.1f}MB ({pct}%){end_color} [ΔCMM: {delta_cmm_str}] | "
            f"OS可用: {os_avail_mb:.1f}MB | "
            f"VmRSS: {vm_rss_mb:.1f}MB [ΔRSS: {delta_rss_str}]"
        )

    def _format_dict(self, d):
        if not d:
            return "None"
        if isinstance(d, dict):
            # If payload is short, format in one line, else compact json
            try:
                s = json.dumps(d, ensure_ascii=False)
                if len(s) < 120:
                    return s
                parts = [f"{k}={v}" for k, v in list(d.items())[:6]]
                if len(d) > 6:
                    parts.append(f"...(+{len(d)-6} items)")
                return ", ".join(parts)
            except Exception:
                return str(d)
        return str(d)

    def _format_gates(self, gates):
        if not gates:
            return "N/A"
        formatted = []
        for name, item in gates.items():
            ok = item.get("passed", False)
            mark = "✓ PASS" if ok else "✗ FAIL"
            desc = item.get("desc", "")
            actual = item.get("actual", "")
            expected = item.get("expected", "")
            formatted.append(
                f"[{mark} | {name}: {desc} (期望: {expected} | 实际: {actual})]"
            )
        return "\n                                  ".join(formatted)

    def get_summary(self):
        total = len(self.cases)
        passed = sum(1 for c in self.cases if c["status"] == "PASS")
        failed = sum(1 for c in self.cases if c["status"] == "FAIL")
        total_duration = sum(c.get("duration", 0.0) for c in self.cases)
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "total_duration": round(total_duration, 3)
        }

    def save_json(self, path):
        summary = self.get_summary()
        payload = {"summary": summary, "cases": self.cases}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def save_junit_xml(self, path):
        """Export test results to standard JUnit XML format for CI/CD integration."""
        import xml.etree.ElementTree as ET
        summary = self.get_summary()
        
        testsuites = ET.Element("testsuites", {
            "name": "AXCK_Test_Suite",
            "tests": str(summary["total"]),
            "failures": str(summary["failed"]),
            "errors": "0",
            "time": str(summary["total_duration"])
        })
        
        # Group cases by suite
        suites = {}
        for c in self.cases:
            s_name = c.get("suite", "default")
            suites.setdefault(s_name, []).append(c)
            
        for s_name, cases in suites.items():
            s_duration = sum(c.get("duration", 0.0) for c in cases)
            s_failures = sum(1 for c in cases if c.get("status") == "FAIL")
            testsuite = ET.SubElement(testsuites, "testsuite", {
                "name": s_name,
                "tests": str(len(cases)),
                "failures": str(s_failures),
                "errors": "0",
                "time": str(round(s_duration, 3))
            })
            for c in cases:
                testcase = ET.SubElement(testsuite, "testcase", {
                    "name": c.get("case", "unknown"),
                    "classname": f"axck.{s_name}",
                    "time": str(c.get("duration", 0.0))
                })
                if c.get("status") == "FAIL":
                    fail_elem = ET.SubElement(testcase, "failure", {
                        "message": str(c.get("error") or "Assertion gates failed"),
                        "type": "AssertionError"
                    })
                    fail_elem.text = json.dumps(c.get("gates", {}), ensure_ascii=False, indent=2)

        tree = ET.ElementTree(testsuites)
        ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)

    def save_html_report(self, path, title="AX615 camera-kit 自动化回归测试报告"):
        """Export self-contained, offline-capable responsive HTML report dashboard."""
        summary = self.get_summary()
        pass_rate = round((summary["passed"] / summary["total"] * 100), 1) if summary["total"] > 0 else 0.0
        status_badge = '<span class="badge pass">ALL PASS (100%)</span>' if summary["failed"] == 0 else f'<span class="badge fail">{summary["failed"]} FAILED</span>'
        
        rows = []
        for idx, c in enumerate(self.cases, 1):
            status = c.get("status", "UNKNOWN")
            status_cls = "pass" if status == "PASS" else "fail"
            gates_html = []
            for g_name, g_val in (c.get("gates") or {}).items():
                g_passed = g_val.get("passed", False)
                g_cls = "gate-pass" if g_passed else "gate-fail"
                g_mark = "✓" if g_passed else "✗"
                gates_html.append(
                    f'<div class="gate-item {g_cls}"><span class="mark">{g_mark}</span> <strong>{g_name}</strong>: {g_val.get("desc", "")} '
                    f'<span class="threshold">(期望: {g_val.get("expected")}, 实际: {g_val.get("actual")})</span></div>'
                )
            gates_rendered = "".join(gates_html) if gates_html else '<span class="text-muted">N/A</span>'
            
            # Format memory
            mem = c.get("memory")
            mem_rendered = '<span class="text-muted">N/A</span>'
            if mem and isinstance(mem, dict):
                cmm_mb = round(mem.get("cmm_used_kb", 0) / 1024.0, 1)
                cmm_tot = round(mem.get("cmm_total_kb", 0) / 1024.0, 1)
                pct = mem.get("cmm_usage_pct", 0.0)
                d_cmm = mem.get("delta_cmm_kb", 0)
                d_cmm_str = f"+{d_cmm}KB" if d_cmm >= 0 else f"{d_cmm}KB"
                os_mb = round(mem.get("os_avail_kb", 0) / 1024.0, 1)
                rss_mb = round(mem.get("vm_rss_kb", 0) / 1024.0, 1)
                mem_rendered = f'CMM: {cmm_mb}/{cmm_tot}MB ({pct}%) [{d_cmm_str}] | OS: {os_mb}MB | RSS: {rss_mb}MB'

            row = f"""
            <tr class="case-row {status_cls}">
                <td class="col-id">{idx}</td>
                <td class="col-suite"><span class="suite-tag">{c.get('suite', '')}</span></td>
                <td class="col-name">
                    <div class="case-title">{c.get('case', '')}</div>
                    <div class="case-method">{c.get('step_method', '') or ''}</div>
                </td>
                <td class="col-status"><span class="badge {status_cls}">{status}</span></td>
                <td class="col-gates">{gates_rendered}</td>
                <td class="col-mem">{mem_rendered}</td>
                <td class="col-time">{c.get('duration', 0.0)}s</td>
            </tr>
            """
            rows.append(row)

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg-color: #0d1117;
            --card-bg: #161b22;
            --border-color: #30363d;
            --text-primary: #c9d1d9;
            --text-secondary: #8b949e;
            --accent-blue: #58a6ff;
            --pass-green: #2ea043;
            --fail-red: #f85149;
            --warn-yellow: #d29922;
        }}
        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 24px;
            font-size: 14px;
        }}
        .container {{
            max-width: 1440px;
            margin: 0 auto;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        h1 {{
            margin: 0;
            font-size: 24px;
            color: #f0f6fc;
        }}
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px;
        }}
        .card-label {{
            color: var(--text-secondary);
            font-size: 13px;
            margin-bottom: 6px;
        }}
        .card-value {{
            font-size: 28px;
            font-weight: 700;
            color: #f0f6fc;
        }}
        .card-value.pass {{ color: var(--pass-green); }}
        .card-value.fail {{ color: var(--fail-red); }}
        .card-value.blue {{ color: var(--accent-blue); }}
        
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge.pass {{ background: rgba(46, 160, 67, 0.2); color: #3fb950; border: 1px solid rgba(46, 160, 67, 0.4); }}
        .badge.fail {{ background: rgba(248, 81, 73, 0.2); color: #f85149; border: 1px solid rgba(248, 81, 73, 0.4); }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            overflow: hidden;
        }}
        th, td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        th {{
            background-color: #21262d;
            color: #f0f6fc;
            font-weight: 600;
            font-size: 13px;
        }}
        tr:hover {{
            background-color: #1c2128;
        }}
        .suite-tag {{
            background: #21262d;
            border: 1px solid var(--border-color);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
            font-family: monospace;
            color: var(--accent-blue);
        }}
        .case-title {{
            font-weight: 600;
            color: #f0f6fc;
            margin-bottom: 4px;
        }}
        .case-method {{
            color: var(--text-secondary);
            font-size: 12px;
        }}
        .gate-item {{
            margin-bottom: 4px;
            font-size: 12px;
        }}
        .gate-pass .mark {{ color: var(--pass-green); font-weight: bold; }}
        .gate-fail .mark {{ color: var(--fail-red); font-weight: bold; }}
        .threshold {{ color: var(--text-secondary); font-size: 11px; }}
        .text-muted {{ color: var(--text-secondary); }}
        .col-time {{ font-family: monospace; white-space: nowrap; }}
        .col-mem {{ font-family: monospace; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>{title}</h1>
                <div style="color: var(--text-secondary); margin-top: 6px;">生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 设备架构: AXERA AX615 (ARMv7 uClibc)</div>
            </div>
            <div>{status_badge}</div>
        </header>

        <div class="summary-cards">
            <div class="card">
                <div class="card-label">总测试用例数</div>
                <div class="card-value blue">{summary['total']}</div>
            </div>
            <div class="card">
                <div class="card-label">通过用例数 (Passed)</div>
                <div class="card-value pass">{summary['passed']}</div>
            </div>
            <div class="card">
                <div class="card-label">失败用例数 (Failed)</div>
                <div class="card-value {'fail' if summary['failed'] > 0 else 'pass'}">{summary['failed']}</div>
            </div>
            <div class="card">
                <div class="card-label">通过率 (Pass Rate)</div>
                <div class="card-value pass">{pass_rate}%</div>
            </div>
            <div class="card">
                <div class="card-label">总执行耗时</div>
                <div class="card-value">{summary['total_duration']}s</div>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th style="width: 40px;">#</th>
                    <th style="width: 120px;">分类</th>
                    <th>测试用例 & 验证方法</th>
                    <th style="width: 80px;">状态</th>
                    <th>判定门限断言 (Verification Gates)</th>
                    <th style="width: 260px;">内存健康监控 (Memory)</th>
                    <th style="width: 70px;">耗时</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
</body>
</html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)
