#!/usr/bin/env python3
"""AX615 VO 时序脚本共享常量、严格校验、能力闸门与刷新率计算。

约束来源均取自本 skill 内化副本（运行时不访问 skill 目录以外的路径）：
  字段/位宽：references/ax615/sdk-inline/ax_vo_api.h:169-190（AX_VO_SYNC_INFO_T；
    u16*/u32*/u8* 位宽，bIop/bIdv/bIhs/bIvs/bDlbClk 取 0/1）
  尺寸约束：ax_vo_api.h:22-27（宽 [16,3840] 且 2 对齐；高 [4,8190] 且 2 对齐）
  接口/格式/芯片能力：vo-constraints.md 第 2 节、vo-config-reference.md 第 4 节
  刷新率公式与 DPI 串行倍率：vo-constraints.md 第 3 节（SDK V3.14.0 实现行为，需按版本核验）

约定：
  - srgb 是 dpi（串行 sRGB）的接口别名，统一归一化为 dpi；倍率按格式区分
    （并行 RGB565=1；串行 SRGB565/SRGB666=2、SRGB565S/SRGB888=3、SRGB888A/B=4）。
  - bDlbClk 必须由输入显式提供；缺失时按 unknown 传播，不默认 SDR。
  - 可预期的输入/能力错误统一抛 TimingError，脚本捕获后结构化输出并非 0 退出。
"""
from __future__ import annotations

import math
from typing import Any

# 接口：srgb 为 dpi 串行别名
BT_INTF = frozenset({"bt656", "bt601", "bt1120"})
INTERFACES = BT_INTF | {"dpi"}
BT_FMT = "yuv422"

# DPI 串行 sRGB 格式 → 显示时钟倍率（配置公式刷新率需除以该倍率）
DPI_FMT_FACTOR = {
    "rgb565": 1,
    "srgb565": 2,
    "srgb666": 2,
    "srgb565s": 3,
    "srgb888": 3,
    "srgb888a": 4,
    "srgb888b": 4,
}
PARALLEL_DPI_FMTS = frozenset(fmt for fmt, factor in DPI_FMT_FACTOR.items() if factor == 1)
SERIAL_SRGB_FMTS = frozenset(fmt for fmt, factor in DPI_FMT_FACTOR.items() if factor > 1)

# 时序字段（AX_VO_SYNC_INFO_T，ax_vo_api.h:169-190）
TIMING_KEYS = (
    "bIop", "u16Vact", "u16Vbb", "u16Vfb", "u16Hact", "u16Hbb",
    "u16Hfb", "u16Hpw", "u16Vpw", "u32Pclk", "bIdv", "bIhs",
    "bIvs", "bDlbClk",
)
BOOL_KEYS = ("bIop", "bIdv", "bIhs", "bIvs", "bDlbClk")
U16_KEYS = ("u16Vact", "u16Vbb", "u16Vfb", "u16Hact", "u16Hbb", "u16Hfb",
            "u16Hpw", "u16Vpw")
U8_KEYS = ("u8DelaySel",)
# 可选字段：客户/表条目可缺，缺时按 unknown（不默认等价）
OPTIONAL_KEYS = U8_KEYS

AX_U8_MAX = 0xFF
AX_U16_MAX = 0xFFFF
AX_U32_MAX = 0xFFFFFFFF

# 显示宽高约束（ax_vo_api.h:22-27）
HACT_MIN, HACT_MAX, HACT_ALIGN = 16, 3840, 2
VACT_MIN, VACT_MAX, VACT_ALIGN = 4, 8190, 2

# AX615D 串行 sRGB 上限（vo-config-reference.md 第 4 节：最大 640×480@30fps）
AX615D_SERIAL_MAX = (640, 480, 30)

_CHIPS = frozenset({"ax615", "ax615d", "ax615q"})


