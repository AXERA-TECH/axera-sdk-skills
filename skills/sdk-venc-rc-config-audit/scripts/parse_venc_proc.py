#!/usr/bin/env python3
"""Parse AX VENC proc text into stable JSON and flag obvious RC issues."""
import argparse
import json
import re
import sys


def num(value):
    if value in (None, "", "-"):
        return None
    try:
        return float(value) if "." in value else int(value, 0)
    except (TypeError, ValueError):
        return None


def typed(value):
    """Convert scalars while preserving range strings such as '[10,51]'."""
    if value in (None, "", "-", "N", "Y"):
        return value
    converted = num(value)
    return value if converted is None else converted


# Addresses and timestamps stay in the form proc printed them so a report can
# be matched against the raw text; convert with num() when a range check needs it.
RAW_FIELDS = ("QpMapPhyAddr", "QpMapVirAddr", "Pts")


def keep_raw(name, value):
    return value if name in RAW_FIELDS else typed(value)


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def sdk_version(text):
    """Read the SDK version banner printed above the proc tables."""
    match = re.search(r"^\s*\[?\s*SDK\s+version\s*\]?\s*[:：]\s*(\S.*?)\s*$", text, re.M | re.I)
    return match.group(1) if match else None


def column_offsets(header_line):
    """Leading offset of every column name in a proc table header."""
    return [match.start() for match in re.finditer(r"\S+", header_line)]


def continuation_start(line, offsets):
    """Column index a continuation line resumes at, or None when unclear.

    Headers and data share the same printf field widths, so the first token of
    a continuation line starts at the offset of the column it belongs to.
    """
    match = re.search(r"\S", line)
    if not match:
        return None
    start = match.start()
    return min(range(len(offsets)), key=lambda index: abs(offsets[index] - start))


def table(text, title, issues=None):
    marker = re.compile(r"^-{3,}.*%s.*\n" % re.escape(title), re.M)
    match = marker.search(text)
    if not match:
        return [], []
    tail = text[match.end():]
    next_match = re.search(r"^\s*-{3,}", tail, re.M)
    block = tail[: next_match.start()] if next_match else tail
    raw = [line.rstrip() for line in block.splitlines()
           if line.strip() and not re.fullmatch(r"[- ]+", line.strip())]
    if len(raw) < 2:
        return [], []
    # Users often paste proc output with a uniform indent; judge continuation
    # lines by their indent relative to the table, not to column 0.
    indent = min(len(line) - len(line.lstrip()) for line in raw)
    raw = [line[indent:] for line in raw]
    headers = raw[0].split()
    offsets = column_offsets(raw[0])
    rows = []
    for line in raw[1:]:
        stripped = line.strip()
        if stripped.startswith(("[", "VeChn", "ChnId")):
            continue
        values = stripped.split()
        if not values:
            continue
        if line[:1].isspace() and rows and len(offsets) == len(headers):
            # Multi-line record: leading columns are printed as blanks and only
            # the trailing columns carry values.
            start = continuation_start(line, offsets)
            if start is not None and start + len(values) == len(headers):
                previous = rows[-1]
                previous.setdefault("__continuation", []).append(
                    dict(zip(headers[start:], values)))
                continue
            if issues is not None:
                issues.append({"level": "错误", "channel": None, "field": f"表格 {title}",
                               "message": f"{title} 续行字段数({len(values)})无法对齐表头"
                                          f"({len(headers)} 列)，该行已跳过，结论需人工核对"})
            continue
        if re.match(r"^\d+$", values[0]):
            if len(values) != len(headers) and issues is not None:
                issues.append({"level": "错误", "channel": None, "field": f"表格 {title}",
                               "message": f"{title} 数据行字段数({len(values)})与表头"
                                          f"({len(headers)} 列)不匹配，字段可能错位，结论需人工核对"})
            row = dict(zip(headers, values))
            row["__values"] = values
            rows.append(row)
    return headers, rows


