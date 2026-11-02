#!/usr/bin/env python3
"""AX615 VO 时序参数校验 — 对照 skill 内化时序表（自包含，不访问外部路径）。

用法：
  check_vo_timing.py --json '{"bIop":1,...,"u32Pclk":74250,"bDlbClk":0}'
  check_vo_timing.py --file customer_timing.json --intf bt656
  check_vo_timing.py --json '<客户时序>' --intf dpi --fmt srgb565 --chip AX615D

功能：
  1) 严格输入校验：类型/位宽（AX_U16/AX_U32/AX_U8）/尺寸（宽 [16,3840] 且 2 对齐、
     高 [4,8190] 且 2 对齐，ax_vo_api.h:22-27）/布尔字段 0-1/必填字段；
     bDlbClk 缺失按错误处理 —— 不默认 SDR
  2) 接口 × 格式 × 芯片能力闸门（非法格式所有路径拒绝；AX615D 不支持 BT1120 与并行
     DPI，但串行 sRGB 可用且 ≤640x480@30）
  3) 计算**配置公式刷新率**（BT656/601 + YUV422 且显式 SDR 时 ÷2；DDR 不除；
     DPI 串行 sRGB 按格式 ÷2/÷3/÷4）
  4) 校验 u32Pclk 是否**精确命中** PCLK 离散档位表（references/ax615/vo-pclk-table.json）
  5) 与 54 组已验证时序表逐字段比对：固定全集 = 14 必填字段（含 bDlbClk）+ 可选
     u8DelaySel；任一侧缺失记 unknown，完整匹配与部分匹配分离，可选字段差异计入差异数
  6) 与官方 sample 19 组时序表交叉比对；并核对三份数据与 version-manifest 的
     版本/条目数一致性

数据来源（全部为本 skill 内化副本，运行时不依赖 skill 目录以外的任何路径）：
  references/ax615/vo-timing-table.json、references/ax615/sample-vo-timings.json、
  references/ax615/vo-pclk-table.json、references/ax615/version-manifest.json
版本提示：时序表与档位表为 SDK V3.14.0 实现行为，需按版本核验。

退出码：0 = 校验完成；2 = 可预期错误（输入/格式/能力/缺字段，结构化 JSON 输出）。
"""
import argparse
import json
import os
import sys

try:
    from timing_common import (OPTIONAL_KEYS, TIMING_KEYS, TimingError,
                               actual_refresh, capability_errors, dataset_issues,
                               normalize_chip, normalize_interface,
                               resolve_format, validate_timing)
except ImportError:
    from scripts.timing_common import (OPTIONAL_KEYS, TIMING_KEYS, TimingError,
                                       actual_refresh, capability_errors,
                                       dataset_issues, normalize_chip,
                                       normalize_interface, resolve_format,
                                       validate_timing)

_HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.normpath(os.path.join(_HERE, "..", "references", "ax615"))
SYNC_INFOS = os.path.join(REF, "vo-timing-table.json")
SAMPLE_INFOS = os.path.join(REF, "sample-vo-timings.json")
PCLK_TABLE = os.path.join(REF, "vo-pclk-table.json")
VERSION_MANIFEST = os.path.join(REF, "version-manifest.json")

# 比对固定全集：14 必填字段（含 bDlbClk）+ 可选 u8DelaySel
COMPARE_KEYS = TIMING_KEYS


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as error:
        raise TimingError(f"数据文件读取失败: {path}: {error}",
                          code="data_load_failed") from error


def load_version_hint():
    manifest = _load(VERSION_MANIFEST)
    return manifest["canonical_version_note"]


def load_manifest():
    return _load(VERSION_MANIFEST)


def load_sync_infos():
    data = _load(SYNC_INFOS)
    return data["entries"], data.get("_meta", {})


def load_sample_infos():
    data = _load(SAMPLE_INFOS)
    return data.get("entries", []), data.get("conflicts", []), data.get("_meta", {})


def load_pclk_table():
    """PCLK 精确离散档位表（5 源 × 16 分频，取整商）。"""
    data = _load(PCLK_TABLE)
    reachable = data.get("reachable_pclk_khz", [])
    combos = data.get("combos", [])
    deriv = {}
    for c in combos:
        deriv.setdefault(c["pclk_khz"], (c["source_khz"], c["divider"]))
    return set(reachable), deriv, data.get("_meta", {})


