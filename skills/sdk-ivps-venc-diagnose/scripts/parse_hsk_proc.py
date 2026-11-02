#!/usr/bin/env python3
"""Parse AX615 HSK diagnosis proc dumps into stable JSON and flag obvious HSK issues.

输入是 SKILL.md 第 1 节采样脚本产出的文本：可以带多轮 `===== SAMPLE n =====` 分隔，
也可以直接是每轮 `cat /proc/ax_proc/{link_table,syncagent,ivps,venc,jenc}` 的粘贴结果
（含 `/root #` 提示符）。只做确定性的解析与 16 位环形算术；形态判定和卡死结论留在
SKILL.md 的散文规则里，脚本不代替人工下结论。
"""
import argparse
import json
import math
import re
import sys

# ---------------------------------------------------------------- 基础转换

# 十六进制地址保持 proc 打印原样，便于和现场文本逐字比对。
RAW_FIELDS = ("SyncAddr", "waWaPhy0", "waUpPhy0", "waReInfo0", "waReInfo1", "upReInfo")

# HSK 只在低内存/低延迟两种 data flow mode 下启用（venc.c 的 VENC_CHECK_HSK_MODE）；
# SW_Offline、HW_Online、Mode_Unset 的链路没有握手寄存器，SW_Offline 改走第 3.2 节的
# offline 业务计数判定，HW_Online/Mode_Unset 只标注模式。
HSK_MODES = ("SW_Low_Mem", "SW_Low_Latency")


def num(value):
    """把 proc 字段转成 int/float；无法识别时返回 None，由 typed() 保留原文。"""
    if isinstance(value, (int, float)):
        return value
    if value in (None, "", "-"):
        return None
    try:
        return float(value) if "." in value else int(value, 0)
    except (TypeError, ValueError):
        return None


def typed(value):
    if value in (None, "", "-", "N", "Y"):
        return value
    converted = num(value)
    return value if converted is None else converted


def hex_addr(value):
    """把 `43c45000` / `0x43c45000` 统一成 `0x43c45000`，便于跨模块比对地址。"""
    if value in (None, "", "-"):
        return value
    text = str(value).strip()
    try:
        return "0x%x" % int(text, 16)
    except ValueError:
        return text


def keep_raw(name, value):
    """地址类字段保留 proc 打印原样，便于和现场文本逐字比对。"""
    return value if name in RAW_FIELDS else typed(value)


def sdk_versions(text):
    """收集 proc 中所有版本横幅，按模块名归类（第一个是 ax_sys）。"""
    versions = {}
    order = []
    for match in re.finditer(r"^\s*\[?\s*SDK\s+version\s*\]?\s*[:：]\s*(\S.*?)\s*$", text, re.M | re.I):
        banner = match.group(1)
        module = banner.split()[0] if banner.split() else banner
        # 同一个模块名可能被重复打印，保留首次出现的完整横幅。
        if module not in versions:
            versions[module] = banner
            order.append(module)
    return versions, order


# ---------------------------------------------------------------- 表格切分

TITLE_RE = re.compile(r"^-{3,}\s*(?P<title>\S.*?)\s*-{2,}\s*$")


def is_noise(line):
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("[SDK version]"):
        return True
    if "/proc/ax_proc" in stripped:
        return True
    return bool(re.fullmatch(r"\S*\s*#", stripped))


def merge_colon(tokens):
    """合并 proc 用 `%d :%d` 打印的值：`1` `:24064` 与 `0.0` `:` `0.0`。"""
    joined = []
    for token in tokens:
        if token.startswith(":") and joined:
            joined[-1] += token
            continue
        joined.append(token)
    merged = []
    index = 0
    while index < len(joined):
        current = joined[index]
        if current.endswith(":") and index + 1 < len(joined) and not joined[index + 1].startswith(":"):
            merged.append(current + joined[index + 1])
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def tokenize(line):
    """按空白切分，保留 `[...]` 为一整块，并合并被空格的 `:` 拆开的值。"""
    tokens = []
    index = 0
    length = len(line)
    while index < length:
        char = line[index]
        if char.isspace():
            index += 1
            continue
        if char == "[":
            end = line.find("]", index)
            end = length - 1 if end == -1 else end
            tokens.append(line[index:end + 1])
            index = end + 1
            continue
        end = index
        while end < length and not line[end].isspace():
            end += 1
        tokens.append(line[index:end])
        index = end
    return merge_colon(tokens)


def bracket_values(token):
    if token.startswith("[") and token.endswith("]"):
        return [typed(item) for item in token[1:-1].split()]
    return None


def numbered_group(header, start):
    """返回 `RegVal0 RegVal1 RegVal2` 这类同名前缀编号列的 (前缀, 列数)。"""
    match = re.match(r"^(.*?)(\d+)$", header[start])
    if not match:
        return None
    prefix, width = match.group(1), len(match.group(2))
    names = []
    for offset in range(start, len(header)):
        next_match = re.match(r"^(.*?)(\d+)$", header[offset])
        if not next_match or next_match.group(1) != prefix or len(next_match.group(2)) != width:
            break
        if int(next_match.group(2)) != int(match.group(2)) + len(names):
            break
        names.append(header[offset])
    return (prefix, names) if names else None


def zip_row(header, tokens, title, issues=None):
    """把一行数据按列名对齐。

    `[...]` 块有两种含义：对应 `RegVal0 RegVal1 RegVal2` 这类编号列组时按列展开；
    否则整块作为一个列表值（例如 `OppWaitChn`、`HoldCnt`）。对齐失败时记录问题而不是
    静默错位。
    """
    row = {}
    column = 0
    for token in tokens:
        if column >= len(header):
            if issues is not None:
                issues.append({"level": "错误", "channel": None, "field": "表格 %s" % title,
                               "message": "%s 数据行字段数超出表头(%d 列)，多余字段已忽略" % (title, len(header))})
            break
        values = bracket_values(token)
        if values is None:
            row[header[column]] = keep_raw(header[column], token)
            column += 1
            continue
        group = numbered_group(header, column)
        if group and len(group[1]) == len(values):
            for name, value in zip(group[1], values):
                row[name] = value
            column += len(group[1])
            continue
        row[header[column]] = values
        column += 1
    if column != len(header) and issues is not None:
        issues.append({"level": "错误", "channel": None, "field": "表格 %s" % title,
                       "message": "%s 数据行字段数(%d)与表头(%d 列)不匹配，字段可能错位，结论需人工核对"
                                  % (title, column, len(header))})
    return row


def sections(block):
    """切成 (标题, 表头, [数据行]) 列表；同一标题可重复出现（如 HSK STATUS 的两段表）。"""
    result = []
    title = None
    header = None
    rows = []
    issues = []
    for line in block.splitlines():
        if is_noise(line):
            continue
        title_match = TITLE_RE.match(line)
        if title_match:
            if header is not None and rows:
                result.append((title, header, rows))
            title = title_match.group("title")
            header = None
            rows = []
            continue
        stripped = line.lstrip()
        if not re.match(r"^[\d\[]", stripped):
            # 新表头：首字段是列名而非数据。表头里的 `[...]` 是列名分组（要展开成
            # 独立的列），但 `Src : Dst` 这种被空格拆开的列名要合并，才能与数据行对齐。
            if header is not None and rows:
                result.append((title, header, rows))
            header = [token.strip("[]") for token in merge_colon(line.split())]
            rows = []
            continue
        if header is None:
            continue
        rows.append(zip_row(header, tokenize(line), title or "<无标题>", issues))
    if header is not None and rows:
        result.append((title, header, rows))
    return result, issues


def group_by_title(tables):
    grouped = {}
    for title, header, rows in tables:
        grouped.setdefault(title, []).append((header, rows))
    return grouped


# ---------------------------------------------------------------- 模块解析

LINK_RE = re.compile(
    r"^\(\s*(?P<src_mod>\w+)\s+(?P<src_grp>-?\d+)\s+(?P<src_chn>-?\d+)\s*\)\s*->\s*"
    r"\(\s*(?P<dst_mod>\w+)\s+(?P<dst_grp>-?\d+)\s+(?P<dst_chn>-?\d+)\s*\)\s*"
    r"Mode\s*:\s*(?P<mode>\S+)\s+Line\s*:\s*(?P<line>-?\d+)")

