#!/usr/bin/env python3
"""把 IVPS→VENC 诊断结果渲染成自包含的 HTML 报告。

分两部分输入：

- `--analysis`：分析结论 JSON（`title`/`conclusion`/`summary`/`next_step`），默认 stdin；
- `--proc`：原始 proc 文本，给出时脚本自己调用 `parse_hsk_proc` 补齐机器事实。

分析 JSON 里带 `parse` 键时优先用它，便于直接复用已经生成的解析结果。
两部分都可以缺省：只给 `--proc` 出机器事实报告，只给 `--analysis` 出结论文本报告。
"""
import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path

import parse_hsk_proc

STYLE = """
:root {
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
}
* { box-sizing: border-box; }
body { margin: 0; line-height: 1.62; }
.report { width: min(1180px, calc(100% - 40px)); margin: 32px auto; background: var(--paper); border: 1px solid var(--line-strong); box-shadow: 0 12px 34px rgba(24,33,43,.08); }
.report-header { display: grid; grid-template-columns: 10px 1fr; min-height: 184px; border-bottom: 1px solid var(--line); }
.signal-rail { background: var(--ok); }
.state-warning .signal-rail { background: var(--warning); }
.state-danger .signal-rail { background: var(--danger); }
.header-main { padding: 32px 38px 28px; }
.kicker { margin: 0 0 8px; color: var(--muted); font: 700 12px/1.3 ui-monospace, SFMono-Regular, Consolas, monospace; text-transform: uppercase; }
h1 { margin: 0; font-family: "Arial Narrow", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; font-size: 36px; line-height: 1.2; font-weight: 760; letter-spacing: 0; }
.verdict { display: flex; align-items: flex-start; gap: 12px; margin-top: 20px; }
.verdict p { margin: 0; max-width: 920px; font-size: 17px; }
.meta-bar { display: flex; flex-wrap: wrap; gap: 12px 24px; padding: 13px 38px; border-bottom: 1px solid var(--line); background: #fafbfc; color: var(--muted); font-size: 12px; }
.meta-bar span { display: inline-flex; gap: 7px; align-items: center; }
.meta-label { color: #344054; font-weight: 700; }
.snapshot { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border-bottom: 1px solid var(--line); }
.snapshot-item { min-height: 92px; padding: 19px 24px; border-right: 1px solid var(--line); }
.snapshot-item:last-child { border-right: 0; }
.snapshot-value { display: block; font: 700 24px/1.2 ui-monospace, SFMono-Regular, Consolas, monospace; }
.snapshot-label { display: block; margin-top: 7px; color: var(--muted); font-size: 12px; }
.section { padding: 30px 38px 34px; border-bottom: 1px solid var(--line); }
.section:last-child { border-bottom: 0; }
.section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
h2 { margin: 0; font-size: 19px; line-height: 1.35; letter-spacing: 0; }
h3 { margin: 22px 0 10px; font-size: 14px; line-height: 1.4; }
h3:first-of-type { margin-top: 0; }
.section-note { color: var(--muted); font-size: 12px; }
.summary-list { border: 1px solid var(--line-strong); }
.summary-item { display: grid; grid-template-columns: 132px minmax(0, 1fr); min-width: 0; border-bottom: 1px solid var(--line); }
.summary-item:last-child { border-bottom: 0; }
.summary-item h3 { margin: 0; padding: 17px 18px; color: #344054; background: #f7f8fa; border-right: 1px solid var(--line); font-size: 13px; line-height: 1.55; letter-spacing: 0; }
.summary-item p { min-width: 0; margin: 0; padding: 17px 20px; color: #344054; overflow-wrap: anywhere; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { padding: 11px 12px; text-align: left; color: #475467; background: #f7f8fa; border-bottom: 1px solid var(--line-strong); font-size: 11px; white-space: nowrap; }
td { padding: 14px 12px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); white-space: nowrap; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: #fbfcfd; }
.channel-id { font: 700 12px/1.4 ui-monospace, SFMono-Regular, Consolas, monospace; }
.mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-variant-numeric: tabular-nums; }
.emphasis { font-weight: 700; }
.subvalue { display: block; margin-top: 2px; color: var(--muted); font-size: 10px; }
.badge { display: inline-flex; min-height: 24px; align-items: center; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 750; white-space: nowrap; }
.badge-ok { color: var(--ok); background: var(--ok-soft); }
.badge-warning { color: var(--warning); background: var(--warning-soft); }
.badge-danger { color: var(--danger); background: var(--danger-soft); }
.badge-info { color: var(--info); background: var(--info-soft); }
.issues { border-top: 1px solid var(--line); }
.issue { position: relative; display: grid; grid-template-columns: 4px 1fr; column-gap: 17px; padding: 18px 0; border-bottom: 1px solid var(--line); }
.issue:last-child { border-bottom: 0; }
.issue-signal { grid-row: 1 / span 2; width: 4px; min-height: 100%; background: var(--info); }
.issue-warning .issue-signal { background: var(--warning); }
.issue-danger .issue-signal { background: var(--danger); }
.issue-heading { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 11px; min-width: 0; }
.issue-channel { color: var(--muted); font: 700 11px/1.4 ui-monospace, SFMono-Regular, Consolas, monospace; }
.issue p { grid-column: 2; margin: 7px 0 0; color: #475467; }
.empty-state { padding: 20px 0; color: var(--ok); font-weight: 650; }
.empty { color: var(--muted); }
.actions { margin: 0; padding: 0; list-style: none; counter-reset: action; border-top: 1px solid var(--line); }
.actions li { display: grid; grid-template-columns: 34px 1fr; gap: 12px; padding: 16px 0; border-bottom: 1px solid var(--line); counter-increment: action; }
.actions li::before { content: counter(action); display: grid; width: 28px; height: 28px; place-items: center; color: var(--info); background: var(--info-soft); border-radius: 50%; font: 750 12px/1 ui-monospace, SFMono-Regular, Consolas, monospace; }
.actions li:last-child { border-bottom: 0; }
.next-step { padding: 18px 20px; border-left: 4px solid var(--info); background: #f7faff; }
.next-step p { margin: 0; }
.next-step p + p { margin-top: 6px; }
details { margin-top: 20px; border-top: 1px solid var(--line); }
details.support { margin-top: 0; border-top: 0; }
.snap-block { padding-top: 24px; margin-top: 24px; border-top: 1px dashed var(--line); }
.snap-block:first-child { padding-top: 0; margin-top: 0; border-top: 0; }
.section-heading h3 { margin: 0; }
summary { padding: 15px 0 0; color: var(--info); cursor: pointer; font-size: 13px; font-weight: 700; }
summary:focus-visible { outline: 3px solid #93b9e2; outline-offset: 4px; }
pre { max-height: 460px; overflow: auto; margin: 14px 0 0; padding: 16px; color: #e8edf2; background: #202932; border-radius: 4px; font: 12px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; }
@media (max-width: 840px) {
  .report { width: 100%; margin: 0; border-width: 0; box-shadow: none; }
  .header-main, .section { padding-left: 20px; padding-right: 20px; }
  .meta-bar { padding-left: 20px; padding-right: 20px; }
  .snapshot { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .snapshot-item:nth-child(2n) { border-right: 0; }
  .snapshot-item:nth-child(-n+4) { border-bottom: 1px solid var(--line); }
  .table-wrap { overflow: visible; border: 0; }
  table, tbody, tr, td { display: block; width: 100%; }
  thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  tbody { display: grid; gap: 14px; }
  tbody tr { border: 1px solid var(--line-strong); }
  td { display: grid; grid-template-columns: minmax(92px, 36%) 1fr; gap: 12px; padding: 10px 12px; border-bottom: 1px solid var(--line); white-space: normal; }
  td::before { content: attr(data-label); color: var(--muted); font-size: 11px; font-weight: 700; }
  tbody tr:hover { background: transparent; }
  .summary-item { grid-template-columns: 112px minmax(0, 1fr); }
}
@media (max-width: 480px) {
  .report-header { min-height: 0; }
  .header-main { padding-top: 24px; padding-bottom: 24px; }
  .verdict { flex-direction: column; }
  h1 { font-size: 27px; }
  .snapshot { grid-template-columns: 1fr 1fr; }
  .snapshot-item { min-height: 80px; padding: 15px 16px; }
  .snapshot-value { font-size: 20px; }
  .section-heading { display: block; }
  .section-note { display: block; margin-top: 4px; }
  .summary-item { display: block; }
  .summary-item h3 { padding: 10px 14px; border-right: 0; border-bottom: 1px solid var(--line); }
  .summary-item p { padding: 14px; }
}
@media print {
  :root { --canvas: #fff; }
  .report { width: 100%; margin: 0; border: 0; box-shadow: none; }
  details { display: none; }
}
"""

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "reports"
DEFAULT_TITLE = "AX615 IVPS→VENC 诊断报告"


