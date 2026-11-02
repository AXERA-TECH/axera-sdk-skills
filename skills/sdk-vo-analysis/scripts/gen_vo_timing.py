#!/usr/bin/env python3
"""AX615 VO 时序正向求解 — sdk-vo-setting 配置生成专用。

用法：
  gen_vo_timing.py --intf bt656 --res 1920x1080 --fps 30
  gen_vo_timing.py --intf dpi --fmt rgb565 --res 800x480 --fps 60   # 并行 DPI 须显式 --fmt
  gen_vo_timing.py --intf dpi --fmt srgb565 --res 640x480 --fps 30 --chip AX615D
  gen_vo_timing.py --json '{"intf":"bt656","hact":1920,"vact":1080,"fps":30}'
  gen_vo_timing.py --json '<完整时序字段>' --verify   # 校验任意给定参数

格式约定：BT 系只支持 yuv422（缺省即 yuv422）；DPI/srgb 必须显式给 fmt
（并行 rgb565，串行 srgb565/srgb666/srgb565s/srgb888/srgb888a/srgb888b），
缺格式按缺失拒绝，不假定并行倍率。

三级求解策略（可信度递减）：
1) 精确查表：条目名显式标注同接口、分辨率相等，且配置公式刷新率相对误差 ≤2%
   （source=table；未标注接口的条目、表内缺 bDlbClk 等字段的条目一律不作命中，
   只记入 skipped_entries）
2) 近邻推导：未命中时在 PCLK 离散档位表内枚举可达时钟，用字段完整、逐行且 SDR 的
   同分辨率/近邻条目 porch 作模板缩放，仅保留配置公式刷新率与目标相对误差 ≤2% 且
   通过合法性复核（字段/位宽/尺寸/档位表）的候选（source=derived，须实机验证）
3) 参数校验：给定完整参数时计算实际刷新率/档位表命中/能力与尺寸约束
   （能力闸门按**配置公式刷新率**判定，与 check_vo_timing.py 一致：
   如 AX615D 串行 sRGB 的 640x480@30 上限；刷新率不可计算时不绕过闸门）

数据内化于本 skill（references/ax615/vo-timing-table.json，54 组；另交叉参考
sample-vo-timings.json 官方 sample 19 组；PCLK 离散档位表 vo-pclk-table.json），
运行时不依赖任何外部目录。版本提示：SDK V3.14.0 实现行为，需按版本核验。

退出码：0 = 求解/校验成功；1 = 未找到满足 ≤2% 目标误差的候选（搜索失败不构成能力
证明，未扩展 DDR 搜索）；2 = 可预期错误（输入/格式/能力/缺字段，结构化 JSON 输出）。
"""
import argparse
import json
import os
import sys

try:
    from timing_common import (DPI_FMT_FACTOR, INTERFACES, TIMING_KEYS,
                               TimingError, actual_refresh, capability_errors,
                               dataset_issues, normalize_chip,
                               normalize_interface, refresh_factor,
                               refresh_formula, resolve_format,
                               validate_positive_number, validate_resolution,
                               validate_timing)
except ImportError:
    from scripts.timing_common import (DPI_FMT_FACTOR, INTERFACES, TIMING_KEYS,
                                       TimingError, actual_refresh,
                                       capability_errors, dataset_issues,
                                       normalize_chip, normalize_interface,
                                       refresh_factor, refresh_formula,
                                       resolve_format,
                                       validate_positive_number,
                                       validate_resolution, validate_timing)

_HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.normpath(os.path.join(_HERE, "..", "references", "ax615"))
SYNC_INFOS = os.path.join(REF, "vo-timing-table.json")
PCLK_TABLE = os.path.join(REF, "vo-pclk-table.json")
VERSION_MANIFEST = os.path.join(REF, "version-manifest.json")

# 目标误差门槛：配置公式刷新率与目标帧率的相对误差 ≤2%
FPS_TOLERANCE_RATIO = 0.02

# 接口后缀 → 表条目名匹配模式（未带后缀的条目不视为任何接口的已验证条目）
INTF_TAG = {
    "bt656": "_bt656",
    "bt601": "_bt601",
    "bt1120": "_bt1120",
    "dpi": "_dpi",
    "srgb": "_srgb",
}


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as error:
        raise TimingError(f"数据文件读取失败: {path}: {error}",
                          code="data_load_failed") from error


def load_version_hint():
    return _load(VERSION_MANIFEST)["canonical_version_note"]