# `/proc/ax_proc/link_table_kernel` 在 `Line` 之后多印 `Engine (srcId:SrcEngine --> dstId:DstEngine)`，
# 这是 SKILL.md 第 2 节判断 VENC/JENC 分支的唯一依据（用户态 link_table 没有该列）。
LINK_KERNEL_RE = re.compile(
    r"^\(\s*(?P<src_mod>\w+)\s+(?P<src_grp>-?\d+)\s+(?P<src_chn>-?\d+)\s*\)\s*->\s*"
    r"\(\s*(?P<dst_mod>\w+)\s+(?P<dst_grp>-?\d+)\s+(?P<dst_chn>-?\d+)\s*\)\s*"
    r"Mode\s*:\s*(?P<mode>\S+)\s+Line\s*:\s*(?P<line>-?\d+)\s+"
    r"Engine\s*\(\s*(?P<src_id>-?\d+)\s*:\s*(?P<src_engine>\w+)\s*-->\s*"
    r"(?P<dst_id>-?\d+)\s*:\s*(?P<dst_engine>\w+)\s*\)")


def link_key(src_mod, src_grp, src_chn, dst_mod, dst_grp, dst_chn):
    return (src_mod, src_grp, src_chn, dst_mod, dst_grp, dst_chn)


def parse_link_table(*texts):
    """解析用户态 `link_table` 与/或 `link_table_kernel`，按同一条链路合并。

    两次输出覆盖同一批链路，kernel 版多带 `Engine`；合并后每条链路只有一个 `engine` 键，
    缺失 `engine` 说明该链路没采到 kernel 表。
    """
    merged = {}
    order = []
    for text in texts:
        if not text:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            kernel = LINK_KERNEL_RE.match(stripped)
            match = kernel or LINK_RE.match(stripped)
            if not match:
                continue
            groups = match.groupdict()
            key = link_key(groups["src_mod"], int(groups["src_grp"]), int(groups["src_chn"]),
                           groups["dst_mod"], int(groups["dst_grp"]), int(groups["dst_chn"]))
            if key not in merged:
                merged[key] = {"src": {"module": groups["src_mod"], "grp": int(groups["src_grp"]),
                                       "chn": int(groups["src_chn"])},
                               "dst": {"module": groups["dst_mod"], "grp": int(groups["dst_grp"]),
                                       "chn": int(groups["dst_chn"])},
                               "mode": groups["mode"], "line": int(groups["line"])}
                order.append(key)
            if kernel:
                merged[key]["engine"] = {"src_id": int(groups["src_id"]),
                                         "src": groups["src_engine"],
                                         "dst_id": int(groups["dst_id"]),
                                         "dst": groups["dst_engine"]}
    return {"links": [merged[key] for key in order]}


# ---------------------------------------------------------------- 字段白名单
# 只保留 SKILL.md 第 2、3、4、5 节 用到的 proc 字段。GOP、RC ATTR 2/3、`CHN ATTR 1`
# （Profile/Stride/Crop/PixFmt/BufMode）、耗时与带宽统计、节点池等与 HSK 诊断无关的表和
# 列不解析。码控表是例外：第 3.2、6 节要用 `SrcFr`/`DstFr` 区分「配置低帧率」与「真停滞」，
# 所以 VENC `CHN RC ATTR 1`、JENC `CHN RC ATTR` 只取这几个列。

# syncagent 只保留 SESSION 的 SessId/State/ConWait/InitVal（在 parse_syncagent 中显式取值）、
# CONNECT 的同步寄存器与映射字段、INFO 的 HoldCnt/ReleaseCnt。
CONNECT_FIELDS = ("ConId", "State", "Type", "DoubleWait", "ChnId", "Cons",
                  "OppUpChn", "OppWaitChn", "RegVal",
                  "RegVal0", "RegVal1", "RegVal2",
                  "InitVal0", "InitVal1", "InitVal2", "SyncAddr")
INFO_FIELDS = ("HoldCnt", "ReleaseCnt")

# 编码器 HSK STATUS 两张表：第一张是握手寄存器与映射 id，第二张是等待分支关系。
# EncHPre/maxH/fMode/ringLCnt/saSize 等未在 SKILL.md 中使用的字段不保留。
HSK_FIELDS = ("bHsk", "srcNum", "EncH", "minhskLin", "sliceNum", "conId", "waitId", "upId",
              "initVal", "syncVal", "hskCnt", "errDropCnt", "bFrmDrop")
HSK_WAIT_FIELDS = ("cntWa", "douWa", "opWaChn0", "opWaChn1", "opUpChn0", "opUpChn1")

# 标题 -> 保留的列；不在表内的标题整表跳过。
IVPS_TITLES = {
    # `Frc(src:dst)` 是 IVPS 通道的抽帧配置，与编码侧 `SrcFr/DstFr` 一起解释低 OutFps。
    "CHN INFO": ("GrpId", "ChnId", "OutDepth", "OutSts", "FrcMode", "Frc(src:dst)", "OutFps"),
    "FILTER STATE": ("GrpId", "ChnId", "FltId", "Engine",
                     "TotalCnt", "Fail1", "Fail2", "InCnt", "OutCnt"),
}

# `None` 表示整表保留（HSK STATUS 两段表在定义上全部是 HSK 字段）。
ENCODER_TITLES = {
    "venc": {
        "CHN ATTR 2": ("frame", ("ID", "EncW", "EncH", "SeqNum", "PTS")),
        "CHN HSK STATUS": ("hsk", None),
        # 码控帧率：`SrcFr`/`DstFr` 是这一路编码配置的源/目的帧率。低 OutFps 是不是故障，
        # 必须靠它区分（例如 IVPS 抽帧到 1fps 时 JENC 的 SrcFr/DstFr 就是 1/1）。
        "CHN RC ATTR 1": ("rc", ("ID", "RcMode", "SrcFr", "DstFr", "TargetBitRate")),
        # VENC 的表标题是 `VENC STREAM BUF STATUS`，JENC 的是 `JENC CHN STREAM BUF STATUS`。
        "STREAM BUF STATUS": ("stream_buf", ("ChnId", "ReadCycle", "WriteCycle",
                                             "AvalRSize", "HwUsed")),
        "CHN STATUS 0": ("status0", ("ChnId", "Send2EncCnt", "Send2EncFail", "EncSucCnt",
                                     "ErrorCnt", "TimeOutCnt", "BufFullCnt", "NoFreeCnt")),
        # SubMitCnt/SubMitFail/WaitEncFail/SeqDiscont 是第 3.2 节offline 数据流判定的关键计数。
        "CHN STATUS 2": ("status2", ("VeChn", "FrmRecv", "DiscardedNum", "SubMitCnt",
                                     "SubMitFail", "RecvBsCnt", "BsFrmCnt", "OutFps",
                                     "WaitEncFail", "SeqDiscont")),
    },
    "jenc": {
        "CHN ATTR 2": ("frame", ("ID", "EncW", "EncH", "SeqNum", "PTS")),
        "CHN HSK STATUS": ("hsk", None),
        # JENC 的码控表没有 TargetBitRate，标题也不带 `1`。
        "CHN RC ATTR": ("rc", ("ID", "RcMode", "SrcFr", "DstFr")),
        # JENC 的 STREAM BUF STATUS 没有 `HwUsed`，对应列是 `BufBusy`，不在 SKILL.md 里。
        "STREAM BUF STATUS": ("stream_buf", ("VeChn", "ReadCycle", "WriteCycle", "AvalRSize")),
        "CHN STATUS 1": ("status1", ("VeChn", "SubmitCnt", "SucCnt", "RatDrpCnt", "EncFail",
                                     "BufOver", "AbortCnt", "TimeOutCnt", "BusyCnt", "HwUsed")),
        "CHN STATUS 2": ("status2", ("VeChn", "FrmRecv", "DiscardedNum", "SubMitCnt",
                                     "SubMitFail", "RecvBsCnt", "BsFrmCnt", "OutFps",
                                     "WaitEncFail", "SeqDiscont")),
        "FRAME LIST STATUS": ("frame_list", ("busyCnt", "freeCnt", "HwState")),
    },
}


def keep(row, fields):
    """按白名单取列；`fields` 为 None 时整行保留。"""
    if fields is None:
        return dict(row)
    return {name: row[name] for name in fields if name in row}


