#!/usr/bin/env python3
"""Render a structured AX615 RC audit result as a self-contained HTML report."""
import argparse
import html
import json
from datetime import datetime
from pathlib import Path


def esc(value):
    return html.escape("" if value is None else str(value))


def cell(value):
    if isinstance(value, (dict, list)):
        return esc(json.dumps(value, ensure_ascii=False))
    return esc(value)


def present(value):
    return value not in (None, "", "-")


def first_present(*values):
    return next((value for value in values if present(value)), "-")


def with_unit(value, unit):
    return f"{value} {unit}" if present(value) else "-"


def rate_label(rc):
    mode = str(rc.get("RcMode", "")).upper()
    if mode == "CBR":
        name = "Target"
        value = first_present(rc.get("TargetBitRate"), rc.get("MaxBitRate"))
    else:
        name = "Max"
        value = first_present(rc.get("MaxBitRate"), rc.get("TargetBitRate"))
    return name, value


def qp_range(rc, minimum, maximum):
    low = rc.get(minimum)
    high = rc.get(maximum)
    if not present(low) and not present(high):
        return "-"
    return f"{first_present(low)}–{first_present(high)}"


def qp_delta_range(channel):
    """QpDltRng 列的两种形态：两列 Min/Max，或单列（仅 Max，Min 未知）。"""
    rc = channel.get("rc", {})
    shape = rc.get("QpDltRngShape")
    if shape == "min_max":
        return (f"Min {first_present(rc.get('QpDltRngMin'))} / "
                f"Max {first_present(rc.get('QpDltRngMax'))}")
    if shape == "single":
        return f"Max {first_present(rc.get('QpDltRng'))}（Min 未知）"
    return "-"


def qp_intervention(channel):
    """One-line summary of the QP overlays stacked on top of the RC mode."""
    parts = []
    qpmap = channel.get("qpmap") or {}
    names = {"map1": "QPMAP1", "map2": "QPMAP2", "local_map": "LocalMap"}
    active = [names[key] for key in ("map1", "map2", "local_map") if key in qpmap]
    if active:
        parts.append("/".join(active))
    svc = channel.get("svc_param") or {}
    if svc:
        kind = "绝对" if svc.get("AbsQp") == "Y" else "相对"
        types = svc.get("types") or []
        detail = "，".join(
            f"TYPE{entry.get('TypeId')} {entry.get('IQp')}/{entry.get('PQp')}"
            for entry in types if present(entry.get("TypeId"))
        )
        summary = (f"智能编码（{kind} QP）背景 {svc.get('BgIQp')}/{svc.get('BgPQp')}"
                   f"，{first_present(svc.get('TypeNum'))} 类")
        parts.append(summary + ("：" + detail if detail else ""))
    regions = channel.get("svc_region") or []
    if regions:
        counts = "、".join(str(item.get("RectNum")) for item in regions)
        parts.append(f"区域数 {counts}")
    return "<br>".join(esc(part) for part in parts) or "-"


def level_key(level):
    normalized = str(level or "信息").strip().lower()
    if normalized in {"错误", "高风险", "error", "danger", "critical"}:
        return "danger"
    if normalized in {"提示", "警告", "warning", "warn", "关注", "需调整", "调整"}:
        return "warning"
    return "info"


def overall_state(issues):
    keys = {level_key(issue.get("level")) for issue in issues}
    if "danger" in keys:
        return "danger", "存在异常"
    if "warning" in keys:
        return "warning", "需要关注"
    return "ok", "配置正常"


def render_paragraphs(value):
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    return "".join(f"<p>{esc(line)}</p>" for line in lines) or '<p class="empty">暂无说明</p>'


def summary_entries(value):
    if isinstance(value, dict):
        return [(str(label), str(text)) for label, text in value.items()]
    if isinstance(value, list):
        entries = []
        for item in value:
            if isinstance(item, dict):
                entries.append((str(item.get("label", "概览")), str(item.get("text", ""))))
            else:
                entries.append(("概览", str(item)))
        return entries

    entries = []
    for line in (line.strip() for line in str(value or "").splitlines()):
        if not line:
            continue
        separator = "：" if "：" in line else ":" if ":" in line else None
        if separator:
            label, text = line.split(separator, 1)
            entries.append((label.strip(), text.strip()))
        else:
            entries.append(("概览", line))
    return entries