def load_sync_infos():
    data = _load(SYNC_INFOS)
    return data["entries"], data.get("_meta", {})


def load_pclk_table():
    """PCLK 精确离散档位表（5 源 × 16 分频，取整商；不再要求整除）。"""
    data = _load(PCLK_TABLE)
    reachable = data.get("reachable_pclk_khz", [])
    deriv = {}
    for c in data.get("combos", []):
        deriv.setdefault(c["pclk_khz"], (c["source_khz"], c["divider"]))
    return reachable, deriv, data.get("_meta", {})


def data_consistency():
    """核对两份内化数据的版本与条目数是否与 version-manifest 一致。"""
    manifest = _load(VERSION_MANIFEST)
    entries, sync_meta = load_sync_infos()
    reachable, _, pclk_meta = load_pclk_table()
    datasets = {
        "vo-timing-table.json": {
            "sdk_version": sync_meta.get("sdk_version"),
            "declared_count": sync_meta.get("count"),
            "actual_count": len(entries),
        },
        "vo-pclk-table.json": {
            "sdk_version": pclk_meta.get("sdk_version"),
            "declared_count": pclk_meta.get("count_reachable"),
            "actual_count": len(reachable),
        },
    }
    return dataset_issues(manifest, datasets)


def all_reachable_pclk(reachable):
    """档位表全部可达时钟，降序。"""
    return sorted(reachable, reverse=True)


def pclk_in_table(pclk, reachable, deriv):
    """精确命中 PCLK 离散档位表；返回 (命中?, 源, 分频)。"""
    if pclk in reachable:
        src, div = deriv.get(pclk, ("?", "?"))
        return True, src, div
    return False, 0, 0


def intf_of_name(name):
    """从条目名推断接口；未标注接口返回 None（不得冒充任何接口的已验证条目）。"""
    for intf, tag in INTF_TAG.items():
        if tag in name:
            return normalize_interface(intf)
    return None


def _entry_missing_keys(entry):
    return [key for key in TIMING_KEYS if entry.get(key) is None]


def find_exact(entries, intf, hact, vact, fps, fmt=None):
    """精确命中：条目名显式同接口 + 分辨率相等 + 配置公式刷新率相对误差 ≤2%。

    返回 (hits, skipped)：hits 元素为 (相对误差, 条目名, 参数, 实际刷新率)，按误差升序；
    未标注接口的条目、表内缺 bDlbClk 等字段的条目不作命中，记入 skipped。
    """
    normalized_intf = normalize_interface(intf)
    normalized_fmt = resolve_format(normalized_intf, fmt)
    hits, skipped = [], []
    for name, e in entries.items():
        if e.get("u16Hact") != hact or e.get("u16Vact") != vact:
            continue
        e_intf = intf_of_name(name)
        if e_intf is None:
            skipped.append((name, "条目名未标注接口，不能作为该接口的已验证命中"))
            continue
        if e_intf != normalized_intf:
            continue
        missing = _entry_missing_keys(e)
        if missing:
            skipped.append((name, "表未记录字段 " + ",".join(missing)
                            + "（unknown，不得当作已验证配置）"))
            continue
        _, _, actual, notes = refresh_formula(e, e_intf, normalized_fmt)
        if actual is None:
            skipped.append((name, "；".join(notes)))
            continue
        ratio = abs(actual - fps) / fps
        if ratio > FPS_TOLERANCE_RATIO:
            continue
        hits.append((ratio, name, e, actual))
    hits.sort(key=lambda item: (item[0], item[1]))
    return hits, skipped