def parse_syncagent(text, issues):
    tables, table_issues = sections(text)
    issues.extend(table_issues)
    sessions = []
    for title, _, rows in tables:
        if title == "SESSION":
            for row in rows:
                sessions.append({"sess_id": row.get("SessId"), "state": row.get("State"),
                                 "con_wait": row.get("ConWait"), "init_val": row.get("InitVal"),
                                 "connects": [], "info": {}})
        elif title == "CONNECT" and sessions:
            sessions[-1]["connects"].extend(keep(row, CONNECT_FIELDS) for row in rows)
        elif title == "INFO" and sessions:
            for row in rows:
                sessions[-1]["info"].update(keep(row, INFO_FIELDS))
    for session in sessions:
        if session["state"] != 2:
            issues.append({"level": "高风险", "channel": session["sess_id"],
                           "field": "syncagent SESSION State",
                           "message": "SessId %s 的 State=%s（非 2），同步 session 未进入正常工作状态，"
                                      "不能把 wait 未推进直接归因于 VPP/VENC/JENC"
                                      % (session["sess_id"], session["state"])})
    return {"sessions": sessions}


IVPS_COUNTERS = ("TotalCnt", "Fail1", "Fail2", "InCnt", "OutCnt")


def parse_ivps(text, issues):
    tables, table_issues = sections(text)
    issues.extend(table_issues)
    grouped = group_by_title(tables)
    result = {}
    for title, fields in IVPS_TITLES.items():
        entries = grouped.get(title)
        if not entries:
            continue
        result[title.lower().replace(" ", "_")] = [keep(row, fields) for row in entries[0][1]]
    return result



ENCODER_COUNTERS = {
    "status0": ("Send2EncCnt", "Send2EncFail", "EncSucCnt", "ErrorCnt", "TimeOutCnt",
                "BufFullCnt", "NoFreeCnt"),
    "status1": ("SubmitCnt", "SucCnt", "RatDrpCnt", "EncFail", "BufOver", "AbortCnt",
                "TimeOutCnt", "BusyCnt"),
    "status2": ("FrmRecv", "DiscardedNum", "RecvBsCnt", "BsFrmCnt", "SubMitCnt",
                "SubMitFail", "WaitEncFail", "SeqDiscont"),
    "stream_buf": ("ReadCycle", "WriteCycle", "AvalRSize"),
}
ENCODER_EXTRA_COUNTERS = ("hskCnt", "errDropCnt", "bFrmDrop")


def title_of(title, tables):
    """按 `ENCODER_TITLES` 的后缀匹配表标题；返回 (标题, 键, 保留列) 或 None。"""
    for suffix, (key, fields) in tables.items():
        if title.endswith(suffix):
            return suffix, key, fields
    return None


def parse_encoder(module, text, issues):
    """VENC 与 JENC 的 proc 布局基本一致，按标题后缀匹配而不是固定偏移。"""
    tables, table_issues = sections(text)
    issues.extend(table_issues)
    grouped = group_by_title(tables)
    known = ENCODER_TITLES[module]
    channels = {}
    frame_list = {}

    def channel_of(identifier):
        return channels.setdefault(identifier, {"id": identifier})

    def attach(rows, key, id_key, fields):
        for row in rows:
            identifier = row.get(id_key)
            if identifier is None:
                continue
            channel_of(identifier)[key] = keep(row, fields)

    for title, entries in grouped.items():
        matched = title_of(title, known)
        if not matched:
            # RC/GOP 等与 HSK 诊断无关的表不解析，也不产生「无法识别」问题。
            continue
        _, key, fields = matched
        if key == "frame_list":
            # `FRAME LIST STATUS` 是模块级单行表（无通道号列），不能当成 chn0。
            frame_list.update(keep(entries[0][1][0], fields))
            continue
        if key == "hsk":
            id_key = entries[0][0][0]
            hsk_rows = entries[0][1]
            wait_key = entries[1][0][0] if len(entries) > 1 else id_key
            wait_rows = entries[1][1] if len(entries) > 1 else []
            for row in hsk_rows:
                identifier = row.get(id_key)
                if identifier is None:
                    continue
                channel_of(identifier)["hsk"] = keep(row, HSK_FIELDS)
            # 等待分支的物理地址和 `索引:值` 字段在第二张表里，与第一张表按同一通道号对齐。
            for row in wait_rows:
                identifier = row.get(wait_key)
                if identifier is None:
                    continue
                channel = channel_of(identifier)
                channel["hsk_wait"] = keep(row, HSK_WAIT_FIELDS)
                info = {}
                for name in ("waReInfo0", "waReInfo1", "upReInfo"):
                    info[name] = parse_pair(row.get(name))
                for name in ("waWaPhy0", "waUpPhy0"):
                    info[name] = hex_addr(row.get(name))
                channel["hsk_info"] = info
            continue
        attach(entries[0][1], key, entries[0][0][0], fields)
    return {"channels": list(channels.values()), "frame_list": frame_list}


def parse_pair(value):
    """`1 :24064` 这类 `索引:值` 字段。"""
    if not isinstance(value, str) or ":" not in value:
        return value
    head, _, tail = value.partition(":")
    return {"idx": num(head), "val": num(tail)}


# ---------------------------------------------------------------- 派生计算

MODULE_SIGNATURES = (
    # `Link Table Kernel` 必须单独匹配：它的表头也含 `Link Table`，只按用户态表切分会把
    # kernel 段并进 link_table 里，Engine 信息就丢了。
    ("link_table_kernel", re.compile(r"^-{3,}\s*.*Link Table Kernel", re.M)),
    ("link_table", re.compile(r"^-{3,}\s*.*Link Table", re.M)),
    ("syncagent", re.compile(r"^-{3,}\s*SESSION\s*-{2,}", re.M)),
    ("ivps", re.compile(r"^-{3,}\s*IVPS VERSION", re.M)),
    ("venc", re.compile(r"^-{3,}\s*VENC CHN ATTR 1", re.M)),
    ("jenc", re.compile(r"^-{3,}\s*JENC CHN ATTR 1", re.M)),
)
SAMPLE_RE = re.compile(r"^=+\s*SAMPLE\s+(?P<label>\S+)(?P<rest>.*?)=+\s*$", re.M)


def split_modules(text):
    found = []
    for name, pattern in MODULE_SIGNATURES:
        match = pattern.search(text)
        if match:
            found.append((match.start(), name))
    found.sort()
    modules = {}
    for index, (start, name) in enumerate(found):
        end = found[index + 1][0] if index + 1 < len(found) else len(text)
        modules[name] = text[start:end]
    return modules


def split_samples(text):
    markers = list(SAMPLE_RE.finditer(text))
    if not markers:
        return [{"label": "SAMPLE 1", "marker": None, "text": text}]
    samples = []
    if markers[0].start() > 0:
        head = text[:markers[0].start()].strip()
        if head:
            samples.append({"label": "SAMPLE 0", "marker": None, "text": head})
    for index, match in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        samples.append({"label": "SAMPLE %s" % match.group("label"),
                        "marker": match.group(0).strip(),
                        "text": text[match.end():end]})
    return samples


def parse_sample(text, issues):
    modules = split_modules(text)
    sample_issues = []
    sample = {"modules_found": sorted(modules),
              "link_table": {"links": []}, "syncagent": {"sessions": []},
              "ivps": {}, "venc": {"channels": [], "frame_list": {}},
              "jenc": {"channels": [], "frame_list": {}}}
    if "link_table" in modules or "link_table_kernel" in modules:
        # 两张表描述同一批链路，按 `(src, dst)` 合并，`engine` 只在 kernel 版里有。
        sample["link_table"] = parse_link_table(modules.get("link_table"),
                                                modules.get("link_table_kernel"))
        if "link_table_kernel" not in modules:
            sample_issues.append({"level": "提示", "channel": None, "field": "模块 link_table_kernel",
                                  "message": "本轮采样缺少 link_table_kernel，链路的 Engine 未知，"
                                             "消费端按目的通道落在 venc/jenc proc 的哪一侧归一"
                                             "（link_table 统一用 VENC 打印两条分支）；两侧都没有"
                                             "该通道时才需补采该表核对 Engine"})
    if "syncagent" in modules:
        sample["syncagent"] = parse_syncagent(modules["syncagent"], sample_issues)
    if "ivps" in modules:
        sample["ivps"] = parse_ivps(modules["ivps"], sample_issues)
    for name in ("venc", "jenc"):
        if name in modules:
            sample[name] = parse_encoder(name, modules[name], sample_issues)
    for module in ("link_table", "syncagent", "ivps", "venc", "jenc"):
        if module not in modules:
            sample_issues.append({"level": "提示", "channel": None, "field": "模块 %s" % module,
                                  "message": "本轮采样缺少 %s，该模块相关结论受此限制" % module})
    issues.extend(sample_issues)
    return sample