def parse(text):
    channels = {}
    issues = []

    _, attrs = table(text, "VENC CHN ATTR 1")
    for row in attrs:
        cid = int(row["ID"])
        values = row.get("__values", [])
        # Crop columns have changed between SDK versions. Recover trailing
        # fields from their stable value pattern instead of relying on offsets.
        pix_index = next((i for i in range(len(values) - 2)
                          if values[i + 1] in ("Y", "N") and
                          values[i + 2].upper() in ("FULL", "LIMIT", "LIMITED")), None)
        if pix_index is not None:
            row["PixFmt"] = values[pix_index]
            row["link"] = values[pix_index + 1]
            row["Range"] = values[pix_index + 2]
            if pix_index + 4 < len(values):
                row["BufMode"] = values[pix_index + 3]
                row["StrmBufSize(KB)"] = values[pix_index + 4]
        channels.setdefault(cid, {}).update({
            "id": cid, "codec": row.get("Type"), "profile": row.get("Profile"),
            "level": num(row.get("Level")), "width": num(row.get("wSrc")),
            "height": num(row.get("hSrc")), "pixfmt": row.get("PixFmt"),
            "buffer_mode": row.get("BufMode"), "stream_buffer_kb": num(row.get("StrmBufSize(KB)")),
        })

    _, rc = table(text, "VENC CHN RC ATTR 1")
    for row in rc:
        cid = int(row["ID"])
        item = channels.setdefault(cid, {"id": cid})
        item["rc"] = {key: (value if key in ("RcMode", "SvcEn") else typed(value))
                       for key, value in row.items() if key not in ("ID", "__values")}

    # QpDltRng 列在不同 SDK 版本打印成不同形态，两者取自不同字段，不能按同一
    # 字段比较：两列形态给出 Min/Max 两个边界，单列形态只给一个边界。这里只给
    # rc 打形态标记、不改数值字段，供范围检查与报告按形态处理。
    for item in channels.values():
        rc_cfg = item.get("rc")
        if not rc_cfg:
            continue
        if "QpDltRngMin" in rc_cfg or "QpDltRngMax" in rc_cfg:
            rc_cfg["QpDltRngShape"] = "min_max"
        elif "QpDltRng" in rc_cfg:
            rc_cfg["QpDltRngShape"] = "single"

    _, jpeg_rc = table(text, "JENC CHN RC ATTR")
    for row in jpeg_rc:
        if "ID" not in row:
            continue
        cid = int(row["ID"])
        channels.setdefault(cid, {"id": cid})["jpeg_rc"] = {
            key: (value if key in ("RcMode",) else typed(value))
            for key, value in row.items() if key not in ("ID", "__values")
        }

    # Alternate AX VPU proc format exposes the same H.26x controls as CTRL0/1/2.
    vpu_rc = {}
    for title, key in (("H26X RC CTRL0", "ctrl0"), ("H26X RC CTRL1", "ctrl1"),
                       ("H26X RC CTRL2", "ctrl2")):
        _, rows = table(text, title)
        for row in rows:
            if "ChnId" not in row:
                continue
            cid = int(row["ChnId"])
            vpu_rc.setdefault(cid, {})[key] = {
                name: (value if name in ("RcMode", "FixQp") else typed(value))
                for name, value in row.items() if name not in ("ChnId", "__values")
            }
    for cid, controls in vpu_rc.items():
        channels.setdefault(cid, {"id": cid})["vpu_rc"] = controls

    # QPMAP is printed in dedicated sections, not in RC ATTR 1.
    qpmap = {}
    for title, key in (("VENC CHN USER QPMAP1 INFO", "map1"),
                       ("VENC CHN USER QPMAP2 INFO", "map2"),
                       ("VENC CHN USER LocalMap INFO", "local_map")):
        _, rows = table(text, title, issues)
        for row in rows:
            if "ID" not in row:
                continue
            cid = int(row["ID"])
            qpmap.setdefault(cid, {})[key] = {
                name: keep_raw(name, value)
                for name, value in row.items()
                if name not in ("ID", "__values", "__continuation")
            }
    for cid, maps in qpmap.items():
        channels.setdefault(cid, {"id": cid})["qpmap"] = maps

    # SVC (智能编码) prints one parameter row per channel, with one extra line
    # per rectangle type, and one region row per ring-buffer snapshot, with one
    # extra line per rectangle.
    _, svc_param = table(text, "VENC CHN SVC PARAM INFO", issues)
    for row in svc_param:
        if "ID" not in row:
            continue
        cid = int(row["ID"])
        param = {name: typed(value) for name, value in row.items()
                 if name not in ("ID", "__values", "__continuation",
                                 "TypeId", "IQp", "PQp")}
        param["types"] = [{name: typed(value) for name, value in entry.items()}
                          for entry in [{"TypeId": row.get("TypeId"), "IQp": row.get("IQp"),
                                         "PQp": row.get("PQp")}] + row.get("__continuation", [])]
        channels.setdefault(cid, {"id": cid})["svc_param"] = param

    _, svc_region = table(text, "VENC CHN SVC REGION INFO", issues)
    for row in svc_region:
        if "ID" not in row:
            continue
        cid = int(row["ID"])
        rect_keys = ("RectIdx", "Type", "X", "Y", "Width", "Height")
        record = {name: keep_raw(name, value) for name, value in row.items()
                  if name not in ("ID", "__values", "__continuation") + rect_keys}
        record["rects"] = [{name: typed(entry.get(name)) for name in rect_keys}
                           for entry in [row] + row.get("__continuation", [])]
        channels.setdefault(cid, {"id": cid}).setdefault("svc_region", []).append(record)

    # Preserve ancillary controls that can change effective bitrate/quality.
    for title, key in (("VENC CHN RJ&SupFrm ATTR", "rj_superframe"),
                       ("VENC CHN ROI INFO", "roi")):
        _, rows = table(text, title, issues if key == "roi" else None)
        for row in rows:
            id_key = "ID" if "ID" in row else ("VeChn" if "VeChn" in row else None)
            if id_key is None:
                continue
            cid = int(row[id_key])
            channels.setdefault(cid, {"id": cid}).setdefault(key, []).append({
                name: typed(value) for name, value in row.items()
                if name not in ("ID", "VeChn", "__values", "__continuation")
            })

    for section, output_key in (("VENC CHN RC ATTR 2", "rc_attr2"),
                                ("VENC CHN RC ATTR 3", "rc_attr3")):
        _, extra = table(text, section)
        for row in extra:
            if "ID" not in row:
                continue
            cid = int(row["ID"])
            channels.setdefault(cid, {"id": cid})[output_key] = {
                key: typed(value)
                for key, value in row.items() if key not in ("ID", "__values")
            }

    _, gop = table(text, "VENC CHN GOP ATTR")
    for row in gop:
        cid = int(row["ID"])
        channels.setdefault(cid, {"id": cid})["gop"] = {
            "mode": row.get("GopMode"), "gop": num(row.get("Gop"))
        }

    _, status = table(text, "VENC CHN STATUS 2")
    for row in status:
        # STATUS 2 is followed by a NodeCnt table in some SDK versions.
        # Keep only rows carrying the bRecv state to avoid treating NodeCnt
        # values as frame-rate and bitrate metrics.
        if row.get("bRecv") not in ("Y", "N"):
            continue
        id_key = "ChnId" if "ChnId" in row else ("VeChn" if "VeChn" in row else None)
        if not id_key:
            continue
        cid = int(row[id_key])
        channels.setdefault(cid, {"id": cid})["status"] = {
            "recv_fps": num(row.get("RecvFps")), "out_fps": num(row.get("OutFps")),
            "bitrate_kbps": num(row.get("BitRate(kbps)")),
        }

    for cid, item in sorted(channels.items()):
        rc_cfg = item.get("rc", {})
        mode = str(rc_cfg.get("RcMode", "")).upper()
        for lo, hi, label in (("MinQp", "MaxQp", "QP"), ("MinIQp", "MaxIQp", "I QP")):
            low, high = rc_cfg.get(lo), rc_cfg.get(hi)
            # QVBR 等模式的专属列打印 '-'，非数值时跳过范围比较
            if numeric(low) and numeric(high) and (low < 0 or high > 51 or low > high):
                issues.append({"level": "错误", "channel": cid, "field": f"{lo}/{hi}",
                               "message": f"{label} 范围非法: {low}..{high}"})
        # QpDltRng（CU 相对 slice/帧级 QP 的差值范围）按形态判域，见
        # references/rc-mode-matrix.md：两列 Min∈[-16,0]/Max∈[0,16]，单列 [0,16]。
        delta_shape = rc_cfg.get("QpDltRngShape")
        if delta_shape == "min_max":
            low, high = rc_cfg.get("QpDltRngMin"), rc_cfg.get("QpDltRngMax")
            if numeric(low) and not -16 <= low <= 0:
                issues.append({"level": "错误", "channel": cid, "field": "QpDltRngMin",
                               "message": f"QpDltRngMin={low} 超出两列形态合法域 [-16,0]"})
            if numeric(high) and not 0 <= high <= 16:
                issues.append({"level": "错误", "channel": cid, "field": "QpDltRngMax",
                               "message": f"QpDltRngMax={high} 超出两列形态合法域 [0,16]"})
        elif delta_shape == "single":
            value = rc_cfg.get("QpDltRng")
            if numeric(value) and not 0 <= value <= 16:
                issues.append({"level": "提示", "channel": cid, "field": "QpDltRng",
                               "message": f"QpDltRng={value} 超出单列形态常见域 [0,16]；"
                                          f"单列取值随 SDK 版本不同，需结合版本确认"})
        target = rc_cfg.get("TargetBitRate")
        actual = item.get("status", {}).get("bitrate_kbps")
        if numeric(target) and numeric(actual):
            item["status"]["target_deviation_percent"] = round((actual - target) * 100 / target, 2)
        if mode in ("CBR", "AVBR") and numeric(target) and target <= 0:
            issues.append({"level": "错误", "channel": cid, "field": "TargetBitRate",
                           "message": f"{mode} 目标码率必须为正: {target}"})
        if item.get("gop", {}).get("gop") and item.get("rc", {}).get("DstFr"):
            item["gop"]["duration_seconds"] = round(item["gop"]["gop"] / item["rc"]["DstFr"], 3)

        status = item.get("status", {})
        runtime = {}
        for configured, measured, label in (("SrcFr", "recv_fps", "RecvFps"),
                                             ("DstFr", "out_fps", "OutFps")):
            expected, observed_value = rc_cfg.get(configured), status.get(measured)
            if expected and observed_value is not None:
                deviation = round((observed_value - expected) * 100 / expected, 2)
                runtime[f"{label}_deviation_percent"] = deviation
                if abs(deviation) > 10:
                    issues.append({"level": "提示", "channel": cid, "field": label,
                                   "message": f"实际 {label}={observed_value} 与配置 {configured}={expected} 偏差 {deviation}%"})
        bitrate_limit = target
        if mode in ("VBR", "AVBR", "CVBR"):
            bitrate_limit = rc_cfg.get("MaxBitRate")
        if numeric(bitrate_limit) and numeric(actual):
            runtime["bitrate_limit_kbps"] = bitrate_limit
            runtime["bitrate_over_limit_percent"] = round((actual - bitrate_limit) * 100 / bitrate_limit, 2)
            if actual > bitrate_limit * 1.1:
                issues.append({"level": "高风险", "channel": cid, "field": "BitRate(kbps)",
                               "message": f"实际码率 {actual} kbps 超过 {mode} 上限 {bitrate_limit} kbps 超过 10%"})
        if runtime:
            item["runtime_comparison"] = runtime

        # 智能编码 (SVC): 背景 QP 与按矩形类型分配的 QP。
        # 取值域来自 ax_venc_comm.h 的 AX_VENC_SVC_* 常量。
        svc = item.get("svc_param")
        if svc:
            absolute = svc.get("AbsQp") == "Y"
            low, high = (0, 51) if absolute else (-51, 51)
            label = "绝对 QP" if absolute else "相对 QP"
            type_num = svc.get("TypeNum")
            if numeric(type_num) and not 1 <= type_num <= 5:
                issues.append({"level": "错误", "channel": cid, "field": "SVC TypeNum",
                               "message": f"智能编码矩形类型数 {type_num} 超出 [1,5]"})
            entries = svc.get("types", [])
            if numeric(type_num) and len(entries) != type_num:
                issues.append({"level": "错误", "channel": cid, "field": "SVC TypeId",
                               "message": f"智能编码 QP 配置行数 {len(entries)} 与 TypeNum={type_num} 不一致"})
            for name in ("BgIQp", "BgPQp"):
                value = svc.get(name)
                if numeric(value) and not low <= value <= high:
                    issues.append({"level": "错误", "channel": cid, "field": f"SVC {name}",
                                   "message": f"智能编码背景 {name}={value} 超出{label}范围 [{low},{high}]"})
            for entry in entries:
                for name in ("IQp", "PQp"):
                    value = entry.get(name)
                    if numeric(value) and not low <= value <= high:
                        issues.append({"level": "错误", "channel": cid,
                                       "field": f"SVC TYPE{entry.get('TypeId')} {name}",
                                       "message": f"智能编码 TYPE{entry.get('TypeId')} {name}={value} "
                                                  f"超出{label}范围 [{low},{high}]"})
            if item.get("rc", {}).get("SvcEn") == "N":
                issues.append({"level": "提示", "channel": cid, "field": "SvcEn",
                               "message": "RC ATTR 1 的 SvcEn=N 但 proc 输出了智能编码表，需确认使能状态"})

        for record in item.get("svc_region", []):
            rect_num = record.get("RectNum")
            if numeric(rect_num) and not 0 <= rect_num <= 32:
                issues.append({"level": "错误", "channel": cid, "field": "SVC RectNum",
                               "message": f"智能编码区域数 {rect_num} 超出 [0,32]"})
            rects = record.get("rects", [])
            if numeric(rect_num) and rect_num and len(rects) != rect_num:
                issues.append({"level": "错误", "channel": cid, "field": "SVC RectIdx",
                               "message": f"智能编码区域行数 {len(rects)} 与 RectNum={rect_num} 不一致"})
            for rect in rects:
                kind = rect.get("Type")
                if numeric(kind) and not 0 <= kind <= 4:
                    issues.append({"level": "错误", "channel": cid, "field": "SVC Type",
                                   "message": f"智能编码矩形类型 {kind} 超出 TYPE0..TYPE4"})
                if any(numeric(rect.get(name)) and rect[name] <= 0 for name in ("Width", "Height")):
                    issues.append({"level": "高风险", "channel": cid, "field": "SVC Rect",
                                   "message": f"智能编码区域 RectIdx={rect.get('RectIdx')} "
                                              f"宽高非正: {rect.get('Width')}x{rect.get('Height')}"})

        for name, maps in sorted(item.get("qpmap", {}).items()):
            for field in ("MbWidth", "MapSize"):
                value = maps.get(field)
                if numeric(value) and value <= 0:
                    issues.append({"level": "错误", "channel": cid, "field": f"QPMAP {field}",
                                   "message": f"{name} 的 {field}={value} 必须为正"})
            if num(maps.get("QpMapPhyAddr")) == 0:
                issues.append({"level": "错误", "channel": cid, "field": "QpMapPhyAddr",
                               "message": f"{name} 已启用但物理地址为 0"})

    observed = set()
    for item in channels.values():
        if item.get("rc", {}).get("RcMode") not in (None, "-"):
            observed.add(str(item["rc"]["RcMode"]).upper())
        if item.get("jpeg_rc", {}).get("RcMode") not in (None, "-"):
            observed.add(str(item["jpeg_rc"]["RcMode"]).upper())
        if item.get("vpu_rc", {}).get("ctrl0", {}).get("RcMode") not in (None, "-"):
            observed.add(str(item["vpu_rc"]["ctrl0"]["RcMode"]).upper())
    version = sdk_version(text)
    if version is None:
        issues.insert(0, {"level": "提示", "channel": None, "field": "SDK version",
                          "message": "proc 未输出 SDK 版本，版本相关结论需人工确认"})

    return {"environment": {"sdk_version": version or "unknown",
                            "sdk_version_source": "proc [SDK version]" if version else None},
            "channels": list(channels.values()), "issues": issues,
            "coverage": {
                "observed_modes": sorted(observed),
                "api_modes": ["H264/H265 CBR", "H264/H265 VBR", "H264/H265 AVBR",
                              "H264/H265 QVBR", "H264/H265 CVBR", "H264/H265 FIXQP",
                              "H264/H265 QPMAP", "MJPEG CBR", "MJPEG VBR", "MJPEG FIXQP"],
                "proc_sections": ["VENC RC ATTR 1/2/3", "VENC GOP ATTR",
                                  "VENC USER QPMAP1/2/LocalMap", "VENC ROI INFO",
                                  "VENC SVC PARAM/REGION INFO", "JENC RC ATTR",
                                  "H26X RC CTRL0/1/2"],
                "mode_gaps": ["QVBR 在 VENC RC ATTR 1 中输出为 '-'，需结合版本或 API 侧配置确认",
                              "QPMAP 通过独立 USER QPMAP 表确认，不能仅看 RcMode",
                              "智能编码(SVC) 叠加在当前 RcMode 之上，通过 SVC PARAM/REGION 表确认，"
                              "不是独立 RcMode；proc 未输出 QPMAP 的 block unit 与 QP 类型，需结合 API 确认"]
            }}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="-", help="proc 文本文件，默认 stdin")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    source = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8", errors="replace").read()
    print(json.dumps(parse(source), ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