def derive(entries, reachable, intf, hact, vact, fps, fmt=None):
    """近邻推导：仅用字段完整、逐行(bIop=1)且 SDR(bDlbClk=0) 的条目作模板，不扩展 DDR 搜索。

    对每个档位表 pclk × 模板，反推 htotal（微调 hfp），必要时反推 vtotal（微调 vfp），
    仅保留配置公式刷新率相对误差 ≤2% 且通过合法性复核的候选。
    返回 (模板名, 候选列表, 被排除的模板/条目, 说明)。
    """
    normalized_intf = normalize_interface(intf)
    normalized_fmt = resolve_format(normalized_intf, fmt)
    factor = refresh_factor(normalized_intf, normalized_fmt, 0)  # 候选显式 bDlbClk=0（SDR）

    tpls, skipped = [], []
    for name, e in entries.items():
        missing = _entry_missing_keys(e)
        if missing:
            skipped.append((name, "表未记录字段 " + ",".join(missing) + "（不作模板）"))
            continue
        if e.get("bIop") != 1 or e.get("bDlbClk") != 0:
            continue
        same_res = e["u16Hact"] == hact and e["u16Vact"] == vact
        dist = abs(e["u16Hact"] - hact) + abs(e["u16Vact"] - vact)
        tpls.append((0 if same_res else 1, dist, name, e))
    tpls.sort()
    same = [(t[2], t[3]) for t in tpls if t[0] == 0]
    seen, near = set(), []
    for t in tpls:
        if t[0] == 0:
            continue
        key = (t[3]["u16Hact"], t[3]["u16Vact"])
        if key in seen:
            continue
        seen.add(key)
        near.append((t[2], t[3]))
    tpls = (same + near)[:8]

    notes = []
    if skipped:
        notes.append(f"{len(skipped)} 个表条目因缺字段（unknown）被排除，"
                     "未作模板/命中")
    if not tpls:
        notes.append("无可用模板：表内没有字段完整、逐行且 SDR 的条目")
        return None, [], skipped, notes

    results, seen_keys = [], set()

    def record(params, tpl_name):
        problems = validate_timing(params, require_all=True)
        if params["u32Pclk"] not in reachable:
            problems.append("u32Pclk 不在离散档位表")
        _, _, actual, refresh_notes = refresh_formula(params, normalized_intf,
                                                      normalized_fmt)
        if actual is None:
            problems.extend(refresh_notes)
            return
        if problems:
            return
        key = (params["u32Pclk"], params["u16Hbb"], params["u16Hfb"],
               params["u16Vbb"], params["u16Vfb"])
        if key in seen_keys:
            return
        ratio = abs(actual - fps) / fps
        if ratio > FPS_TOLERANCE_RATIO:
            return
        seen_keys.add(key)
        results.append({
            "fps_error": round(abs(actual - fps), 3),
            "fps_error_ratio": round(ratio, 5),
            "actual_fps": round(actual, 2),
            "htotal": params["u16Hact"] + params["u16Hbb"] + params["u16Hfb"]
            + params["u16Hpw"],
            "vtotal": params["u16Vact"] + params["u16Vbb"] + params["u16Vfb"]
            + params["u16Vpw"],
            "params": params,
            "template": tpl_name,
            "validity": "字段/位宽/尺寸/PCLK 档位复核通过",
        })

    for pclk in all_reachable_pclk(reachable):
        for tpl_name, tpl in tpls:
            vtotal = tpl["u16Vact"] + tpl["u16Vbb"] + tpl["u16Vfb"] + tpl["u16Vpw"]
            htotal = tpl["u16Hact"] + tpl["u16Hbb"] + tpl["u16Hfb"] + tpl["u16Hpw"]
            # 反推 htotal 目标（模板 vtotal 固定），hfp 承担全部调整
            htotal_t = round(pclk * 1000 / (vtotal * fps * factor))
            if 0.75 * htotal <= htotal_t <= 1.25 * htotal:
                hfp = htotal_t - hact - tpl["u16Hbb"] - tpl["u16Hpw"]
                if hfp >= 1:
                    record({
                        "bIop": 1,
                        "u16Vact": vact,
                        "u16Vbb": tpl["u16Vbb"],
                        "u16Vfb": tpl["u16Vfb"],
                        "u16Hact": hact,
                        "u16Hbb": tpl["u16Hbb"],
                        "u16Hfb": hfp,
                        "u16Hpw": tpl["u16Hpw"],
                        "u16Vpw": tpl["u16Vpw"],
                        "u32Pclk": pclk,
                        "bIdv": tpl["bIdv"],
                        "bIhs": tpl["bIhs"],
                        "bIvs": tpl["bIvs"],
                        "bDlbClk": 0,
                    }, tpl_name)
            # hfp 无解时：vtotal 也放开（vfp 承担垂直调整），hfp 保持 ≥1
            vtotal_t = round(pclk * 1000 / (htotal * fps * factor))
            if 0.75 * vtotal <= vtotal_t <= 1.25 * vtotal:
                vfp = vtotal_t - vact - tpl["u16Vbb"] - tpl["u16Vpw"]
                if vfp >= 1:
                    record({
                        "bIop": 1,
                        "u16Vact": vact,
                        "u16Vbb": tpl["u16Vbb"],
                        "u16Vfb": vfp,
                        "u16Hact": hact,
                        "u16Hbb": tpl["u16Hbb"],
                        "u16Hfb": tpl["u16Hfb"],
                        "u16Hpw": tpl["u16Hpw"],
                        "u16Vpw": tpl["u16Vpw"],
                        "u32Pclk": pclk,
                        "bIdv": tpl["bIdv"],
                        "bIhs": tpl["bIhs"],
                        "bIvs": tpl["bIvs"],
                        "bDlbClk": 0,
                    }, tpl_name)

    results.sort(key=lambda r: (r["fps_error"], r["htotal"] * r["vtotal"]))
    if not results:
        notes.append(f"当前模板/档位表组合内无解（仅 SDR 搜索，未扩展 DDR）；"
                     "搜索失败不构成能力证明")
    return (results[0]["template"] if results else None), results[:3], skipped, notes