def hsk_widths(init_val, sync_val):
    """SKILL.md 第 3 节：init/sync/reg 均为 16 位无符号数，按模 65536 计算。"""
    init = init_val & 0xFFFF
    sync = sync_val & 0xFFFF
    return init, sync, (sync - init) & 0xFFFF


def progress_verdict(progress, height):
    if height == 0:
        return "握手高度为 0（initVal 与 syncVal 相同），无法按本轮区间判断"
    if progress == 0:
        return "寄存器位于 initVal，本轮尚未推进"
    if progress < height:
        return "寄存器处于本轮握手区间"
    if progress == height:
        return "寄存器到达 syncVal，本轮该侧握手完成"
    return "寄存器不在本轮 initVal -> syncVal 有效区间，属于越界、旧值或同步状态异常"


def derive_hsk_channel(module, channel, sessions, issues):
    """单个编码通道的握手高度、参数一致性和 syncagent 映射。"""
    hsk = channel.get("hsk") or {}
    info = channel.get("hsk_info") or {}
    enabled = hsk.get("bHsk") == "Y"
    derived = {"hsk_enabled": enabled}
    if not enabled:
        return {"derived": derived, "session": None}

    init_val, sync_val = hsk.get("initVal"), hsk.get("syncVal")
    enc_h = hsk.get("EncH")
    if not (isinstance(init_val, int) and isinstance(sync_val, int)):
        derived["note"] = "bHsk=Y 但缺少 initVal/syncVal，无法计算握手高度"
        return {"derived": derived, "session": None}

    init, sync, height = hsk_widths(init_val, sync_val)
    derived.update({"init": init, "sync": sync, "handshake_height": height})
    if height == 0:
        issues.append({"level": "提示", "channel": channel["id"],
                       "field": "%s HSK %s" % (module, "高度"),
                       "message": "%s chn%s 的 initVal=%s 与 syncVal=%s 相同，本轮握手高度为 0"
                                  % (module, channel["id"], init_val, sync_val)})
    if isinstance(enc_h, int) and enc_h > 0:
        aligned = int(math.ceil(enc_h / 64.0)) * 64
        derived["expected_height_from_enc_h"] = aligned
        derived["height_matches_enc_h"] = aligned == height
        if aligned != height:
            issues.append({"level": "提示", "channel": channel["id"],
                           "field": "%s HSK %s" % (module, "高度"),
                           "message": "%s chn%s 的 syncVal-initVal=%d 与 ceil(EncH/64)*64=%d 不一致，"
                                      "先报告 HSK 参数或版本配置不一致"
                                      % (module, channel["id"], height, aligned)})
    minhsk, slice_num = hsk.get("minhskLin"), hsk.get("sliceNum")
    if isinstance(minhsk, int) and isinstance(slice_num, int) and isinstance(enc_h, int):
        product = minhsk * slice_num
        derived["slice_num_x_minhsk_lin"] = product
        derived["slice_check_matches_enc_h"] = product == enc_h
        if product != enc_h:
            issues.append({"level": "提示", "channel": channel["id"],
                           "field": "%s HSK sliceNum*minhskLin" % module,
                           "message": "%s chn%s 的 sliceNum*minhskLin=%d 与 EncH=%d 不一致，"
                                      "交叉核对握手节奏前需确认参数"
                                      % (module, channel["id"], product, enc_h)})
    if isinstance(hsk.get("hskCnt"), int) and hsk.get("hskCnt") == 0:
        issues.append({"level": "提示", "channel": channel["id"], "field": "%s hskCnt" % module,
                       "message": "%s chn%s 的 bHsk=Y 但 hskCnt=0，该通道尚未产生 HSK 工作"
                                  % (module, channel["id"])})

    mapping = map_to_session(module, channel["id"], hsk, info, sessions, issues)
    return {"derived": derived, "session": mapping}


def connect_summary(item):
    """syncagent 连接行的诊断相关字段；`InitVal` 是 session 级字段，不在这里。"""
    row = item["row"]
    return {"con_id": item["con_id"], "type": item["type"], "chn": row.get("ChnId"),
            "cons": row.get("Cons"), "reg_val": row.get("RegVal"),
            "init_val0": row.get("InitVal0"), "sync_addr": row.get("SyncAddr"),
            "double_wait": row.get("DoubleWait"), "state": item["state"]}


def map_to_session(module, channel_id, hsk, info, sessions, issues):
    """按 waitId/upId 和物理寄存器地址把编码通道映射到 syncagent 连接。"""
    con_module = "MM_%s" % module.upper()
    wait_id, up_id = hsk.get("waitId"), hsk.get("upId")
    matches = []
    for session in sessions:
        for row in session["connects"]:
            if row.get("Cons") != con_module:
                continue
            if row.get("ChnId") in (wait_id, up_id):
                matches.append({"sess_id": session["sess_id"], "state": session["state"],
                                "con_id": row.get("ConId"), "type": row.get("Type"), "row": row})
    if not matches:
        issues.append({"level": "提示", "channel": channel_id,
                       "field": "%s HSK %s" % (module, "syncagent 映射"),
                       "message": "%s chn%s 的 waitId=%s/upId=%s 在 syncagent 中找不到对应连接，"
                                  "同步字段无法交叉映射" % (module, channel_id, wait_id, up_id)})
        return None
    up_cons = [item for item in matches if item["type"] == "update"]
    wait_cons = [item for item in matches if item["type"] == "wait"]
    sess_ids = sorted({item["sess_id"] for item in matches})
    mapping = {"sess_ids": sess_ids, "wait_id": wait_id, "up_id": up_id,
               "up_connects": [connect_summary(item) for item in up_cons],
               "wait_connects": [connect_summary(item) for item in wait_cons],
               "wait_branch_count": len(wait_cons)}
    if len(sess_ids) > 1:
        issues.append({"level": "提示", "channel": channel_id,
                       "field": "%s HSK %s" % (module, "syncagent 映射"),
                       "message": "%s chn%s 的 waitId/upId 落在多个 SessId %s 上，"
                                  "不能跨 session 直接比较寄存器值"
                                  % (module, channel_id, sess_ids)})
        return mapping

    addresses = []
    for item in matches:
        address = hex_addr(item["row"].get("SyncAddr"))
        if address:
            addresses.append(address)
    reported = []
    for name in ("waWaPhy0", "waUpPhy0"):
        address = hex_addr(info.get(name))
        if address:
            reported.append(address)
    if reported:
        mapping["reported_addrs"] = sorted(reported)
        mapping["sync_addr_match"] = all(address in addresses for address in reported)
        if not mapping["sync_addr_match"]:
            issues.append({"level": "提示", "channel": channel_id,
                           "field": "%s HSK %s" % (module, "物理地址"),
                           "message": "%s chn%s 的 waWaPhy0/waUpPhy0=%s 与 syncagent SyncAddr=%s "
                                      "不一致，同步字段无法交叉映射"
                                      % (module, channel_id, sorted(reported), sorted(addresses))})
    if is_multi_wait(mapping):
        mapping["form_hint"] = "二对一"
    return mapping


def is_multi_wait(mapping):
    return mapping is not None and mapping.get("wait_branch_count", 0) > 1


def session_base_applies(session):
    """session 的 InitVal 能否代表这组 ConId 的读数，决定能不能拿它算进度。

    InitVal 只描述一个寄存器。同一个 session 的 ConId 可以落在不同寄存器上（例如
    MM_VPP->VENC/JENC 一链三 ConId），此时各 ConId 的 RegVal 互不相同，再用同一个 InitVal
    去减就是跨寄存器的运算，结果既不是进度也没有可比的高度，不能据此报同步异常。
    各 ConId 读数一致时 InitVal 代表整组，公式成立。
    """
    return len({row.get("RegVal") for row in session["connects"]}) <= 1