class TimingError(ValueError):
    """可预期的输入/能力错误（脚本捕获后结构化输出并非 0 退出）。"""

    def __init__(self, message: str, code: str = "invalid_input",
                 details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": "error", "code": self.code,
                               "message": str(self)}
        if self.details:
            out["details"] = self.details
        return out


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_bool01(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    return is_int(value) and value in (0, 1)


def normalize_interface(intf: Any) -> str:
    """接口归一化：srgb（串行 sRGB）→ dpi 别名。"""
    value = str(intf or "").strip().lower()
    if value == "srgb":
        return "dpi"
    return value


def normalize_format(fmt: Any) -> str:
    return str(fmt or "").strip().lower()


def normalize_chip(chip: Any) -> str | None:
    """芯片型号归一化；未提供返回 None，非法型号返回 None（由调用方报错）。"""
    if chip is None:
        return None
    value = str(chip).strip().lower().replace("-", "").replace("_", "")
    if not value:
        return None
    return value if value in _CHIPS else None


def resolve_format(intf: Any, fmt: Any) -> str:
    """解析有效格式：BT 系缺省 YUV422（唯一合法格式）；DPI/srgb 缺省按缺失报错。

    DPI 并行 RGB565 与串行 sRGB 的倍率不同（÷1 vs ÷2/÷3/÷4），缺省时不得假定
    并行，否则刷新率换算会算错。
    """
    normalized_fmt = normalize_format(fmt)
    if normalized_fmt:
        return normalized_fmt
    if normalize_interface(intf) in BT_INTF:
        return BT_FMT
    raise TimingError(
        "缺少输出格式 fmt：DPI（含 srgb 别名）并行 RGB565 与串行 sRGB 倍率不同，"
        "必须显式指定（rgb565/srgb565/srgb666/srgb565s/srgb888/srgb888a/srgb888b）",
        code="missing_format")


def capability_errors(intf: Any, fmt: Any = None, chip: Any = None,
                      hact: Any = None, vact: Any = None,
                      fps: Any = None) -> list[str]:
    """接口 × 格式 × 芯片能力校验（返回错误列表，空列表 = 通过）。

    chip 未提供时不按芯片过滤（由脚本输出缺失条件标记）；给出非法型号则报错。
    AX615D：不支持 BT1120 与并行 DPI（VO 仅 11 pin），但串行 sRGB 可用，
    且串行 sRGB 最大 640×480@30fps（vo-config-reference.md 第 4 节）。
    """
    normalized_intf = normalize_interface(intf)
    errors: list[str] = []
    if normalized_intf not in INTERFACES:
        return [f"不支持的接口: {intf}（允许: bt656/bt601/bt1120/dpi，"
                f"dpi 可用 srgb 别名）"]
    normalized_fmt = normalize_format(fmt)
    if not normalized_fmt:
        if normalized_intf in BT_INTF:
            normalized_fmt = BT_FMT
        else:
            errors.append("缺少输出格式 fmt：DPI（含 srgb 别名）并行 RGB565 与串行 "
                          "sRGB 倍率不同，必须显式指定（rgb565/srgb565/srgb666/"
                          "srgb565s/srgb888/srgb888a/srgb888b）")
            return errors
    if normalized_intf in BT_INTF and normalized_fmt != BT_FMT:
        errors.append(f"{normalized_intf} 输出只支持 YUV422，当前 fmt={fmt}"
                      "（vo-constraints.md 第 2 节）")
    if normalized_intf == "dpi" and normalized_fmt not in DPI_FMT_FACTOR:
        errors.append(f"DPI 不支持格式 {fmt}，允许: "
                      + ", ".join(sorted(DPI_FMT_FACTOR)))

    if chip is not None and normalize_chip(chip) is None:
        errors.append(f"未知芯片型号: {chip}（仅 AX615D/AX615Q）")
        return errors

    if normalize_chip(chip) == "ax615d":
        if normalized_intf == "bt1120":
            errors.append("AX615D 不支持 BT1120（VO 仅 11 pin；"
                          "vo-config-reference.md 第 4 节）")
        if normalized_intf == "dpi" and normalized_fmt in PARALLEL_DPI_FMTS:
            errors.append("AX615D 不支持并行 DPI（VO 仅 11 pin）；"
                          "D 的串行 sRGB 可用，最大 640x480@30")
        if normalized_intf == "dpi" and normalized_fmt in SERIAL_SRGB_FMTS:
            max_w, max_h, max_fps = AX615D_SERIAL_MAX
            if is_int(hact) and hact > max_w:
                errors.append(f"AX615D 串行 sRGB 最大 {max_w}x{max_h}@"
                              f"{max_fps}，当前 hact={hact}")
            if is_int(vact) and vact > max_h:
                errors.append(f"AX615D 串行 sRGB 最大 {max_w}x{max_h}@"
                              f"{max_fps}，当前 vact={vact}")
            if isinstance(fps, (int, float)) and not isinstance(fps, bool) \
                    and math.isfinite(float(fps)) and float(fps) > max_fps:
                errors.append(f"AX615D 串行 sRGB 最大 {max_w}x{max_h}@"
                              f"{max_fps}，当前 {fps}fps")
    return list(dict.fromkeys(errors))


def validate_positive_number(value: Any, field: str) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"{field} 必须是数字"
    if not math.isfinite(float(value)) or float(value) <= 0:
        return f"{field} 必须是有限正数"
    return None


def validate_resolution(hact: Any, vact: Any) -> list[str]:
    """显示宽高约束：宽 [16,3840] 且 2 对齐；高 [4,8190] 且 2 对齐（ax_vo_api.h:22-27）。"""
    errors: list[str] = []
    if not is_int(hact):
        errors.append("u16Hact 必须是整数")
    if not is_int(vact):
        errors.append("u16Vact 必须是整数")
    if errors:
        return errors
    if not HACT_MIN <= hact <= HACT_MAX:
        errors.append(f"u16Hact 必须在 {HACT_MIN}..{HACT_MAX} 范围内"
                      "（ax_vo_api.h:22-23）")
    if not VACT_MIN <= vact <= VACT_MAX:
        errors.append(f"u16Vact 必须在 {VACT_MIN}..{VACT_MAX} 范围内"
                      "（ax_vo_api.h:24-25）")
    if not errors:
        if hact % HACT_ALIGN:
            errors.append(f"u16Hact 必须 {HACT_ALIGN} 对齐（ax_vo_api.h:26）")
        if vact % VACT_ALIGN:
            errors.append(f"u16Vact 必须 {VACT_ALIGN} 对齐（ax_vo_api.h:27）")
    return errors


def validate_timing(p: Any, require_all: bool = True) -> list[str]:
    """严格校验时序参数字典：类型/位宽/尺寸/布尔取值范围/必填字段。

    require_all=True 时 14 个必填字段（含 bDlbClk）缺失即报错；bDlbClk 缺失
    按错误处理，绝不默认 SDR。u8DelaySel 为可选字段，缺失不算错误。
    """
    if not isinstance(p, dict):
        return ["时序参数必须是 JSON object"]
    errors: list[str] = []
    if require_all:
        missing = [key for key in TIMING_KEYS if key not in p or p[key] is None]
        if missing:
            errors.append("缺少必填字段（bDlbClk 缺失不得默认 SDR）: "
                          + ", ".join(missing))
    for key in TIMING_KEYS:
        if key not in p or p[key] is None:
            continue
        value = p[key]
        if key in BOOL_KEYS:
            if not is_bool01(value):
                errors.append(f"{key} 必须是 0/1（AX_BOOL）")
        elif key == "u32Pclk":
            if not is_int(value):
                errors.append("u32Pclk 必须是整数")
            elif not 1 <= value <= AX_U32_MAX:
                errors.append(f"u32Pclk 必须在 1..{AX_U32_MAX} 范围内（AX_U32，单位 kHz）")
        elif key in U16_KEYS:
            if not is_int(value):
                errors.append(f"{key} 必须是整数")
            elif not 0 <= value <= AX_U16_MAX:
                errors.append(f"{key} 必须在 0..{AX_U16_MAX} 范围内（AX_U16）")
    for key in U8_KEYS:
        if key not in p or p[key] is None:
            continue
        value = p[key]
        if not is_int(value):
            errors.append(f"{key} 必须是整数")
        elif not 0 <= value <= AX_U8_MAX:
            errors.append(f"{key} 必须在 0..{AX_U8_MAX} 范围内（AX_U8）")
    if "u16Hact" in p or "u16Vact" in p:
        errors.extend(validate_resolution(p.get("u16Hact"), p.get("u16Vact")))
    return list(dict.fromkeys(errors))


def _totals(p: dict[str, Any]) -> tuple[int, int]:
    missing = [key for key in U16_KEYS if not is_int(p.get(key))]
    if missing:
        raise TimingError("缺少可用整数时序字段: " + ", ".join(missing),
                          code="invalid_timing", details={"fields": missing})
    htotal = p["u16Hact"] + p["u16Hbb"] + p["u16Hfb"] + p["u16Hpw"]
    vtotal = p["u16Vact"] + p["u16Vbb"] + p["u16Vfb"] + p["u16Vpw"]
    if htotal <= 0 or vtotal <= 0:
        raise TimingError("时序总长度必须为正数", code="invalid_timing")
    return htotal, vtotal


def refresh_factor(intf: Any, fmt: Any, dbl: Any) -> int:
    """配置公式刷新率分母因子；dbl 必须由调用方显式给出（不隐式默认 SDR）。

    BT656/601 + YUV422：SDR(bDlbClk=0) ÷2、DDR ÷1；BT1120 ÷1；
    DPI 并行 RGB565 ÷1，串行 sRGB ÷2/÷3/÷4。
    """
    normalized_intf = normalize_interface(intf)
    if normalized_intf not in INTERFACES:
        raise TimingError(f"不支持的接口: {intf}（允许: bt656/bt601/bt1120/dpi）",
                          code="unsupported_interface")
    normalized_fmt = resolve_format(normalized_intf, fmt)
    if normalized_intf in BT_INTF:
        if normalized_fmt != BT_FMT:
            raise TimingError(f"{normalized_intf} 输出只支持 YUV422，"
                              f"当前 fmt={fmt}", code="unsupported_format")
        if normalized_intf in ("bt656", "bt601") and not dbl:
            return 2
        return 1
    factor = DPI_FMT_FACTOR.get(normalized_fmt)
    if factor is None:
        raise TimingError(f"DPI 不支持格式 {fmt}，允许: "
                          + ", ".join(sorted(DPI_FMT_FACTOR)),
                          code="unsupported_format")
    return factor


def refresh_formula(p: Any, intf: Any, fmt: Any = None
                    ) -> tuple[int, int, float | None, list[str]]:
    """配置公式刷新率：u32Pclk×1000/(htotal×vtotal) ÷ 因子。

    返回 (htotal, vtotal, fps, notes)。fps 为 None 表示关键字段缺失
    （BT656/601 缺 bDlbClk 时 SDR/DDR 语义未知，不默认 SDR）。
    """
    if not isinstance(p, dict):
        raise TimingError("时序参数必须是 JSON object", code="invalid_input")
    normalized_intf = normalize_interface(intf)
    if normalized_intf not in INTERFACES:
        raise TimingError(f"不支持的接口: {intf}（允许: bt656/bt601/bt1120/dpi）",
                          code="unsupported_interface")
    normalized_fmt = resolve_format(normalized_intf, fmt)
    htotal, vtotal = _totals(p)
    pclk = p.get("u32Pclk")
    if not isinstance(pclk, int) or isinstance(pclk, bool) or pclk <= 0:
        raise TimingError("u32Pclk 必须是正整数（单位 kHz）", code="invalid_timing")
    base = pclk * 1000 / (htotal * vtotal)
    notes: list[str] = []
    if normalized_intf in BT_INTF:
        if normalized_fmt != BT_FMT:
            raise TimingError(f"{normalized_intf} 输出只支持 YUV422，"
                              f"当前 fmt={fmt}", code="unsupported_format")
        if normalized_intf in ("bt656", "bt601"):
            dbl = p.get("bDlbClk")
            if dbl is None:
                notes.append("[bDlbClk] 未提供：BT656/601 的 SDR/DDR 时钟语义未知，"
                             "刷新率不给值（不得默认 SDR）")
                return htotal, vtotal, None, notes
            if not is_bool01(dbl):
                raise TimingError("bDlbClk 必须是 0/1（AX_BOOL）",
                                  code="invalid_timing")
            return htotal, vtotal, base if dbl else base / 2, notes
        return htotal, vtotal, base, notes
    factor = DPI_FMT_FACTOR.get(normalized_fmt)
    if factor is None:
        raise TimingError(f"DPI 不支持格式 {fmt}，允许: "
                          + ", ".join(sorted(DPI_FMT_FACTOR)),
                          code="unsupported_format")
    if factor > 1:
        notes.append(f"[fmt] DPI 串行 {normalized_fmt}：配置公式刷新率已 ÷{factor}")
    return htotal, vtotal, base / factor, notes


def actual_refresh(p: Any, intf: Any, fmt: Any = None) -> tuple[int, int, float]:
    """严格版配置公式刷新率；关键字段缺失（如 bDlbClk）抛 TimingError。"""
    htotal, vtotal, fps, notes = refresh_formula(p, intf, fmt)
    if fps is None:
        raise TimingError("；".join(notes) or "刷新率无法计算", code="unknown_refresh",
                          details={"unknown_fields": ["bDlbClk"]})
    return htotal, vtotal, fps


def dataset_issues(manifest: dict[str, Any],
                   datasets: dict[str, dict[str, Any]]) -> list[str]:
    """数据版本/条目数一致性检查。

    datasets[name] = {"sdk_version": 表内版本, "declared_count": 声明条目数,
                      "actual_count": 实际条目数}
    """
    expected = str(manifest.get("internalized_version") or "")
    issues: list[str] = []
    for name in sorted(datasets):
        info = datasets[name]
        version = info.get("sdk_version")
        if version is not None and str(version) != expected:
            issues.append(f"{name} 数据版本 {version} 与 version-manifest "
                          f"基线 {expected} 不一致")
        declared = info.get("declared_count")
        actual = info.get("actual_count")
        if isinstance(declared, int) and isinstance(actual, int) \
                and declared != actual:
            issues.append(f"{name} 声明条目数 {declared} 与实际 {actual} 不一致")
    return issues