def verify(p, intf, fmt, reachable, deriv, version_hint, chip=None):
    """校验给定完整参数：返回 (htotal, vtotal, fps, hints, problems)。

    problems 非空表示存在确定性非法项（如 PCLK 不命中离散档位表）。
    """
    htotal, vtotal, f, notes = refresh_formula(p, intf, fmt)
    if f is None:
        raise TimingError("；".join(notes) or "刷新率无法计算",
                          code="unknown_refresh",
                          details={"unknown_fields": ["bDlbClk"]})
    hints = list(notes)
    problems = []
    ok, src, div = pclk_in_table(p["u32Pclk"], reachable, deriv)
    if not ok:
        near = min(reachable, key=lambda v: abs(v - p["u32Pclk"]))
        problems.append(f"[PCLK] ✗ {p['u32Pclk']} 不在离散档位表（不精确命中即失败；"
                        f"公开 API 侧表现为 AX_ERR_VO_DEV_OP_FAIL，需结合 dmesg 的 "
                        f"unsupport clk 定位），最近可达 {near}")
    else:
        hints.append(f"[PCLK] ✓ {p['u32Pclk']} 精确命中（源 {src} ÷ {div}）")
    if p.get("bIop") != 1:
        hints.append("[bIop] 注意 bIop=0 隔行：垂直时序被改写（vbp/vfp/vpw 减半、"
                     "有效高减半），逐行屏需 bIop=1")
    if intf in ("bt656", "bt601") and fmt == "yuv422" and p.get("bDlbClk"):
        hints.append("[dblclk] BT656/601 DDR 模式：u32Pclk=像素时钟（不×2），"
                     "u8DelaySel 按所选表条目取值（不得简化为 DDR=3）")
    if intf in ("bt656", "bt601") and fmt == "yuv422" and not p.get("bDlbClk"):
        hints.append("[dblclk] BT656/601 SDR 模式：u32Pclk=像素时钟×2（每时钟 1 字节）")
    if intf == "dpi":
        fac = DPI_FMT_FACTOR.get(fmt)
        if fac is None:
            problems.append(f"[fmt] DPI 不支持格式 {fmt}")
        elif fac > 1:
            hints.append(f"[fmt] DPI 串行 {fmt}：配置公式刷新率已 ÷{fac}；"
                         "u32Pclk 仍须精确命中离散档位表")
    if chip is None:
        hints.append("[chip] 未提供芯片型号：未做 AX615D 能力边界判断")
    elif normalize_chip(chip) == "ax615d":
        hints.append("[chip] AX615D：BT1120/并行 DPI 不支持；串行 sRGB ≤640x480@30")
    hints.append(f"[版本] 刷新率为配置公式值（{version_hint}）；实际输出以 proc 的 "
                 f"Refresh/OutFps 与 VSYNC 实测为准")
    return htotal, vtotal, f, hints, problems


def emit_json(out):
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _load_json_arg(raw):
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise TimingError(f"--json 不是合法 JSON: {error}",
                          code="invalid_json") from error
    if not isinstance(value, dict):
        raise TimingError("--json 顶层必须是 JSON object（当前为 "
                          f"{type(value).__name__}）", code="invalid_json")
    return value


def _parse_res(raw):
    try:
        width, height = str(raw).lower().split("x")
        return int(width), int(height)
    except ValueError as error:
        raise TimingError(f"--res 格式应为 WxH: {raw}",
                          code="invalid_input") from error


def _number_field(j, key, integer=False):
    value = j.get(key)
    problem = validate_positive_number(value, key)
    if problem is None and integer and not isinstance(value, int):
        problem = f"{key} 必须是整数"
    if problem:
        raise TimingError(problem, code="invalid_input")
    return int(value) if integer else float(value)