def derive_session(session, hsk_channels, issues):
    """按 SKILL.md 第 3 节计算每个连接相对 session 起点的当前进度。"""
    init_val = session.get("init_val")
    heights = [item["derived"]["handshake_height"] for item in hsk_channels
               if item.get("session") and session["sess_id"] in item["session"]["sess_ids"]
               and item["derived"].get("handshake_height") is not None]
    height = heights[0] if heights else None
    derived = {"height_from_encoder": height}
    connects = []
    if not isinstance(init_val, int) or init_val == 0:
        # InitVal=0 的 session（例如 ISP_IFE/ISP_ITP）是自由计数，不套用握手高度公式。
        derived["note"] = "session InitVal=%s，不套用 initVal->syncVal 握手高度公式" % init_val
        return {"derived": derived, "connects": connects}
    same_register = session_base_applies(session)
    if height is None:
        derived["note"] = "该 session 没有可映射的编码器 HSK，无法取得握手高度"
    elif not same_register:
        derived["note"] = "该 session 的 ConId 读数各不相同，session InitVal 只对应其中一个寄存器，不套用进度公式"
    for row in session["connects"]:
        entry = {"con_id": row.get("ConId"), "type": row.get("Type"), "cons": row.get("Cons"),
                 "chn": row.get("ChnId"), "reg_val": row.get("RegVal"),
                 "connect_init_val0": row.get("InitVal0")}
        reg_val = row.get("RegVal")
        if isinstance(reg_val, int) and same_register:
            progress = (reg_val & 0xFFFF) - (init_val & 0xFFFF) & 0xFFFF
            entry["progress"] = progress
            if height is not None:
                entry["verdict"] = progress_verdict(progress, height)
                if progress > height:
                    issues.append({"level": "高风险", "channel": session["sess_id"],
                                   "field": "syncagent ConId %s RegVal" % row.get("ConId"),
                                   "message": "SessId %s ConId %s(%s) 的当前进度 %d 大于握手高度 %d，"
                                              "该寄存器不在本轮有效区间，标记同步状态异常"
                                              % (session["sess_id"], row.get("ConId"),
                                                 row.get("Type"), progress, height)})
        connects.append(entry)
    return {"derived": derived, "connects": connects}


def consumer_of(link):
    """链路的消费端模块：kernel 表的 Engine 优先于 ModId（第 2 节）。

    某些版本目的模块仍打印 `VENC`，但 `Engine(...->JENC)` 才是真正的 JPEG HSK 分支。
    """
    engine = link.get("engine") or {}
    return engine.get("dst") or link["dst"]["module"]


def resolve_encoder_consumer(sample, destination):
    """把 link_table 的目的模块归一成真正持有该通道的编码模块。

    `link_table` 对用户侧把 H.26x 和 JENC 两条分支统一打印成 `VENC`（见第 5 节），所以目的
    通道在 venc proc 里不存在时要去 jenc 侧核对；两侧都没有该通道才返回 None（无法确认）。
    对应编码 proc 未采集时不做推断，原样返回 ModId。
    """
    module, _, chn = destination
    order = [module] + [other for other in ("VENC", "JENC") if other != module]
    collected = False
    for name in order:
        channels = (sample.get(name.lower()) or {}).get("channels") or []
        if not channels:
            continue
        collected = True
        if chn in {channel["id"] for channel in channels}:
            return name
    return None if collected else module


def multi_source_consumers(sample):
    """编码侧 `srcNum=2` 的 HSK 通道：它们由二对一形态解释，link_table 不再另算一对一。"""
    consumers = set()
    for module in ("venc", "jenc"):
        for channel in sample[module]["channels"]:
            hsk = channel.get("hsk") or {}
            if hsk.get("bHsk") == "Y" and hsk.get("srcNum") == 2:
                consumers.add((module.upper(), channel["id"]))
    return consumers


def derive_topology(sample, issues):
    links = sample["link_table"]["links"]
    encoder_links = [link for link in links if consumer_of(link) in ("VENC", "JENC")]
    hsk_links = [link for link in encoder_links if link["mode"] in HSK_MODES]
    non_hsk_links = [link for link in encoder_links if link["mode"] not in HSK_MODES]
    sources = {}
    for link in hsk_links:
        key = (link["src"]["module"], link["src"]["grp"], link["src"]["chn"])
        sources.setdefault(key, []).append(link)
    claimed = multi_source_consumers(sample)
    forms = []
    bindings = {}
    for key, group in sorted(sources.items()):
        destinations = {(consumer_of(link), link["dst"]["grp"], link["dst"]["chn"])
                        for link in group}
        resolved = {}
        for module, grp, chn in sorted(destinations):
            actual = resolve_encoder_consumer(sample, (module, grp, chn))
            if actual is None:
                issues.append({"level": "提示", "channel": None,
                               "field": "link_table 目的通道",
                               "message": "link_table 的 %s %s/%s -> %s %s/%s 在已解析的 venc 和"
                                          " jenc proc 里都没有 chn%s，消费端无法确认，该链路不计"
                                          "入 HSK 形态；补采 link_table_kernel 核对 Engine 后再定"
                                          "形态" % (key[0], key[1], key[2], module, grp, chn, chn)})
            else:
                resolved[(actual, grp, chn)] = module
        if not resolved:
            continue
        # srcNum=2 的目的端由编码侧的二对一形态解释，link_table 只提供它的来源绑定。
        pending = {item for item in resolved if (item[0], item[2]) not in claimed}
        for (module, grp, chn), printed in sorted(resolved.items()):
            note = "%s %s/%s -> %s %s/%s" % (key[0], key[1], key[2], printed, grp, chn)
            if printed != module:
                note += "（JENC/VENC 统一命名，实为 %s chn%s）" % (module, chn)
            bindings.setdefault((module, chn), []).append(note)
        if not pending:
            continue
        form = "一对二" if len(pending) > 1 else "一对一"
        forms.append({"form": form,
                      "evidence": "link_table: %s %s/%s -> %s" % (
                          key[0], key[1], key[2],
                          ", ".join(sorted("%s %s/%s" % item for item in pending)))})
    for module in ("venc", "jenc"):
        for channel in sample[module]["channels"]:
            hsk = channel.get("hsk") or {}
            if hsk.get("bHsk") != "Y":
                continue
            src_num = hsk.get("srcNum")
            if src_num == 2:
                # srcNum 只说「有两个来源」；绑定关系一律引用 link_table 里归一到该消费端的链路。
                notes = bindings.get((module.upper(), channel["id"]))
                evidence = "%s chn%s: srcNum=2" % (module, channel["id"])
                if notes:
                    evidence += "；link_table 绑定：" + "，".join(notes)
                elif links:
                    evidence += "；link_table 里没有指向该消费端的链路，来源绑定待确认"
                else:
                    evidence += "；link_table 未采集，来源绑定待确认"
                forms.append({"form": "二对一", "evidence": evidence})
            elif src_num == 1 and not any(item["form"] == "一对一" for item in forms):
                forms.append({"form": "一对一",
                              "evidence": "%s chn%s: srcNum=1" % (module, channel["id"])})
    return {"hsk_links": [{"src": link["src"], "dst": link["dst"], "mode": link["mode"],
                           "line": link["line"], "engine": link.get("engine"),
                           "consumer": consumer_of(link)} for link in hsk_links],
            "non_hsk_links": [{"src": link["src"], "dst": link["dst"], "mode": link["mode"],
                               "line": link["line"], "engine": link.get("engine"),
                               "consumer": consumer_of(link)} for link in non_hsk_links],
            "forms": forms}


def report_non_hsk_links(topology, issues):
    """非 HSK 绑定的 IVPS->编码器链路没有握手寄存器可判，但走第 3.2 节的数据流判定。

    这类链路必须显式列出而不是静默丢弃：没有 HSK STATUS 段是正常现象，不代表数据缺失。
    """
    links = topology.get("non_hsk_links") or []
    if not links:
        return
    described = ", ".join(sorted({
        "%s %s/%s -> %s %s/%s (%s)" % (link["src"]["module"], link["src"]["grp"],
                                       link["src"]["chn"], link["consumer"],
                                       link["dst"]["grp"], link["dst"]["chn"], link["mode"])
        for link in links}))
    modes = ", ".join(sorted({link["mode"] for link in links}))
    issues.append({"level": "提示", "channel": None, "field": "link_table 非 HSK 链路",
                   "message": "以下 IVPS->编码器链路是 %s 绑定：%s；HSK 只在 %s 下启用，"
                              "这些链路不做握手判定，改按业务计数与上下游关系判定数据流卡死"
                              % (modes, described, "/".join(HSK_MODES))})


# ---------------------------------------------------------------- offline 数据流判定

OFFLINE_MODE = "SW_Offline"