def data_consistency():
    """核对三份内化数据的版本与条目数是否与 version-manifest 一致。"""
    manifest = load_manifest()
    datasets = {}
    entries, sync_meta = load_sync_infos()
    datasets["vo-timing-table.json"] = {
        "sdk_version": sync_meta.get("sdk_version"),
        "declared_count": sync_meta.get("count"),
        "actual_count": len(entries),
    }
    samples, _, sample_meta = load_sample_infos()
    datasets["sample-vo-timings.json"] = {
        "sdk_version": sample_meta.get("sdk_version"),
        "declared_count": sample_meta.get("count"),
        "actual_count": len(samples),
    }
    reachable, _, pclk_meta = load_pclk_table()
    datasets["vo-pclk-table.json"] = {
        "sdk_version": pclk_meta.get("sdk_version"),
        "declared_count": pclk_meta.get("count_reachable"),
        "actual_count": len(reachable),
    }
    return dataset_issues(manifest, datasets)


def pclk_supported(pclk, reachable, deriv):
    """返回 (命中?, PLL源, 分频) —— 只按离散表精确匹配。"""
    if pclk in reachable:
        src, div = deriv.get(pclk, ("?", "?"))
        return True, src, div
    return False, 0, 0


def nearest_pclk(pclk, reachable):
    return min(reachable, key=lambda v: (abs(v - pclk), v))


def _field_state(entry, cust, key):
    """字段比对结果：'same' / 'diff' / 'unknown'（任一侧缺失或 None 均记 unknown）。"""
    left, right = entry.get(key), cust.get(key)
    if left is None or right is None:
        return "unknown"
    return "same" if left == right else "diff"


def _state_table(entry, cust):
    """固定全集（14 必填字段 + u8DelaySel）的比对状态。"""
    states = {key: _field_state(entry, cust, key) for key in COMPARE_KEYS}
    states.update({key: _field_state(entry, cust, key) for key in OPTIONAL_KEYS})
    diffs = {k: (entry.get(k), cust.get(k)) for k, s in states.items() if s == "diff"}
    unknown = [k for k, s in states.items() if s == "unknown"]
    table_missing = [k for k in COMPARE_KEYS + OPTIONAL_KEYS
                     if entry.get(k) is None]
    return states, diffs, unknown, table_missing


def compare(entries, cust, limit=3):
    """与已验证表逐字段比对，返回 (similar, full_matches, partial_matches)。

    - 固定全集含 bDlbClk；u8DelaySel 为可选字段，其差异计入差异数。
    - unknown = 表未记录或客户未提供（任一侧），不得默认等价。
    - full_matches：全部比对字段一致且无 unknown（完整匹配）。
    - partial_matches：固定字段零差异但存在 unknown（部分匹配，不构成完全等价，
      表缺关键字段的条目不得当作已验证配置）。
    """
    similar, full, partial = [], [], []
    for name, e in entries.items():
        _, diffs, unknown, table_missing = _state_table(e, cust)
        ndiff, nunknown = len(diffs), len(unknown)
        if ndiff == 0 and nunknown == 0:
            full.append(name)
        elif ndiff == 0:
            partial.append((name, unknown, table_missing))
        if ndiff <= limit:
            similar.append((ndiff, nunknown, name, diffs, unknown, table_missing))
    similar.sort(key=lambda x: (x[0], x[1], x[2]))
    return similar, full, partial


def compare_sample(sample_entries, cust, limit=2):
    """与官方 sample 19 组时序表交叉比对（同样按固定全集 + unknown 传播）。"""
    hits = []
    for e in sample_entries:
        p = e["params"]
        _, diffs, unknown, table_missing = _state_table(p, cust)
        if len(diffs) <= limit:
            hits.append((len(diffs), len(unknown), e["index"], e["label"],
                         diffs, unknown, table_missing))
    hits.sort()
    return hits