def main() -> int:
    ap = argparse.ArgumentParser(description="AX615 VO 时序正向求解")
    ap.add_argument("--intf", choices=["bt656", "bt601", "bt1120", "dpi", "srgb"],
                    help="输出接口（srgb 为 dpi 串行 sRGB 别名）")
    ap.add_argument("--res", help="分辨率 WxH")
    ap.add_argument("--fps", type=float, help="目标帧率")
    ap.add_argument("--fmt", default=None,
                    help="输出格式；默认 BT 系 yuv422、dpi/srgb rgb565（并行）")
    ap.add_argument("--chip", default=None,
                    help="芯片型号（可选 AX615D/AX615Q；未提供时不按芯片能力过滤）")
    ap.add_argument("--json", help="JSON 输入：求解场景或完整参数（--verify）")
    ap.add_argument("--verify", action="store_true", help="校验完整参数模式")
    args = ap.parse_args()

    try:
        j = _load_json_arg(args.json) if args.json is not None else None
        if j is None:
            if not (args.intf and args.res and args.fps):
                ap.error("需要 --intf --res --fps 或 --json")
            hact, vact = _parse_res(args.res)
            j = {"intf": args.intf, "hact": hact, "vact": vact, "fps": args.fps}

        intf_raw = j.get("intf", args.intf)
        interface_defaulted = not intf_raw
        if interface_defaulted:
            intf_raw = "bt656"
        intf = normalize_interface(intf_raw)
        if intf not in INTERFACES:
            raise TimingError(f"不支持的接口: {intf_raw}"
                              "（允许: bt656/bt601/bt1120/dpi，dpi 可用 srgb 别名）",
                              code="unsupported_interface")
        fmt_raw = j.get("fmt", args.fmt)
        fmt = resolve_format(intf, fmt_raw)
        chip_raw = j.get("chip", args.chip)
        chip = normalize_chip(chip_raw)
        if chip_raw and chip is None:
            raise TimingError(f"未知芯片型号: {chip_raw}（仅 AX615D/AX615Q）",
                              code="unknown_chip")

        entries, sync_meta = load_sync_infos()
        reachable, deriv, pclk_meta = load_pclk_table()
        version_hint = load_version_hint()
        notes = []
        if not chip_raw:
            notes.append("[chip] 未提供芯片型号：未按 AX615D 能力边界过滤"
                         "（D 不支持 BT1120/并行 DPI；D 串行 sRGB ≤640x480@30）")
        if interface_defaulted:
            notes.append("[intf] 未指定输出接口，按默认 bt656 处理；"
                         "如为 DPI/BT1120 请显式指定")
        elif intf != str(intf_raw or "").strip().lower():
            notes.append(f"[intf] {intf_raw} 按 dpi（串行 sRGB）别名处理")
        if fmt_raw is None:
            notes.append(f"[fmt] 未显式指定：BT 系按唯一合法格式 {fmt}；"
                         "DPI/srgb 缺格式会按缺失拒绝（不假定并行倍率）")
        for issue in data_consistency():
            notes.append(f"[data] {issue}")

        if args.verify:
            p = {key: j[key] for key in TIMING_KEYS if key in j}
            errors = validate_timing(p, require_all=True)
            if errors:
                raise TimingError("时序参数校验失败（类型/位宽/尺寸/布尔取值范围/必填）",
                                  code="invalid_timing", details={"errors": errors})
            # 能力闸门一律按**配置公式刷新率**判定：verify 输入没有目标 fps，
            # 不得用 --fps 等额外输入替代。刷新率无法计算（如 bDlbClk 缺失）时
            # 由 actual_refresh 抛结构化错误，不绕过闸门。
            eff_fps = actual_refresh(p, intf, fmt)[2]
            cap_errors = capability_errors(intf, fmt, chip, p["u16Hact"],
                                           p["u16Vact"], eff_fps)
            if cap_errors:
                raise TimingError(
                    f"接口 × 格式 × 芯片能力校验失败（按配置公式刷新率 "
                    f"{eff_fps:.2f}Hz 判定）", code="capability",
                    details={"errors": cap_errors,
                             "actual_fps": round(eff_fps, 2),
                             "fps_kind": "配置公式值"})
            htotal, vtotal, f, hints, problems = verify(
                p, intf, fmt, reachable, deriv, version_hint, chip)
            emit_json({
                "status": "invalid" if problems else "ok",
                "mode": "verify", "intf": intf, "intf_raw": intf_raw, "fmt": fmt,
                "chip": chip, "chip_unknown": chip is None,
                "htotal": htotal, "vtotal": vtotal, "actual_fps": round(f, 2),
                "fps_kind": "配置公式值",
                "fps_tolerance": "≤2%（相对误差；verify 对给定参数只做核对，"
                                 "不重算目标）",
                "version_note": version_hint, "hints": hints,
                "problems": problems, "warnings": notes,
                "missing_conditions": [n for n in notes if n.startswith("[chip]")],
            })
            return 1 if problems else 0

        hact = _number_field(j, "hact", integer=True)
        vact = _number_field(j, "vact", integer=True)
        fps = _number_field(j, "fps")
        res_errors = validate_resolution(hact, vact)
        if res_errors:
            raise TimingError("分辨率非法（宽 [16,3840]/高 [4,8190] 且 2 对齐，"
                              "ax_vo_api.h:22-27）", code="invalid_resolution",
                              details={"errors": res_errors})
        cap_errors = capability_errors(intf, fmt, chip, hact, vact, fps)
        if cap_errors:
            raise TimingError("接口 × 格式 × 芯片能力校验失败", code="capability",
                              details={"errors": cap_errors})

        hits, skipped = find_exact(entries, intf, hact, vact, fps, fmt)
        if hits:
            ratio, name, entry, actual = hits[0]
            emit_json({
                "status": "ok", "mode": "table", "intf": intf,
                "intf_raw": intf_raw, "fmt": fmt, "chip": chip,
                "chip_unknown": chip is None,
                "entry": name, "fps_error": round(abs(actual - fps), 3),
                "fps_error_ratio": round(ratio, 5),
                "fps_tolerance": f"≤{FPS_TOLERANCE_RATIO:.0%}（相对误差）",
                "actual_fps": round(actual, 2), "fps_kind": "配置公式值",
                "version_note": version_hint, "params": entry,
                "source": "已验证时序表条目（显式同接口 + 分辨率相等 + 误差 ≤2%）",
                "other_matches": [
                    {"entry": n, "actual_fps": round(a, 2),
                     "fps_error_ratio": round(r, 5),
                     "bDlbClk": entries[n].get("bDlbClk")}
                    for r, n, _, a in hits[1:]],
                "skipped_entries": [{"entry": n, "reason": why}
                                    for n, why in skipped],
                "u8DelaySel": "按所选条目取值；表未记录/客户未提供时为 unknown，"
                              "不得默认",
                "warnings": notes,
            })
            return 0

        tpl_name, candidates, skipped_tpl, derive_notes = derive(
            entries, reachable, intf, hact, vact, fps, fmt)
        if not candidates:
            raise TimingError(
                f"未找到满足 ≤{FPS_TOLERANCE_RATIO:.0%} 目标误差的候选"
                "（当前仅按字段完整/逐行/SDR 模板 + PCLK 档位表枚举搜索）",
                code="no_solution",
                details={
                    "target_fps": fps,
                    "capability_note": "求解搜索失败只说明当前模板 + 档位表组合内无解，"
                                       "不构成芯片/接口能力证明（未扩展 DDR 搜索）；"
                                       "请按屏规格书手工核算 porch 或实机验证",
                    "skipped_entries": [{"entry": n, "reason": why}
                                        for n, why in skipped_tpl],
                    "notes": derive_notes,
                })
        emit_json({
            "status": "ok", "mode": "derived", "intf": intf,
            "intf_raw": intf_raw, "fmt": fmt, "chip": chip,
            "chip_unknown": chip is None, "template": tpl_name,
            "target_fps": fps,
            "fps_tolerance": f"≤{FPS_TOLERANCE_RATIO:.0%}（相对误差）",
            "fps_kind": "配置公式值", "version_note": version_hint,
            "candidates": candidates,
            "source": "推导值（字段完整/逐行/SDR 模板缩放 + 档位表枚举，"
                      "已复核字段/位宽/尺寸/PCLK 档位），未经实机验证，"
                      "须按屏规格书核对 porch 并实机回归",
            "warnings": notes, "notes": derive_notes,
        })
        return 0
    except TimingError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False, indent=2))
        return 1 if error.code == "no_solution" else 2


if __name__ == "__main__":
    sys.exit(main())