# 第 3.2 节的判定结果；只有这四种构成现场问题，no_input/insufficient_evidence 只作信息呈现。
OFFLINE_VERDICT_LEVELS = {"upstream_stall": "高风险", "link_dispatch_drop": "高风险",
                          "downstream_stall": "高风险", "stream_buf_backpressure": "高风险"}


def ivps_tail_filter(sample, grp, chn):
    """IVPS 某个 `(grp, chn)` 链路的末尾 filter：FltId 最大的一级，它的输出才进 link。"""
    rows = [row for row in sample["ivps"].get("filter_state", [])
            if row.get("GrpId") == grp and row.get("ChnId") == chn]
    if not rows:
        return None
    return max(rows, key=lambda row: row["FltId"] if isinstance(row.get("FltId"), int) else -1)


def ivps_chn_info(sample, grp, chn):
    for row in sample["ivps"].get("chn_info", []):
        if row.get("GrpId") == grp and row.get("ChnId") == chn:
            return row
    return None


def offline_upstream(sample, link):
    """offline 链路的上游：IVPS 输出通道的末尾 filter 计数与 CHN INFO 输出积压。"""
    source = link["src"]
    if source["module"] != "IVPS":
        return None
    tail = ivps_tail_filter(sample, source["grp"], source["chn"])
    if tail is None:
        return None
    info = ivps_chn_info(sample, source["grp"], source["chn"]) or {}
    return {"grp": source["grp"], "chn": source["chn"], "filter": tail.get("FltId"),
            "engine": tail.get("Engine"), "in_cnt": tail.get("InCnt"),
            "out_cnt": tail.get("OutCnt"), "fail1": tail.get("Fail1"), "fail2": tail.get("Fail2"),
            "out_sts": info.get("OutSts"), "out_depth": info.get("OutDepth"),
            "frc_mode": info.get("FrcMode"), "frc": info.get("Frc(src:dst)"),
            "out_fps": info.get("OutFps")}


def offline_downstream(sample, link):
    """offline 链路的下游：编码器通道的接收、送编码、取流与错误计数。"""
    module = link["consumer"].lower()
    if module not in ("venc", "jenc"):
        return None
    channel = next((item for item in sample[module]["channels"]
                    if item["id"] == link["dst"]["chn"]), None)
    if channel is None:
        return None
    status0 = channel.get("status0") or {}
    status1 = channel.get("status1") or {}
    status2 = channel.get("status2") or {}
    stream = channel.get("stream_buf") or {}
    rc = channel.get("rc") or {}
    return {"module": module, "chn": link["dst"]["chn"],
            "rc_mode": rc.get("RcMode"), "src_fr": rc.get("SrcFr"), "dst_fr": rc.get("DstFr"),
            # 配置的目的帧率就是这一路编码应有的输出速率，用来区分低帧率是配置还是停滞。
            "out_fps": status2.get("OutFps"),
            "recv": status2.get("FrmRecv"), "submit": status2.get("SubMitCnt"),
            "submit_fail": status2.get("SubMitFail"), "wait_fail": status2.get("WaitEncFail"),
            "seq_discont": status2.get("SeqDiscont"),
            "send_fail": status0.get("Send2EncFail") if module == "venc" else status1.get("EncFail"),
            "timeout": status0.get("TimeOutCnt") if module == "venc" else status1.get("TimeOutCnt"),
            "buf_full": status0.get("BufFullCnt"), "busy": status1.get("BusyCnt"),
            "read_cycle": stream.get("ReadCycle"), "aval_r_size": stream.get("AvalRSize"),
            "hw_used": stream.get("HwUsed")}


def build_offline_links(sample):
    """SKILL.md 第 3.2 节：非 HSK 绑定的 IVPS->编码器链路，按业务计数判定数据流。

    只有 `SW_Offline` 走业务计数路径；`HW_Online`/`Mode_Unset` 仅标注模式，不下卡死结论。
    """
    links = []
    for link in sample["topology"]["non_hsk_links"]:
        entry = {"src": link["src"], "dst": link["dst"], "consumer": link["consumer"],
                 "mode": link["mode"], "line": link["line"], "verdict": None, "evidence": None,
                 "upstream": offline_upstream(sample, link),
                 "downstream": offline_downstream(sample, link)}
        if link["mode"] != OFFLINE_MODE:
            entry["evidence"] = ("%s 绑定不做数据流判定；只有 SW_Offline 走业务计数路径"
                                 % link["mode"])
        links.append(entry)
    return links


def counter_summary(pairs):
    """只列出取到的计数，避免把 `X=None` 写进结论文本。"""
    listed = ["%s=%s" % (name, value) for name, value in pairs if value is not None]
    return " ".join(listed) if listed else "无可用计数"


def rate_hint(upstream, downstream):
    """配置帧率提示（第 3.2 节）：低 OutFps 只有和配置比对过才谈得上是不是停滞。

    IVPS 的抽帧（`FrcMode`/`Frc(src:dst)`）和编码器的 `SrcFr`/`DstFr` 是两处独立的配置，
    真正的故障判定必须拿两个 OutFps 去比，而不是看绝对帧率高低。
    IVPS CHN INFO 的 InFps/OutFps 是 proc_snapshot 快照，帧流停了仍保留最后一次计算结果
    （健康采样里读 29.99，停流采样里读成配置值 30.0），所以只作参考，不能当实时速率。
    """
    parts = []
    if upstream:
        frc = " ".join(str(item) for item in (upstream.get("frc_mode"), upstream.get("frc"))
                       if item is not None)
        if frc:
            parts.append("IVPS 抽帧 %s" % frc)
        if upstream.get("out_fps") is not None:
            parts.append("IVPS OutFps 快照=%s" % upstream["out_fps"])
    if downstream:
        if downstream.get("src_fr") is not None or downstream.get("dst_fr") is not None:
            parts.append("编码配置 Src/Dst=%s/%s fps"
                         % (downstream.get("src_fr"), downstream.get("dst_fr")))
        if downstream.get("out_fps") is not None:
            parts.append("编码 OutFps=%s" % downstream["out_fps"])
    return "，".join(parts) if parts else "未采集到帧率配置"


def classify_offline_link(link, delta_map):
    """按 S1 -> S2 的业务计数差值定位 offline 链路卡在哪一段；返回 (verdict, evidence)。

    数据流方向：IVPS filter 输出 -> link 派发（同步回调传共享内存块）-> 编码器接收 ->
    送编码 -> 码流取出。任一段前面推进而后面不推进，问题就落在后面那一段。
    """
    if link["mode"] != OFFLINE_MODE:
        return None, link["evidence"]
    upstream, downstream = link["upstream"], link["downstream"]
    if not upstream or not downstream:
        return "insufficient_evidence", "缺少该链路 IVPS 或编码器对应通道的 proc，无法建立数据流判定"

    def moved(key):
        item = delta_map.get(key)
        return None if item is None else item["delta"]

    prefix = "ivps/grp%s/chn%s/flt%s" % (upstream["grp"], upstream["chn"], upstream["filter"])
    encoder = "%s/chn%s" % (downstream["module"], downstream["chn"])
    in_move = moved("%s/InCnt" % prefix)
    out_move = moved("%s/OutCnt" % prefix)
    recv = moved("%s/FrmRecv" % encoder)
    submit = moved("%s/SubMitCnt" % encoder)
    read = moved("%s/ReadCycle" % encoder)
    aval = moved("%s/AvalRSize" % encoder)
    if out_move is None or recv is None:
        return "insufficient_evidence", "IVPS 输出或编码器接收计数在两次采样间无法对齐，判定受限"
    if out_move == 0 and in_move == 0:
        return "no_input", ("IVPS filter %s 的 InCnt/OutCnt 两轮都不变（%s），"
                            "该通道没有新的输出，先看 VIN 与上游 filter；配置帧率本身很低时"
                            "请延长采样间隔后再判"
                            % (upstream["filter"], rate_hint(upstream, downstream)))
    if out_move == 0:
        return "upstream_stall", ("IVPS filter %s 有输入但 OutCnt 不推进（%s），阻塞在 IVPS 这一级"
                                  % (upstream["filter"],
                                     counter_summary((("Fail1", upstream["fail1"]),
                                                      ("Fail2", upstream["fail2"])))))
    if recv == 0:
        return "link_dispatch_drop", ("IVPS 输出在推进但编码器 FrmRecv 不变；offline 靠同步回调"
                                      "派发共享内存块，丢帧只留 syslog 的 `Chn %%d busy!/full!`，"
                                      "同时看 IVPS 输出积压（%s）"
                                      % counter_summary((("OutSts", upstream["out_sts"]),
                                                         ("OutDepth", upstream["out_depth"]))))
    if submit is None:
        return "insufficient_evidence", "编码器 CHN STATUS 2 缺少 SubMitCnt，无法判断送编码是否推进"
    if submit == 0:
        return "downstream_stall", ("编码器已接收（FrmRecv 增长）但 SubMitCnt 不推进；%s"
                                    % counter_summary((("Send2EncFail", downstream["send_fail"]),
                                                       ("BufFullCnt", downstream["buf_full"]),
                                                       ("TimeOutCnt", downstream["timeout"]),
                                                       ("BusyCnt", downstream["busy"]))))
    if read == 0 and (aval or 0) > 0:
        return "stream_buf_backpressure", ("编码已完成但 ReadCycle 不推进、AvalRSize 仍在增加"
                                           "（HwUsed=%s）；优先判用户态取流/释放码流不及时"
                                           % downstream["hw_used"])
    return "progressing", ("IVPS 输出、编码器接收与送编码计数都在推进（%s）"
                           % rate_hint(upstream, downstream))