def esc(value):
    return html.escape("" if value is None else str(value))


def cell(value):
    if isinstance(value, (dict, list)):
        return esc(json.dumps(value, ensure_ascii=False))
    return esc(value)


def present(value):
    return value not in (None, "", "-", [])


def first_present(*values):
    return next((value for value in values if present(value)), "-")


def level_key(level):
    normalized = str(level or "信息").strip().lower()
    if normalized in {"错误", "高风险", "error", "danger", "critical"}:
        return "danger"
    if normalized in {"提示", "警告", "warning", "warn", "关注", "需确认"}:
        return "warning"
    return "info"


def overall_state(issues):
    keys = {level_key(issue.get("level")) for issue in issues}
    if "danger" in keys:
        return "danger", "存在异常"
    if "warning" in keys:
        return "warning", "需要关注"
    return "ok", "未发现已记录问题"


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


def render_table(headers, rows, empty="无数据"):
    if not rows:
        return f'<div class="table-wrap"><table><tbody><tr><td>{esc(empty)}</td></tr></tbody></table></div>'
    head = "".join(f"<th>{esc(name)}</th>" for name in headers)
    body = "".join(
        "<tr>" + "".join(f'<td data-label="{esc(name)}">{value}</td>'
                         for name, value in zip(headers, row)) + "</tr>"
        for row in rows
    )
    return (f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>")


def flag(value):
    if value is True:
        return '<span class="badge badge-ok">一致</span>'
    if value is False:
        return '<span class="badge badge-danger">不一致</span>'
    return "-"


def engine_text(engine):
    if not engine:
        return '<span class="empty">未采集 link_table_kernel</span>'
    return (f'<span class="mono">{esc(engine.get("src_id"))}:{esc(engine.get("src"))} → '
            f'{esc(engine.get("dst_id"))}:{esc(engine.get("dst"))}</span>')


def snapshot_note(samples, subject):
    """形态 / 握手 / 会话是同一套静态事实，与采样轮次无关。

    连续两次 `cat` 是为了看 `S1 -> S2` 差值，不构成两套形态；`SAMPLE n` 只是 proc 文本里的
    分隔标记（SKILL.md 第 1 节的采样脚本输出），这里不按轮次重复渲染同一张表。
    """
    if not samples:
        return f"{subject}为静态快照"
    if len(samples) < 2:
        return f"{subject}为静态快照，本次只有一轮采集"
    return f"{subject}为静态快照；两次采集只为「跨采样差值」服务"


def render_topology(sample):
    topology = sample.get("topology") or {}
    forms = topology.get("forms") or []
    links = topology.get("hsk_links") or []
    rows = [(f'<span class="badge badge-info">{esc(item.get("form"))}</span>',
             esc(item.get("evidence"))) for item in forms]
    link_rows = [
        (f'<span class="mono">{esc(link["src"]["module"])} {esc(link["src"]["grp"])}/'
         f'{esc(link["src"]["chn"])}</span>',
         f'<span class="mono">{esc(link["dst"]["module"])} {esc(link["dst"]["grp"])}/'
         f'{esc(link["dst"]["chn"])}</span>',
         f'<span class="mono">{esc(link.get("mode"))}</span>',
         f'<span class="mono">{esc(link.get("line"))}</span>',
         engine_text(link.get("engine")),
         f'<strong>{esc(link.get("consumer"))}</strong>')
        for link in links
    ]
    return (render_table(["形态", "依据"], rows, "未识别到有效 HSK 编码链路")
            + '<h3>HSK 编码链路</h3>'
            + render_table(["源", "目的", "Mode", "Line", "Engine", "消费端"], link_rows,
                           "link_table 缺失或没有 VENC/JENC 目的端"))


OFFLINE_BADGES = {"progressing": "ok", "upstream_stall": "danger", "link_dispatch_drop": "danger",
                  "downstream_stall": "danger", "stream_buf_backpressure": "warning",
                  "no_input": "info", "insufficient_evidence": "info"}

# 表格排序：现场问题在前，正常与「不需判定」在后。
OFFLINE_ORDER = ("downstream_stall", "link_dispatch_drop", "upstream_stall",
                 "stream_buf_backpressure", "no_input", "insufficient_evidence", "progressing")


def offline_upstream_cell(link):
    upstream = link.get("upstream")
    if not upstream:
        return '<span class="empty">未采集 IVPS 对应通道</span>'
    return (f'<span class="mono">flt{esc(first_present(upstream.get("filter")))} '
            f'{esc(first_present(upstream.get("engine")))}</span>'
            f'<span class="subvalue">In {esc(first_present(upstream.get("in_cnt")))} · '
            f'Out {esc(first_present(upstream.get("out_cnt")))} · '
            f'OutSts {esc(first_present(upstream.get("out_sts")))}/'
            f'{esc(first_present(upstream.get("out_depth")))}</span>'
            f'<span class="subvalue">抽帧 {esc(first_present(upstream.get("frc_mode")))} '
            f'{esc(first_present(upstream.get("frc")))} · '
            f'OutFps {esc(first_present(upstream.get("out_fps")))}</span>')


def offline_downstream_cell(link):
    downstream = link.get("downstream")
    if not downstream:
        return '<span class="empty">未采集编码通道</span>'
    return (f'{esc(downstream.get("module"))} chn{esc(downstream.get("chn"))}'
            f'<span class="subvalue">FrmRecv {esc(first_present(downstream.get("recv")))} · '
            f'SubMit {esc(first_present(downstream.get("submit")))} · '
            f'ReadCycle {esc(first_present(downstream.get("read_cycle")))} · '
            f'AvalRSize {esc(first_present(downstream.get("aval_r_size")))} · '
            f'HwUsed {esc(first_present(downstream.get("hw_used")))}</span>'
            f'<span class="subvalue">码控 {esc(first_present(downstream.get("rc_mode")))} '
            f'Src/Dst {esc(first_present(downstream.get("src_fr")))}/'
            f'{esc(first_present(downstream.get("dst_fr")))} fps · '
            f'OutFps {esc(first_present(downstream.get("out_fps")))}</span>')


def render_offline(sample):
    links = sample.get("offline_links") or []
    if not links:
        return ('<div class="empty-state">没有非 HSK 绑定的 IVPS→编码器链路；'
                'HSK 链路看上方的握手判定</div>')
    ranked = sorted(links, key=lambda item: OFFLINE_ORDER.index(item["verdict"])
                    if item.get("verdict") in OFFLINE_ORDER else len(OFFLINE_ORDER))
    rows = []
    for link in ranked:
        verdict = link.get("verdict")
        badge = OFFLINE_BADGES.get(verdict, "info")
        evidence = link.get("evidence")
        note = f'<span class="subvalue">{esc(evidence)}</span>' if present(evidence) else ""
        rows.append((
            f'<span class="mono">{esc(link["src"]["module"])} {esc(link["src"]["grp"])}/'
            f'{esc(link["src"]["chn"])}</span>',
            f'<span class="mono">{esc(link["consumer"])} {esc(link["dst"]["grp"])}/'
            f'{esc(link["dst"]["chn"])}</span>',
            f'<span class="mono">{esc(link.get("mode"))}</span>',
            offline_upstream_cell(link),
            offline_downstream_cell(link),
            f'<span class="badge badge-{badge}">{esc(verdict or "待判定")}</span>{note}',
        ))
    return render_table(["源", "目的", "Mode", "IVPS 上游最新计数", "编码器下游最新计数", "判定"],
                        rows)


def rc_fps_cell(rc):
    """编码通道的配置帧率：`SrcFr`/`DstFr` 是这一路应有的输入/输出速率。"""
    if not rc:
        return "-"
    return (f'<span class="mono">{esc(first_present(rc.get("SrcFr")))}/'
            f'{esc(first_present(rc.get("DstFr")))}</span>'
            f'<span class="subvalue">{esc(first_present(rc.get("RcMode")))}</span>')


def render_handshake(sample):
    rows = []
    for item in sample.get("hsk_channels") or []:
        hsk = item.get("hsk") or {}
        derived = item.get("derived") or {}
        mapping = item.get("session") or {}
        height = derived.get("handshake_height")
        consistency = []
        if derived.get("height_matches_enc_h") is False:
            consistency.append(f'ceil(EncH/64)*64={derived.get("expected_height_from_enc_h")} ✗')
        if derived.get("slice_check_matches_enc_h") is False:
            consistency.append(f'sliceNum*minhskLin={derived.get("slice_num_x_minhsk_lin")} ✗')
        if not consistency and derived.get("hsk_enabled") and height is not None:
            consistency.append("参数自洽")
        sess_ids = mapping.get("sess_ids")
        rows.append((
            f'<span class="channel-id">{esc(item.get("module"))} chn{esc(item.get("chn"))}</span>',
            f'<strong>{esc(first_present(hsk.get("bHsk")))}</strong>',
            f'<span class="mono">{esc(first_present(hsk.get("srcNum")))}</span>',
            rc_fps_cell(item.get("rc")),
            f'<span class="mono">{esc(first_present(hsk.get("EncH")))}</span>',
            f'<span class="mono">{esc(first_present(hsk.get("initVal")))} → '
            f'{esc(first_present(hsk.get("syncVal")))}</span>',
            f'<span class="mono emphasis">{esc(first_present(height))}</span>',
            esc("；".join(consistency)) if consistency else "-",
            f'<span class="mono">{esc(first_present(hsk.get("waitId")))}/'
            f'{esc(first_present(hsk.get("upId")))}</span>',
            f'<span class="mono">{esc(sess_ids if sess_ids else "-")}</span>',
            f'<span class="mono">{esc(first_present(mapping.get("wait_branch_count")))}</span>',
            f'<span class="badge badge-warning">{esc(mapping.get("form_hint"))}</span>'
            if mapping.get("form_hint") else "-",
        ))
    return render_table(["编码通道", "bHsk", "srcNum", "配置帧率 Src/Dst (fps)", "EncH",
                          "initVal → syncVal", "握手高度", "参数一致性", "waitId/upId",
                          "映射 SessId", "等待分支", "形态提示"], rows,
                         "没有采集到 venc/jenc HSK STATUS")


def connect_lines(connects):
    if not connects:
        return "-"
    lines = []
    for item in connects:
        detail = (f'ConId {first_present(item.get("con_id"))} {first_present(item.get("type"))} '
                  f'RegVal={first_present(item.get("reg_val"))} 进度={first_present(item.get("progress"))}')
        if item.get("verdict"):
            detail += f' · {item["verdict"]}'
        lines.append(f'<div class="mono">{esc(detail)}</div>')
    return "".join(lines)


def render_sessions(sample):
    rows = []
    for check in sample.get("session_checks") or []:
        derived = check.get("derived") or {}
        note = derived.get("note")
        blocks_note = f'<span class="subvalue">{esc(note)}</span>' if note else ""
        state = check.get("state")
        state_html = (f'<span class="badge badge-{"ok" if state == 2 else "danger"}">'
                      f'{esc(state)}</span>')
        rows.append((
            f'<span class="mono">{esc(check.get("sess_id"))}</span>',
            state_html,
            f'<span class="mono">{esc(first_present(check.get("init_val")))}</span>',
            f'<span class="mono">{esc(first_present(derived.get("height_from_encoder")))}</span>'
            + blocks_note,
            connect_lines(check.get("connects")),
        ))
    return render_table(["SessId", "State", "Session InitVal", "编码器握手高度", "连接进度"],
                        rows, "没有采集到 syncagent SESSION")


def render_deltas(deltas, detail=False):
    if not deltas:
        return ('<div class="empty-state">只有一轮采样，无法比较 S1 → S2；'
                '持续卡死结论需要第二次采样确认</div>')
    blocks = []
    for entry in deltas:
        pair = " → ".join(str(item) for item in entry.get("sample_pair") or [])
        stalled = entry.get("stalled_groups") or []
        badges = "".join(f'<span class="badge badge-warning">{esc(group)}</span> '
                         for group in stalled) or '<span class="badge badge-ok">无整组停滞</span>'
        groups = entry.get("groups") or []
        group_rows = [
            (f'<span class="mono">{esc(item.get("group"))}</span>',
             esc(", ".join(item.get("changed") or []) or "-"),
             esc(", ".join(item.get("unchanged") or []) or "-"))
            for item in groups
        ]
        counter_rows = [
            (f'<span class="mono">{esc(item.get("key"))}</span>',
             f'<span class="mono">{esc(item.get("s1"))}</span>',
             f'<span class="mono">{esc(item.get("s2"))}</span>',
             f'<span class="mono emphasis">{esc(item.get("delta"))}</span>')
            for item in entry.get("deltas") or []
        ]
        block = (f'<h3>{esc(pair)}</h3>'
                 f'<p>推进类计数整组不变的通道：{badges}</p>'
                 + render_table(["分组", "有变化的计数", "两轮不变的计数"], group_rows))
        if detail:
            block += ('<details><summary>查看全部计数器差值</summary>'
                      + render_table(["计数器", "S1", "S2", "Δ"], counter_rows)
                      + "</details>")
        blocks.append(block)
    return "".join(blocks)


def render_coverage(coverage):
    if not coverage:
        return ""
    blocks = []
    for label, key in (("解析模块", "modules"), ("proc 表", "proc_sections"),
                       ("确定性推导", "derived")):
        items = coverage.get(key) or []
        if items:
            blocks.append(f'<h3>{esc(label)}</h3><ul>'
                          + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>")
    limits = coverage.get("limits") or []
    if limits:
        blocks.append('<h3>不给出的结论</h3><ul>'
                      + "".join(f"<li>{esc(item)}</li>" for item in limits) + "</ul>")
    excluded = coverage.get("excluded") or []
    if excluded:
        blocks.append('<h3>不解析的表与列</h3><ul>'
                      + "".join(f"<li>{esc(item)}</li>" for item in excluded) + "</ul>")
    return "".join(blocks)


def render_issues(issues):
    if not issues:
        return '<div class="empty-state">未发现已记录问题</div>'
    items = []
    for issue in issues:
        key = level_key(issue.get("level"))
        channel = issue.get("channel")
        channel_html = (f'<span class="issue-channel">{esc(channel)}</span>'
                        if present(channel) else "")
        items.append(
            f'<article class="issue issue-{key}">'
            f'<div class="issue-signal" aria-hidden="true"></div>'
            f'<div class="issue-heading"><span class="badge badge-{key}">'
            f'{esc(issue.get("level"))}</span>{channel_html}'
            f'<strong>{esc(issue.get("field"))}</strong></div>'
            f'<p>{esc(issue.get("message"))}</p>'
            f"</article>"
        )
    return '<div class="issues">' + "".join(items) + "</div>"


def render(data, parsed=None, source="标准输入", detail=False):
    title = data.get("title") or DEFAULT_TITLE
    conclusion = data.get("conclusion", "")
    summary = data.get("summary", "")
    next_step = data.get("next_step", "")
    environment = (parsed or {}).get("environment") or {}
    issues = (parsed or {}).get("issues") or data.get("issues") or []
    samples = (parsed or {}).get("samples") or []
    coverage = (parsed or {}).get("coverage") or {}

    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    state_key, state_label = overall_state(issues)
    danger_count = sum(level_key(issue.get("level")) == "danger" for issue in issues)
    warning_count = sum(level_key(issue.get("level")) == "warning" for issue in issues)
    latest = samples[-1] if samples else {}
    hsk_links = (latest.get("topology") or {}).get("hsk_links") or []
    offline_links = latest.get("offline_links") or []
    hsk_channels = [item for item in latest.get("hsk_channels") or []
                    if (item.get("derived") or {}).get("hsk_enabled")]
    forms = sorted({item.get("form") for item in (latest.get("topology") or {}).get("forms") or []})
    sdk_version = environment.get("sdk_version") or data.get("sdk_version") or "未知"
    module_versions = environment.get("module_versions") or {}
    sample_count = environment.get("sample_count") or len(samples)

    meta = [
        ("数据源", esc(source)),
        ("SDK 版本", f'<code>{esc(sdk_version)}</code>'),
        ("采样", esc(f"{sample_count} 轮 · " + " / ".join(environment.get("sample_labels") or []))
         if samples else "未提供 proc"),
        ("模式", "详细" if detail else "简洁"),
        ("生成时间", f"<time>{esc(generated)}</time>"),
    ]
    if module_versions:
        meta.insert(2, ("模块版本", esc("；".join(
            f"{name}: {version}" for name, version in module_versions.items()))))

    machine_note = ("脚本解析结果" if samples
                    else "未提供 proc 文本，仅渲染结论文本")
    # 详细模式只附分析 JSON：解析结果已经渲染成上文的表，整份 dump 会让页面平白多出上百 KB。
    details = "" if not detail else html.escape(json.dumps(data, ensure_ascii=False, indent=2))

    # 简洁模式只保留结论、问题与证据表；逐条计数器明细和解析范围只在详细模式渲染。
    coverage_section = "" if not detail else f'''  <section class="section">
    <div class="section-heading"><h2>解析范围</h2><span class="section-note">脚本给出与不给出的结论</span></div>
    {render_coverage(coverage) or '<div class="empty-state">未提供 proc 文本</div>'}
  </section>
'''

    # 形态 / 握手 / 会话 / 跨采样差值 / Offline 链路是同一批静态事实，只支撑上面的结论。
    # 简洁模式整体折叠，详细模式展开。
    if not samples:
        snapshot_section = '''  <section class="section">
    <div class="section-heading"><h2>支撑快照</h2></div>
    <div class="empty-state">未提供 proc 文本</div>
  </section>
'''
    else:
        blocks = [
            ("HSK 形态", snapshot_note(samples, "形态") + "；判定以 link_table 的连接关系为准",
             render_topology(latest)),
            ("握手基准", snapshot_note(samples, "握手") + "；initVal → syncVal 按 16 位模 65536 计算",
             render_handshake(latest)),
            ("syncagent 会话", snapshot_note(samples, "会话") + "；State 是 HSK 工作的前置条件",
             render_sessions(latest)),
            ("跨采样差值", "只有单调推进类计数能判定停滞",
             render_deltas((parsed or {}).get("deltas") or [], detail)),
            ("Offline 链路", snapshot_note(samples, "Offline 链路") + "；非 HSK 绑定没有握手寄存器，按业务计数差值判定",
             render_offline(latest)),
        ]
        body = "".join(
            f'    <div class="snap-block">'
            f'<div class="section-heading"><h3>{esc(title)}</h3>'
            f'<span class="section-note">{esc(note)}</span></div>{block}</div>\n'
            for title, note, block in blocks
        )
        if detail:
            snapshot_section = ('  <section class="section">\n'
                                '    <div class="section-heading"><h2>支撑快照</h2></div>\n'
                                + body + '  </section>\n')
        else:
            snapshot_section = ('  <section class="section">\n'
                                '    <details class="support">'
                                '<summary>支撑快照：HSK 形态 / 握手基准 / syncagent 会话 / 跨采样差值 / Offline 链路</summary>\n'
                                + body + '    </details>\n  </section>\n')

    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{STYLE}</style>
</head>
<body>
<main class="report state-{state_key}">
  <header class="report-header">
    <div class="signal-rail" aria-hidden="true"></div>
    <div class="header-main">
      <p class="kicker">AX615 · IVPS→VENC DIAGNOSE</p>
      <h1>{esc(title)}</h1>
      <div class="verdict"><span class="badge badge-{state_key}">{state_label}</span><p>{esc(conclusion) or "未提供结论"}</p></div>
    </div>
  </header>
  <div class="meta-bar">{''.join(f'<span><b class="meta-label">{label}</b>{value}</span>' for label, value in meta)}</div>
  <div class="snapshot" aria-label="诊断概览">
    <div class="snapshot-item"><span class="snapshot-value">{esc(' / '.join(forms) or '-')}</span><span class="snapshot-label">HSK 形态</span></div>
    <div class="snapshot-item"><span class="snapshot-value">{len(hsk_links)}</span><span class="snapshot-label">HSK 编码链路</span></div>
    <div class="snapshot-item"><span class="snapshot-value">{len(offline_links)}</span><span class="snapshot-label">Offline 链路</span></div>
    <div class="snapshot-item"><span class="snapshot-value">{len(hsk_channels)}</span><span class="snapshot-label">启用 HSK 的编码通道</span></div>
    <div class="snapshot-item"><span class="snapshot-value">{danger_count} / {warning_count}</span><span class="snapshot-label">错误·高风险 / 需确认</span></div>
  </div>
  <section class="section">
    <div class="section-heading"><h2>结论摘要</h2><span class="section-note">区分已确认事实与当前推断</span></div>
    {render_summary(summary)}
  </section>
  <section class="section">
    <div class="section-heading"><h2>问题与依据</h2><span class="section-note">{machine_note}</span></div>
    {render_issues(issues)}
  </section>
{coverage_section}  <section class="section">
    <div class="section-heading"><h2>下一步</h2></div>
    <div class="next-step">{render_paragraphs(next_step)}</div>
    {"" if detail else '<p class="section-note">简洁模式已省略逐条计数器差值、解析范围与分析 JSON；需要时用 --detail 重新生成</p>'}
    <details><summary>查看分析 JSON</summary><pre>{details}</pre></details>
  </section>
{snapshot_section}
</main>
</body>
</html>'''


def write_report(data, parsed=None, output_dir=DEFAULT_OUTPUT_DIR, filename=None,
                 source="标准输入", detail=False):
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if not filename:
        filename = "ax615-ivps-venc-diagnose-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".html"
    path = directory / filename
    path.write_text(render(data, parsed, source, detail), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", default="-", help="分析 JSON，默认 stdin")
    parser.add_argument("--proc", help="原始 proc 文本；给出时由本脚本调用解析器")
    parser.add_argument("--detail", action="store_true",
                        help="详细模式；默认简洁模式只渲染结论、问题与证据表")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="报告输出目录，默认 <skill>/reports")
    parser.add_argument("--filename")
    args = parser.parse_args()
    raw = sys.stdin.read() if args.analysis == "-" else Path(args.analysis).read_text(encoding="utf-8")
    data = json.loads(raw) if raw.strip() else {}
    parsed = data.get("parse")
    if parsed is None and args.proc:
        parsed = parse_hsk_proc.parse(Path(args.proc).read_text(encoding="utf-8"))
    source = args.proc or data.get("source") or "标准输入"
    path = write_report(data, parsed, args.output_dir, args.filename, source, args.detail)
    print(f"HTML_REPORT={path}")
    print(f"HTML_REPORT_DIR={path.parent}")


if __name__ == "__main__":
    main()