def _read_input(args):
    if args.json is not None:
        try:
            payload = json.loads(args.json)
        except json.JSONDecodeError as error:
            raise TimingError(f"--json 不是合法 JSON: {error}",
                              code="invalid_json") from error
    elif args.file:
        payload = _load(args.file)
    else:
        raise TimingError("需要 --json 或 --file", code="invalid_input")
    if not isinstance(payload, dict):
        raise TimingError("时序参数 JSON 顶层必须是 object（当前为 "
                          f"{type(payload).__name__}）", code="invalid_json")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="AX615 VO 时序参数校验")
    ap.add_argument("--json", help="客户时序参数 JSON 字符串（顶层 object）")
    ap.add_argument("--file", help="客户时序参数 JSON 文件（顶层 object）")
    ap.add_argument("--intf", default="bt656",
                    choices=["bt656", "bt601", "bt1120", "dpi", "srgb"],
                    help="输出接口类型（srgb 为 dpi 串行 sRGB 别名）")
    ap.add_argument("--fmt", default=None,
                    help="输出格式；默认 BT 系 yuv422、dpi/srgb rgb565（并行）")
    ap.add_argument("--chip", default=None,
                    help="芯片型号（可选 AX615D/AX615Q；未提供时不按芯片能力过滤）")
    args = ap.parse_args()

    try:
        cust = _read_input(args)
        intf = normalize_interface(args.intf)
        fmt = resolve_format(intf, args.fmt)
        chip = normalize_chip(args.chip)
        if args.chip and chip is None:
            raise TimingError(f"未知芯片型号: {args.chip}（仅 AX615D/AX615Q）",
                              code="unknown_chip")

        errors = validate_timing(cust, require_all=True)
        if errors:
            raise TimingError("时序参数校验失败（类型/位宽/尺寸/布尔取值范围/必填）",
                              code="invalid_timing", details={"errors": errors})

        cap_errors = capability_errors(intf, fmt, chip, cust["u16Hact"],
                                       cust["u16Vact"])
        if cap_errors:
            raise TimingError("接口 × 格式 × 芯片能力校验失败", code="capability",
                              details={"errors": cap_errors})

        htotal, vtotal, refresh = actual_refresh(cust, intf, fmt)
        cap_errors = capability_errors(intf, fmt, chip, cust["u16Hact"],
                                       cust["u16Vact"], refresh)
        if cap_errors:
            raise TimingError("接口 × 格式 × 芯片能力校验失败", code="capability",
                              details={"errors": cap_errors})

        entries, sync_meta = load_sync_infos()
        sample_entries, conflicts, _ = load_sample_infos()
        reachable, deriv, _ = load_pclk_table()
        version_hint = load_version_hint()
        version_issues = data_consistency()
    except TimingError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False, indent=2))
        return 2

    notes = []
    if not args.chip:
        notes.append("[chip] 未提供芯片型号：未按 AX615D 能力边界过滤"
                     "（D 不支持 BT1120/并行 DPI；D 串行 sRGB ≤640x480@30）")
    if intf != str(args.intf).strip().lower():
        notes.append(f"[intf] {args.intf} 按 dpi（串行 sRGB）别名处理")
    if args.fmt is None:
        notes.append(f"[fmt] 未显式指定：BT 系按唯一合法格式 {fmt}；"
                     "DPI/srgb 缺格式会在校验阶段按缺失拒绝（不假定并行倍率）")
    if "u8DelaySel" not in cust:
        notes.append("[u8DelaySel] 客户未提供：比对中记 unknown，不得默认等价")

    print(f"== 已加载 {len(entries)} 组已验证时序 + {len(sample_entries)} 组官方 sample 时序 + "
          f"{len(reachable)} 个可达 PCLK（内化副本，skill 自包含）")
    print(f"== 版本提示：{version_hint}")
    if version_issues:
        print("== 数据版本一致性：⚠ 不一致（以下问题会让比对结论不可靠）")
        for issue in version_issues:
            print(f"   - {issue}")
    else:
        print(f"== 数据版本一致性：OK（{sync_meta.get('sdk_version', '?')} vs "
              f"version-manifest）")
    print("== 输入校验：通过（14 必填字段 + 类型/位宽/尺寸/布尔取值范围）")
    print(f"== 接口/格式/芯片：intf={intf} fmt={fmt} "
          f"chip={chip if chip else '未提供'}")
    for note in notes:
        print(f"   - {note}")
    print()

    print(f"[配置公式] Htotal={htotal} Vtotal={vtotal} 刷新率={refresh:.2f}Hz"
          f"（接口 {intf}, fmt {fmt}, bDlbClk={cust.get('bDlbClk')}）")
    if intf in ("bt656", "bt601") and fmt == "yuv422":
        mode = "DDR（u32Pclk=像素时钟，不再 ÷2）" if cust.get("bDlbClk") \
            else "SDR（u32Pclk=像素时钟×2，公式 ÷2）"
        print(f"[配置公式] BT {intf} YUV422 时钟语义：{mode}（bDlbClk 显式提供）")
    if intf == "dpi" and fmt in ("srgb565", "srgb666", "srgb565s", "srgb888",
                                 "srgb888a", "srgb888b"):
        print(f"[配置公式] DPI 串行 {fmt}：已按倍率换算；u32Pclk 仍须精确命中离散档位表")
    print("  ↑ 该值为配置公式值；存在版本实现差异时以实机为准 —— "
          "请用 proc display_status 的 Refresh/OutFps 与 VSYNC 回调计数实测核对")
    print(f"[配置公式] bIop={cust.get('bIop')} → "
          f"{'逐行' if cust.get('bIop') else '隔行'}（0=隔行 1=逐行，须与屏扫描方式一致）")

    ok, src, div = pclk_supported(cust["u32Pclk"], reachable, deriv)
    if ok:
        print(f"[PCLK] {cust['u32Pclk']} kHz 精确命中离散档位表（源 {src} ÷ {div}）")
    else:
        near = nearest_pclk(cust["u32Pclk"], reachable)
        print(f"[PCLK] ✗ {cust['u32Pclk']} kHz 不在离散档位表（不精确命中即不可用）；"
              f"最近可达值：{near} kHz")
        print("       公开 API 侧通常表现为 AX_ERR_VO_DEV_OP_FAIL，"
              "真实原因须结合 dmesg 的 unsupport clk 定位")

    similar, full, partial = compare(entries, cust)
    print(f"\n== 与 {len(entries)} 组已验证时序表比对（固定 14 字段含 bDlbClk + "
          f"可选 u8DelaySel，可选字段差异计入差异数；差异 ≤3 字段的条目）:")
    if not similar:
        print("  （无相似条目——参数组合很可能是客户自创，需逐字段核对）")
    for ndiff, nunknown, name, diffs, unknown, _ in similar:
        note = f"（差异 {ndiff} 处" + (f"，另有 {nunknown} 个字段 unknown："
                                        f"{','.join(unknown)}" if nunknown else "") + "）"
        print(f"  - {name}{note}: {diffs}")

    print("\n== 完整匹配（14 固定字段 + u8DelaySel 全部一致，无 unknown）:")
    if not full:
        print("  （无）")
    for name in full:
        print(f"  - {name}")

    print("\n== 部分匹配（固定字段零差异，但存在 unknown —— 不构成完全等价）:")
    if not partial:
        print("  （无）")
    for name, unknown, table_missing in partial:
        miss = f"；表未记录：{','.join(table_missing)}" if table_missing else ""
        print(f"  - {name}（unknown：{','.join(unknown)}{miss}）")
    print("   注：完整/部分匹配只覆盖比对字段；表缺关键字段的条目不得当作已验证配置，"
          "送帧是否成功仍以客户实际配置 + proc/dmesg 为准")

    hits = compare_sample(sample_entries, cust)
    print(f"\n== 与官方 sample {len(sample_entries)} 组时序表交叉比对（差异 ≤2 的条目）:")
    if not hits:
        print("  （无相似条目）")
    for ndiff, nunknown, idx, label, diffs, unknown, _ in hits:
        u = f"，unknown 字段 {','.join(unknown)}" if unknown else ""
        print(f"  - sample 第 {idx} 条 {label}（差异 {ndiff} 处: {diffs}{u}）")

    print("\n== 已知表间差异（不静默合并，详见 sample-vo-timings.json conflicts）:")
    for c in conflicts:
        print(f"  - [{c['id']}] {c['scope']}：{c['difference']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