def classify_offline_links(sample, comparison, issues):
    """SKILL.md 第 3.2 节：把两轮采样的差值套到每条 offline 链路上并报告问题。"""
    delta_map = {item["key"]: item for item in comparison["deltas"]}
    for link in sample.get("offline_links", []):
        verdict, evidence = classify_offline_link(link, delta_map)
        link["verdict"] = verdict
        link["evidence"] = evidence
        level = OFFLINE_VERDICT_LEVELS.get(verdict) if verdict else None
        if not level:
            continue
        issues.append({"level": level,
                       "channel": "%s %s/%s -> %s %s/%s" % (
                           link["src"]["module"], link["src"]["grp"], link["src"]["chn"],
                           link["consumer"], link["dst"]["grp"], link["dst"]["chn"]),
                       "field": "offline 链路 %s" % verdict,
                       "message": evidence})


# 判断停滞只能看单调推进类字段；地址、QP、标志位等电平类字段不在其中。
MONOTONIC_FIELDS = ("hskCnt", "FrmRecv", "SubmitCnt", "SucCnt", "EncSucCnt", "Send2EncCnt",
                    "TotalCnt", "InCnt", "OutCnt", "ReadCycle", "WriteCycle")

CHANNEL_COUNTERS = {
    "venc": {"status0": ENCODER_COUNTERS["status0"], "status2": ENCODER_COUNTERS["status2"],
             "stream_buf": ENCODER_COUNTERS["stream_buf"]},
    "jenc": {"status1": ENCODER_COUNTERS["status1"], "status2": ENCODER_COUNTERS["status2"],
             "stream_buf": ENCODER_COUNTERS["stream_buf"]},
}


def collect_counters(sample):
    """把 S1/S2 需要比较的计数器摊平成 `模块/通道/字段` -> 数值。"""
    counters = {}
    for module, groups in CHANNEL_COUNTERS.items():
        for channel in sample[module]["channels"]:
            prefix = "%s/chn%s" % (module, channel["id"])
            for group, names in groups.items():
                row = channel.get(group)
                if not isinstance(row, dict):
                    continue
                for name in names:
                    if isinstance(row.get(name), int):
                        counters["%s/%s" % (prefix, name)] = row[name]
            for name in ENCODER_EXTRA_COUNTERS:
                value = (channel.get("hsk") or {}).get(name)
                if isinstance(value, int):
                    counters["%s/%s" % (prefix, name)] = value
    for row in sample["ivps"].get("filter_state", []):
        prefix = "ivps/grp%s/chn%s/flt%s" % (row.get("GrpId"), row.get("ChnId"), row.get("FltId"))
        for name in IVPS_COUNTERS:
            if isinstance(row.get(name), int):
                counters["%s/%s" % (prefix, name)] = row[name]
    for session in sample["syncagent"]["sessions"]:
        for name, value in session.get("info", {}).items():
            if not isinstance(value, list):
                continue
            for index, item in enumerate(value):
                if isinstance(item, int):
                    counters["syncagent/sess%s/%s[%d]" % (session["sess_id"], name, index)] = item
    return counters


def analyze_sample(sample, issues):
    sample_issues_start = len(issues)
    sample["topology"] = derive_topology(sample, issues)
    report_non_hsk_links(sample["topology"], issues)
    sample["offline_links"] = build_offline_links(sample)
    sessions = sample["syncagent"]["sessions"]
    hsk_channels = []
    for module in ("venc", "jenc"):
        for channel in sample[module]["channels"]:
            entry = {"module": module, "chn": channel["id"],
                     "hsk": channel.get("hsk"), "hsk_info": channel.get("hsk_info"),
                     "hsk_wait": channel.get("hsk_wait"), "rc": channel.get("rc")}
            entry.update(derive_hsk_channel(module, channel, sessions, issues))
            hsk_channels.append(entry)
    sample["hsk_channels"] = hsk_channels
    session_checks = []
    for session in sessions:
        check = {"sess_id": session["sess_id"], "state": session["state"],
                 "init_val": session.get("init_val")}
        check.update(derive_session(session, hsk_channels, issues))
        session_checks.append(check)
    sample["session_checks"] = session_checks
    sample["counters"] = collect_counters(sample)
    sample["issues"] = issues[sample_issues_start:]
    return sample


# 能证明帧确实流过某一级的计数字段：只要这些字段在涨，帧就已经到了这一级的下游。
FLOW_FIELDS = ("FrmRecv", "SubMitCnt", "SubmitCnt", "Send2EncCnt", "EncSucCnt", "SucCnt", "BsFrmCnt")


def pipeline_flow_note(sample, group, changed_keys):
    """SKILL.md 第 3.2 节：一组冻结的计数是否真的说明这一级停摆。

    帧流转要先看下游有没有收到帧。IVPS 某一级滤器的计数不变、但它的目的编码器还在收帧
    （`FrmRecv`/`SubMitCnt` 这类流转计数在涨），说明帧已经流过这一级，低内存握手下滤器
    计数本来就不逐帧更新，不能把这一级判成停摆。返回一句下游流转的证据，None 表示下游
    也不推进（或映射不到目的编码器），此时冻结计数才能当成停滞线索。
    """
    parts = group.split("/")
    if len(parts) < 3 or parts[0] != "ivps":
        return None
    try:
        grp = int(parts[1].removeprefix("grp"))
        chn = int(parts[2].removeprefix("chn"))
    except ValueError:
        return None
    for link in (sample.get("link_table") or {}).get("links") or []:
        src = link["src"]
        if src["module"] != "IVPS" or src["grp"] != grp or src["chn"] != chn:
            continue
        if consumer_of(link) not in ("VENC", "JENC"):
            continue
        actual = resolve_encoder_consumer(sample, (consumer_of(link),
                                                   link["dst"]["grp"], link["dst"]["chn"]))
        if actual is None:
            continue
        prefix = "%s/chn%s/" % (actual.lower(), link["dst"]["chn"])
        if any(key.startswith(prefix) and key.rsplit("/", 1)[1].split("[")[0] in FLOW_FIELDS
               for key in changed_keys):
            return "%s %s/%s 的目的编码器 %s chn%s 仍在收帧" % (src["module"], src["grp"],
                                                           src["chn"], actual, link["dst"]["chn"])
    return None