def render_summary(value):
    entries = summary_entries(value)
    if not entries:
        return '<div class="empty-state">暂无摘要</div>'
    return '<div class="summary-list">' + "".join(
        f'<article class="summary-item"><h3>{esc(label)}</h3><p>{esc(text)}</p></article>'
        for label, text in entries
    ) + "</div>"


def render(data):
    title = data.get("title", "AX615 码控审查报告")
    conclusion = data.get("conclusion", "")
    summary = data.get("summary", "")
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    channels = data.get("channels", [])
    issues = data.get("issues", [])
    suggestions = data.get("suggestions", [])
    next_step = data.get("next_step", "")
    source = data.get("source", "/proc/ax_proc/venc")
    sdk_version = data.get("sdk_version") or (data.get("environment") or {}).get("sdk_version") or "未知"
    state_key, state_label = overall_state(issues)
    warning_count = sum(level_key(issue.get("level")) == "warning" for issue in issues)
    danger_count = sum(level_key(issue.get("level")) == "danger" for issue in issues)

    channel_rows = []
    for channel in channels:
        rc = channel.get("rc", {})
        status = channel.get("status", {})
        gop = channel.get("gop", {})
        jpeg_rc = channel.get("jpeg_rc", {})
        mode = first_present(rc.get("RcMode"), jpeg_rc.get("RcMode"))
        rate_name, rate_value = rate_label(rc)
        resolution = f"{channel.get('width', '-')} × {channel.get('height', '-')}"
        configured_fps = f"{first_present(rc.get('SrcFr'))} → {first_present(rc.get('DstFr'))}"
        observed_fps = f"{first_present(status.get('recv_fps'))} → {first_present(status.get('out_fps'))}"
        qp = f"P {qp_range(rc, 'MinQp', 'MaxQp')} · I {qp_range(rc, 'MinIQp', 'MaxIQp')}"
        assessment = channel.get("assessment", "正常")
        assessment_key = level_key(assessment)
        if assessment_key == "info":
            assessment_key = "ok"
        values = [
            ("通道", f'<span class="channel-id">CH {cell(channel.get("id"))}</span>'),
            ("编码", f'<strong>{cell(channel.get("codec"))}</strong><span class="subvalue">{cell(channel.get("profile", ""))}</span>'),
            ("分辨率", f'<span class="mono">{cell(resolution)}</span>'),
            ("模式", f'<strong>{cell(mode)}</strong>'),
            ("配置帧率", f'<span class="mono">{cell(configured_fps)}</span><span class="subvalue">Src → Dst</span>'),
            ("GOP", f'<span class="mono">{cell(gop.get("gop", "-"))}</span>'),
            ("码率配置", f'<span class="mono">{cell(with_unit(rate_value, "kbps"))}</span><span class="subvalue">{rate_name}</span>'),
            ("实测帧率", f'<span class="mono">{cell(observed_fps)}</span><span class="subvalue">RecvFps → OutFps</span>'),
            ("当前码率", f'<span class="mono emphasis">{cell(with_unit(status.get("bitrate_kbps"), "kbps"))}</span>'),
            ("QP 范围", f'<span class="mono">{cell(qp)}</span>'),
            ("QP 局部调节", f'<span class="mono">{cell(qp_delta_range(channel))}</span>'),
            ("QP 干预", f'<span class="mono">{qp_intervention(channel)}</span>'),
            ("判断", f'<span class="badge badge-{assessment_key}">{cell(assessment)}</span>'),
        ]
        channel_rows.append("<tr>" + "".join(
            f'<td data-label="{esc(label)}">{value}</td>' for label, value in values
        ) + "</tr>")

    issue_items = []
    for issue in issues:
        level = issue.get("level", "信息")
        key = level_key(level)
        issue_items.append(
            f'<article class="issue issue-{key}">'
            f'<div class="issue-signal" aria-hidden="true"></div>'
            f'<div class="issue-heading"><span class="badge badge-{key}">{cell(level)}</span>'
            f'<span class="issue-channel">CH {cell(issue.get("channel"))}</span>'
            f'<strong>{cell(issue.get("field"))}</strong></div>'
            f'<p>{cell(issue.get("message", issue.get("reason")))}</p>'
            f'</article>'
        )

    suggestion_items = "".join(
        f'<li><span>{cell(item)}</span></li>' for item in suggestions
    )
    details = html.escape(json.dumps(data, ensure_ascii=False, indent=2))
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
:root {{
  color-scheme: light;
  --canvas: #f2f4f7;
  --paper: #ffffff;
  --ink: #18212b;
  --muted: #667085;
  --line: #dfe3e8;
  --line-strong: #c7cdd4;
  --ok: #16735f;
  --ok-soft: #e8f5f1;
  --warning: #9a5b00;
  --warning-soft: #fff3d6;
  --danger: #b42318;
  --danger-soft: #fdeceb;
  --info: #2864a5;
  --info-soft: #eaf2fb;
  font-family: "Noto Sans CJK SC", "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
  color: var(--ink);
  background: var(--canvas);
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; line-height: 1.62; }}
.report {{ width: min(1180px, calc(100% - 40px)); margin: 32px auto; background: var(--paper); border: 1px solid var(--line-strong); box-shadow: 0 12px 34px rgba(24,33,43,.08); }}
.report-header {{ display: grid; grid-template-columns: 10px 1fr; min-height: 184px; border-bottom: 1px solid var(--line); }}
.signal-rail {{ background: var(--ok); }}
.state-warning .signal-rail {{ background: var(--warning); }}
.state-danger .signal-rail {{ background: var(--danger); }}
.header-main {{ padding: 32px 38px 28px; }}
.kicker {{ margin: 0 0 8px; color: var(--muted); font: 700 12px/1.3 ui-monospace, SFMono-Regular, Consolas, monospace; text-transform: uppercase; }}
h1 {{ margin: 0; font-family: "Arial Narrow", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; font-size: 36px; line-height: 1.2; font-weight: 760; letter-spacing: 0; }}
.verdict {{ display: flex; align-items: flex-start; gap: 12px; margin-top: 20px; }}
.verdict p {{ margin: 0; max-width: 920px; font-size: 17px; }}
.meta-bar {{ display: flex; flex-wrap: wrap; gap: 12px 24px; padding: 13px 38px; border-bottom: 1px solid var(--line); background: #fafbfc; color: var(--muted); font-size: 12px; }}
.meta-bar span {{ display: inline-flex; gap: 7px; align-items: center; }}
.meta-label {{ color: #344054; font-weight: 700; }}
.snapshot {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-bottom: 1px solid var(--line); }}
.snapshot-item {{ min-height: 92px; padding: 19px 24px; border-right: 1px solid var(--line); }}
.snapshot-item:last-child {{ border-right: 0; }}
.snapshot-value {{ display: block; font: 700 24px/1.2 ui-monospace, SFMono-Regular, Consolas, monospace; }}
.snapshot-label {{ display: block; margin-top: 7px; color: var(--muted); font-size: 12px; }}
.section {{ padding: 30px 38px 34px; border-bottom: 1px solid var(--line); }}
.section:last-child {{ border-bottom: 0; }}
.section-heading {{ display: flex; align-items: baseline; justify-content: space-between; gap: 18px; margin-bottom: 18px; }}
h2 {{ margin: 0; font-size: 19px; line-height: 1.35; letter-spacing: 0; }}
.section-note {{ color: var(--muted); font-size: 12px; }}
.summary-list {{ border: 1px solid var(--line-strong); }}
.summary-item {{ display: grid; grid-template-columns: 132px minmax(0, 1fr); min-width: 0; border-bottom: 1px solid var(--line); }}
.summary-item:last-child {{ border-bottom: 0; }}
.summary-item h3 {{ margin: 0; padding: 17px 18px; color: #344054; background: #f7f8fa; border-right: 1px solid var(--line); font-size: 13px; line-height: 1.55; letter-spacing: 0; }}
.summary-item p {{ min-width: 0; margin: 0; padding: 17px 20px; color: #344054; overflow-wrap: anywhere; }}
.table-wrap {{ overflow-x: auto; border: 1px solid var(--line); }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ padding: 11px 12px; text-align: left; color: #475467; background: #f7f8fa; border-bottom: 1px solid var(--line-strong); font-size: 11px; white-space: nowrap; }}
td {{ padding: 14px 12px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); white-space: nowrap; }}
tbody tr:last-child td {{ border-bottom: 0; }}
tbody tr:hover {{ background: #fbfcfd; }}
.channel-id {{ font: 700 12px/1.4 ui-monospace, SFMono-Regular, Consolas, monospace; }}
.mono {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-variant-numeric: tabular-nums; }}
.emphasis {{ font-weight: 700; }}
.subvalue {{ display: block; margin-top: 2px; color: var(--muted); font-size: 10px; }}
.badge {{ display: inline-flex; min-height: 24px; align-items: center; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 750; white-space: nowrap; }}
.badge-ok {{ color: var(--ok); background: var(--ok-soft); }}
.badge-warning {{ color: var(--warning); background: var(--warning-soft); }}
.badge-danger {{ color: var(--danger); background: var(--danger-soft); }}
.badge-info {{ color: var(--info); background: var(--info-soft); }}
.issues {{ border-top: 1px solid var(--line); }}
.issue {{ position: relative; display: grid; grid-template-columns: 4px 1fr; column-gap: 17px; padding: 18px 0; border-bottom: 1px solid var(--line); }}
.issue:last-child {{ border-bottom: 0; }}
.issue-signal {{ grid-row: 1 / span 2; width: 4px; min-height: 100%; background: var(--info); }}
.issue-warning .issue-signal {{ background: var(--warning); }}
.issue-danger .issue-signal {{ background: var(--danger); }}
.issue-heading {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px 11px; min-width: 0; }}
.issue-channel {{ color: var(--muted); font: 700 11px/1.4 ui-monospace, SFMono-Regular, Consolas, monospace; }}
.issue p {{ grid-column: 2; margin: 7px 0 0; color: #475467; }}
.empty-state {{ padding: 20px 0; color: var(--ok); font-weight: 650; }}
.actions {{ margin: 0; padding: 0; list-style: none; counter-reset: action; border-top: 1px solid var(--line); }}
.actions li {{ display: grid; grid-template-columns: 34px 1fr; gap: 12px; padding: 16px 0; border-bottom: 1px solid var(--line); counter-increment: action; }}
.actions li::before {{ content: counter(action); display: grid; width: 28px; height: 28px; place-items: center; color: var(--info); background: var(--info-soft); border-radius: 50%; font: 750 12px/1 ui-monospace, SFMono-Regular, Consolas, monospace; }}
.actions li:last-child {{ border-bottom: 0; }}
.next-step {{ padding: 18px 20px; border-left: 4px solid var(--info); background: #f7faff; }}
.next-step p {{ margin: 0; }}
.next-step p + p {{ margin-top: 6px; }}
details {{ margin-top: 20px; border-top: 1px solid var(--line); }}
summary {{ padding: 15px 0 0; color: var(--info); cursor: pointer; font-size: 13px; font-weight: 700; }}
summary:focus-visible {{ outline: 3px solid #93b9e2; outline-offset: 4px; }}
pre {{ max-height: 460px; overflow: auto; margin: 14px 0 0; padding: 16px; color: #e8edf2; background: #202932; border-radius: 4px; font: 12px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; }}
@media (max-width: 840px) {{
  .report {{ width: 100%; margin: 0; border-width: 0; box-shadow: none; }}
  .header-main, .section {{ padding-left: 20px; padding-right: 20px; }}
  .meta-bar {{ padding-left: 20px; padding-right: 20px; }}
  .snapshot {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .snapshot-item:nth-child(2) {{ border-right: 0; }}
  .snapshot-item:nth-child(-n+2) {{ border-bottom: 1px solid var(--line); }}
  .table-wrap {{ overflow: visible; border: 0; }}
  table, tbody, tr, td {{ display: block; width: 100%; }}
  thead {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }}
  tbody {{ display: grid; gap: 14px; }}
  tbody tr {{ border: 1px solid var(--line-strong); }}
  td {{ display: grid; grid-template-columns: minmax(92px, 36%) 1fr; gap: 12px; padding: 10px 12px; border-bottom: 1px solid var(--line); white-space: normal; }}
  td::before {{ content: attr(data-label); color: var(--muted); font-size: 11px; font-weight: 700; }}
  tbody tr:hover {{ background: transparent; }}
  .summary-item {{ grid-template-columns: 112px minmax(0, 1fr); }}
}}
@media (max-width: 480px) {{
  .report-header {{ min-height: 0; }}
  .header-main {{ padding-top: 24px; padding-bottom: 24px; }}
  .verdict {{ flex-direction: column; }}
  h1 {{ font-size: 27px; }}
  .snapshot {{ grid-template-columns: 1fr 1fr; }}
  .snapshot-item {{ min-height: 80px; padding: 15px 16px; }}
  .snapshot-value {{ font-size: 20px; }}
  .section-heading {{ display: block; }}
  .section-note {{ display: block; margin-top: 4px; }}
  .summary-item {{ display: block; }}
  .summary-item h3 {{ padding: 10px 14px; border-right: 0; border-bottom: 1px solid var(--line); }}
  .summary-item p {{ padding: 14px; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior: auto !important; }} }}
@media print {{
  :root {{ --canvas: #fff; }}
  .report {{ width: 100%; margin: 0; border: 0; box-shadow: none; }}
  details {{ display: none; }}
  tbody tr {{ break-inside: avoid; }}
}}
</style>
</head>
<body>
<main class="report state-{state_key}">
  <header class="report-header">
    <div class="signal-rail" aria-hidden="true"></div>
    <div class="header-main">
      <p class="kicker">AX615 · VENC RATE CONTROL AUDIT</p>
      <h1>{esc(title)}</h1>
      <div class="verdict"><span class="badge badge-{state_key}">{state_label}</span><p>{esc(conclusion)}</p></div>
    </div>
  </header>
  <div class="meta-bar"><span><b class="meta-label">数据源</b><code>{esc(source)}</code></span><span><b class="meta-label">SDK 版本</b><code>{esc(sdk_version)}</code></span><span><b class="meta-label">生成时间</b><time>{generated}</time></span></div>
  <div class="snapshot" aria-label="审查概览">
    <div class="snapshot-item"><span class="snapshot-value">{len(channels)}</span><span class="snapshot-label">编码通道</span></div>
    <div class="snapshot-item"><span class="snapshot-value">{danger_count}</span><span class="snapshot-label">错误 / 高风险</span></div>
    <div class="snapshot-item"><span class="snapshot-value">{warning_count}</span><span class="snapshot-label">需关注项</span></div>
    <div class="snapshot-item"><span class="snapshot-value">{len(suggestions)}</span><span class="snapshot-label">调整建议</span></div>
  </div>
  <section class="section">
    <div class="section-heading"><h2>配置摘要</h2><span class="section-note">每个通道与运行状态独立展示</span></div>
    {render_summary(summary)}
  </section>
  <section class="section">
    <div class="section-heading"><h2>通道对照</h2><span class="section-note">帧率格式：输入 → 输出</span></div>
    <div class="table-wrap"><table><thead><tr><th>通道</th><th>编码</th><th>分辨率</th><th>模式</th><th>配置帧率</th><th>GOP</th><th>码率配置</th><th>实测帧率</th><th>当前码率</th><th>QP 范围</th><th>QP 干预</th><th>判断</th></tr></thead><tbody>{''.join(channel_rows) or '<tr><td data-label="通道" colspan="12">无通道数据</td></tr>'}</tbody></table></div>
  </section>
  <section class="section">
    <div class="section-heading"><h2>问题与依据</h2><span class="section-note">按风险等级排列</span></div>
    <div class="issues">{''.join(issue_items) or '<div class="empty-state">未发现已记录问题</div>'}</div>
  </section>
  <section class="section">
    <div class="section-heading"><h2>修改建议</h2><span class="section-note">先确认目标，再调整参数</span></div>
    <ol class="actions">{suggestion_items or '<li><span>保持当前配置</span></li>'}</ol>
  </section>
  <section class="section">
    <div class="section-heading"><h2>下一步</h2></div>
    <div class="next-step">{render_paragraphs(next_step)}</div>
    <details><summary>查看规范化数据</summary><pre>{details}</pre></details>
  </section>
</main>
</body>
</html>'''


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "reports"


def write_report(data, output_dir=DEFAULT_OUTPUT_DIR, filename=None):
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if not filename:
        filename = "ax615-rc-audit-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".html"
    path = directory / filename
    path.write_text(render(data), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="-", help="分析 JSON，默认 stdin")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="报告输出目录，默认 <skill>/reports")
    parser.add_argument("--filename")
    args = parser.parse_args()
    raw = __import__("sys").stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    path = write_report(json.loads(raw), args.output_dir, args.filename)
    print(f"HTML_REPORT={path}")
    print(f"HTML_REPORT_DIR={path.parent}")


if __name__ == "__main__":
    main()