def compare_samples(previous, current, issues):
    """SKILL.md 第 3 节：对每个通道比较 S1 -> S2，确认计数是否持续不变。"""
    deltas = []
    for key in sorted(set(previous["counters"]) & set(current["counters"])):
        before, after = previous["counters"][key], current["counters"][key]
        deltas.append({"key": key, "s1": before, "s2": after, "delta": after - before})
    changed_keys = {item["key"] for item in deltas if item["delta"] != 0}
    groups = {}
    for item in deltas:
        group, field = item["key"].rsplit("/", 1)
        entry = groups.setdefault(group, {"group": group, "changed": [], "unchanged": []})
        # 只有单调推进类字段能用来判断停滞；地址、电平类字段不在其中。
        if field.split("[")[0] not in MONOTONIC_FIELDS:
            continue
        entry["changed" if item["delta"] != 0 else "unchanged"].append(field)
    stalled = [entry for entry in groups.values()
               if entry["unchanged"] and not entry["changed"]]
    for entry in sorted(stalled, key=lambda item: item["group"]):
        flowed = pipeline_flow_note(current, entry["group"], changed_keys)
        if flowed:
            issues.append({"level": "提示", "channel": entry["group"],
                           "field": "S1 -> S2 计数",
                           "message": "%s 的推进类计数在两轮采样间不变（%s），但%s，帧流没有断，"
                                      "不能据此把这一级判成停摆，停滞要往它的下游找"
                                      % (entry["group"], ", ".join(sorted(entry["unchanged"])), flowed)})
            continue
        issues.append({"level": "提示", "channel": entry["group"],
                       "field": "S1 -> S2 计数",
                       "message": "%s 的推进类计数在两轮采样间全部不变: %s；"
                                  "结合上下游判断该通道是否没有新的 HSK/编码工作"
                                  % (entry["group"], ", ".join(sorted(entry["unchanged"])))})
    compare_hold_release(previous, current, issues)
    return {"sample_pair": [previous["label"], current["label"]], "deltas": deltas,
            "groups": [groups[key] for key in sorted(groups)],
            "stalled_groups": sorted(entry["group"] for entry in stalled)}


def compare_hold_release(previous, current, issues):
    """SKILL.md 第 3 节：HoldCnt 与 ReleaseCnt 的差值持续扩大表示存在未释放的同步 hold。"""
    for old_session, new_session in zip(previous["syncagent"]["sessions"],
                                        current["syncagent"]["sessions"]):
        before = old_session.get("info", {})
        after = new_session.get("info", {})
        holds, releases = before.get("HoldCnt"), before.get("ReleaseCnt")
        next_holds, next_releases = after.get("HoldCnt"), after.get("ReleaseCnt")
        if not all(isinstance(item, list) for item in (holds, releases, next_holds, next_releases)):
            continue
        if len(holds) != len(releases) or len(next_holds) != len(next_releases):
            continue
        old_diff = [hold - release for hold, release in zip(holds, releases)]
        new_diff = [hold - release for hold, release in zip(next_holds, next_releases)]
        if all(isinstance(item, int) for item in old_diff + new_diff) and \
                any(after_diff > before_diff for before_diff, after_diff in zip(old_diff, new_diff)):
            issues.append({"level": "高风险", "channel": new_session["sess_id"],
                           "field": "syncagent HoldCnt/ReleaseCnt",
                           "message": "SessId %s 的 HoldCnt-ReleaseCnt 差值持续扩大（%s -> %s），"
                                      "存在未释放的同步 hold，优先看对应 wait 端和下游消费者"
                                      % (new_session["sess_id"], old_diff, new_diff)})


def dedupe_issues(issues):
    """多轮采样会让静态提示（缺 link_table_kernel、非 HSK 链路清单）逐轮重复；按内容去重。

    保留首次出现的顺序，报告里同一件事只说一次。
    """
    seen = set()
    unique = []
    for issue in issues:
        key = (issue.get("level"), issue.get("channel"), issue.get("field"), issue.get("message"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique


def parse(text):
    issues = []
    versions, order = sdk_versions(text)
    samples = split_samples(text)
    parsed = []
    for item in samples:
        sample = parse_sample(item["text"], issues)
        sample["label"] = item["label"]
        sample["marker"] = item["marker"]
        analyze_sample(sample, issues)
        parsed.append(sample)
    deltas = []
    for index in range(1, len(parsed)):
        comparison = compare_samples(parsed[index - 1], parsed[index], issues)
        classify_offline_links(parsed[index], comparison, issues)
        deltas.append(comparison)
    primary = versions.get(order[0]) if order else None
    if primary is None:
        issues.insert(0, {"level": "提示", "channel": None, "field": "SDK version",
                          "message": "proc 未输出 SDK 版本，版本相关结论需人工确认"})
    return {"environment": {"sdk_version": primary or "unknown",
                            "sdk_version_source": "proc [SDK version]" if primary else None,
                            "module_versions": versions,
                            "sample_count": len(parsed),
                            "sample_labels": [item["label"] for item in parsed],
                            "sample_marker_present": any(item["marker"] for item in parsed)},
            "samples": parsed, "deltas": deltas, "issues": dedupe_issues(issues),
            "coverage": {
                "modules": ["link_table", "link_table_kernel", "syncagent", "ivps", "venc",
                            "jenc"],
                "proc_sections": ["Link Table V2（用户态）+ Link Table Kernel V2（带 Engine）",
                                  "syncagent SESSION/CONNECT/INFO",
                                  "IVPS CHN INFO, FILTER STATE",
                                  "VENC CHN ATTR 2(EncW/EncH/SeqNum/PTS), CHN HSK STATUS, "
                                  "CHN STREAM BUF STATUS, CHN STATUS 0/2",
                                  "JENC CHN ATTR 2(EncW/EncH/SeqNum/PTS), CHN HSK STATUS, "
                                  "CHN STREAM BUF STATUS, CHN STATUS 1/2, FRAME LIST STATUS"],
                "excluded": ["保留规则：只输出本 SKILL.md 按名引用、或脚本判定逻辑实际使用的列",
                             "GOP、RC ATTR 2/3 等码控配置、CHN ATTR 1 的 Profile/Stride/Crop/"
                             "PixFmt/BufMode、耗时与带宽统计、节点池、IVPS INPUT FRAME/GRP/"
                             "FILTER/VPP/VGP/GDC/SCALE RANGE INFO——整表不参与 HSK 诊断",
                             "RC ATTR 1（VENC）/ RC ATTR（JENC）只取 RcMode/SrcFr/DstFr/"
                             "TargetBitRate，其余 Qp 与码率细节列不解析；IVPS CHN INFO 只取 "
                             "FrcMode/Frc(src:dst)/OutFps/OutSts/OutDepth",
                             "HSK STATUS 的 EncHPre/maxH/fMode/ringLCnt/saSize/waChn0/waChn1、"
                             "CONNECT 的 RegAddr/SliceNum、IVPS 的 En/InFps、STATUS 2 的 bRecv/"
                             "RecvFps、STREAM BUF 的 ReadPtr/WritePtr/AvalWSize/BufBusy、"
                             "FRAME LIST 的 toHwCnt/userCnt/ErrFrmStatus——同表内未使用的列"],
                "derived": ["握手高度/当前进度（16 位模 65536）与四种判定",
                            "链路的 Engine(src->dst) 与消费端模块（VENC/JENC 分支）",
                            "链路的 HSK/非 HSK 绑定（HSK_MODES，来自 VENC_CHECK_HSK_MODE）",
                            "非 HSK 链路（SW_Offline）的数据流判定：upstream_stall/"
                            "link_dispatch_drop/downstream_stall/stream_buf_backpressure/"
                            "no_input/insufficient_evidence",
                            "编码器 waitId/upId 与 syncagent ConId/ChnId 映射",
                            "waWaPhy0/waUpPhy0 与 syncagent SyncAddr 地址交叉核对",
                            "握手高度与 ceil(EncH/64)*64、sliceNum*minhskLin 的一致性",
                            "S1 -> S2 计数器差值"],
                "limits": ["HSK 形态结论基于 link_table 与 HSK STATUS 的 srcNum/等待分支，"
                           "syncagent 缺失时只能给出候选",
                           "未采到 link_table_kernel 时链路的 Engine 未知，消费端按目的通道落在"
                           "venc/jenc proc 的哪一侧归一；两侧都没有该通道时消费端待确认",
                           "非 HSK 绑定（SW_Offline/HW_Online/Mode_Unset）没有握手寄存器，"
                           "不做形态与握手判定；SW_Offline 改按业务计数判定数据流卡死，"
                           "判定需要两次采样，HW_Online/Mode_Unset 只标注模式",
                           "IVPS 侧没有「下游不消费」的反压计数（ivps_link_infifo_probe_callback "
                           "恒返回 FIFO_STATUS_NOT_FULL），只能靠 IVPS 输出与编码器接收/送编码"
                           "计数的联动推断",
                           "单次采样只能给出静态状态，不能表述为持续卡死",
                           "ahead=(vpp_update-vpp_wait)&0xFFFF 需要帧阶段信息，"
                           "仅凭静态 proc 无法判定，脚本不输出该结论"]}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="-", help="proc 文本文件，默认 stdin")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if args.input == "-":
        source = sys.stdin.read()
    else:
        with open(args.input, encoding="utf-8", errors="replace") as handle:
            source = handle.read()
    print(json.dumps(parse(source), ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
