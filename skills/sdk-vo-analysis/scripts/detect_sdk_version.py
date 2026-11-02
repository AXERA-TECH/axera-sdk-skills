#!/usr/bin/env python3
"""从客户提供的 proc/log 文本中探测 AX615 VO SDK 版本并给出路由策略。

版本 token：`Vx.y.z`（可省略前导 V），可带构建后缀——下划线变体/14 位时间戳
（如 `V3.10.0_2771`、`V3.14.0_20260915123456`）或 `-`/`+` 附加标识。
匹配结果保留完整 raw token，`version` 始终是归一化的 `Vx.y.z` 主版本。

退出码：0 已识别版本或 --known；2 支持的文件均未命中版本；
3 文件存在但未解析出版本；1 输入/读取错误。
"""
import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.normpath(os.path.join(_HERE, "..", "references", "ax615", "version-manifest.json"))
# 只匹配 x.y.z 三段；`3.14.0.1`、`192.0.2.1` 这类多段点分数字由 parse_version 的段数守卫拒绝。
VERSION_TOKEN_RE = re.compile(
    r"(?<![0-9A-Za-z.])(?<![0-9]\.)V?(\d+\.\d+\.\d+)(?:_[0-9A-Za-z]+|[-+][A-Za-z0-9][A-Za-z0-9.]*)?(?![0-9A-Za-z.])",
    re.I,
)
VARIANT_RE = re.compile(r"^_(\d{14})$")
V3_CORE_RE = re.compile(r"V3\.\d+\.\d+")
SDK_LINE_RE = re.compile(r"^\s*\[SDK version\]:\s*(?P<body>[^\r\n]*)$", re.I | re.M)
SYSTEM_RE = re.compile(r"^\s*Ax_Version\s+(?P<version>\S+)\s*$", re.I | re.M)


def load_manifest():
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def read_input(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_version(text):
    """取文本中第一个版本 token；返回 None 表示未命中。"""
    text = text or ""
    for match in VERSION_TOKEN_RE.finditer(text):
        end = match.end()
        # 版本号后紧跟 `.<数字>`（或前一段是 `<数字>.`）的是 IP/多段点分数字，不是 SDK 版本
        if end < len(text) and text[end] == "." and text[end + 1:end + 2].isdigit():
            continue
        if match.start() >= 2 and text[match.start() - 1] == "." and text[match.start() - 2].isdigit():
            continue
        raw = match.group(0)
        core = "V" + match.group(1)
        suffix = raw[match.start(1) + len(match.group(1)) - match.start():]
        if suffix.startswith(("+", "-")):
            # 加号/连字符后缀是版本 token 自身的一部分（如 3.14.1-rc1），不是独立构建变体
            core, suffix = core + suffix, ""
        variant = VARIANT_RE.match(suffix)
        return {
            "version": core,
            "raw_version": raw,
            "build_variant": suffix or None,
            "build_timestamp": variant.group(1) if variant else None,
        }
    return None


def parse_display_status(text):
    for line in SDK_LINE_RE.finditer(text or ""):
        parsed = parse_version(line.group("body"))
        if parsed:
            prefix = line.group("body")[:line.group("body").find(parsed["raw_version"])].strip()
            parsed.update({"source": "display_status", "module": prefix or None,
                           "confidence": "confirmed"})
            return parsed
    return None


def parse_system_version(text):
    match = SYSTEM_RE.search(text or "")
    if not match:
        return None
    parsed = parse_version(match.group("version"))
    if parsed:
        parsed.update({"source": "system_version", "module": "system",
                       "confidence": "confirmed"})
    return parsed


def parse_sdk_lines(text, source):
    findings = []
    for line in SDK_LINE_RE.finditer(text or ""):
        parsed = parse_version(line.group("body"))
        if not parsed:
            continue
        prefix = line.group("body")[:line.group("body").find(parsed["raw_version"])].strip()
        parsed.update({"source": source, "module": prefix or None, "confidence": "reported"})
        findings.append(parsed)
    return findings


def parse_customer_text(text):
    parsed = parse_version(text)
    if parsed:
        parsed.update({"source": "customer", "module": None, "confidence": "reported"})
    return parsed


def select_primary(findings):
    priority = {"display_status": 0, "system_version": 1, "vo_library_log": 2,
                "dmesg": 3, "customer": 4}
    return min(findings, key=lambda item: priority.get(item["source"], 99)) if findings else None


def build_result(findings, manifest, known=False):
    internal = manifest["internalized_version"]
    primary = select_primary(findings)
    conflicts = []
    history = {item["version"]: item for item in manifest.get("version_history", [])}
    if primary:
        for item in findings:
            if item is not primary and item["version"] != primary["version"]:
                conflicts.append({"source": item["source"], "module": item.get("module"),
                                  "version": item["version"], "raw_version": item["raw_version"]})
        match = "same" if primary["version"] == internal else "different"
        usage = "as-is-annotated" if match == "same" else "hypothesis-only"
    else:
        match = "unknown"
        usage = "known-only" if known else "unknown-version-hypothesis"
    # 构建变体（_2771 / _YYYYmmddHHMMSS）不改变主版本语义，按主版本入历史
    detected_base = primary["version"] if primary else None
    hist_entry = history.get(detected_base)
    history_unverified = False
    if match == "different" and not hist_entry and V3_CORE_RE.fullmatch(detected_base or ""):
        # V3 系列但未收录：不给该区间背书，按待验证假设处理
        history_unverified = True
        usage = "hypothesis-only"
    messages = []
    if conflicts:
        messages.append("版本来源存在冲突；按最高优先级来源路由，并保留全部冲突证据")
    if match == "different":
        if hist_entry:
            messages.append("该版本在 V3 版本历史中，可分析；VO 差异点：" + hist_entry["vo_changes"])
        elif history_unverified:
            messages.append("目标版本在 V3 系列但不在已核实版本历史中；该版本区间未经核实，"
                            "D/E 级资料只能作为待验证假设，须用目标版本头文件/知识库/实机复核")
        else:
            messages.append("目标 SDK 与内化版本不同且不在 V3 版本历史中；D/E 级资料只能作为假设，须按目标版本重新核验")
    elif match == "unknown" and not known:
        messages.append("SDK 版本未知，结论适用范围受限；优先收集 /proc/ax_proc/vo/display_status")
    return {
        "schema_version": 1,
        "internalized_version": internal,
        "canonical_version_note": manifest["canonical_version_note"],
        "detected_version": detected_base,
        "raw_version": primary["raw_version"] if primary else None,
        "build_variant": primary.get("build_variant") if primary else None,
        "build_timestamp": primary.get("build_timestamp") if primary else None,
        "source": primary["source"] if primary else "unknown",
        "module": primary.get("module") if primary else None,
        "confidence": primary["confidence"] if primary else "unknown",
        "match": match,
        "conflict": bool(conflicts),
        "conflicts": conflicts,
        "findings": findings,
        "in_version_history": hist_entry is not None,
        "history_version": hist_entry["version"] if hist_entry else None,
        "history_unverified": history_unverified,
        "history_vo_changes": hist_entry["vo_changes"] if hist_entry else None,
        "policy": {
            "d_e_usage": usage,
            "required_annotation": manifest["canonical_version_note"],
            "kb_query_version_hint": f"SDK {primary['version'][1:]}" if primary else None,
            "must_state_unknown": primary is None and not known,
        },
        "messages": messages,
    }


def human_output(result):
    print(f"内化版本：{result['internalized_version']}")
    if result["detected_version"]:
        detail = f"（来源={result['source']}，匹配={result['match']}"
        if result.get("build_variant"):
            detail += f"，构建变体={result['build_variant']}"
        print(f"探测版本：{result['detected_version']}{detail}）")
    else:
        print("探测版本：未知")
    for message in result["messages"]:
        print(f"提示：{message}")
    if result.get("in_version_history"):
        print(f"版本历史：{result['detected_version']} 在 V3 版本历史中，VO 差异：{result['history_vo_changes']}")
    print(f"版本标注：{result['canonical_version_note']}")


def main():
    parser = argparse.ArgumentParser(description="探测 AX615 VO SDK 版本并输出版本路由策略")
    parser.add_argument("--display-status", help="display_status 文件（- 表示从 stdin 读取，需显式写出）")
    parser.add_argument("--system-version", help="/proc/ax_proc/version 采集文件（- 表示从 stdin 读取，需显式写出）")
    parser.add_argument("--dmesg", help="dmesg/axdmesg 采集文件")
    parser.add_argument("--text", help="客户口述或其他版本文本")
    parser.add_argument("--known", action="store_true", help="仅输出内化版本")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()
    if not any((args.display_status, args.system_version, args.dmesg, args.text, args.known)):
        parser.error("至少提供一个版本来源或 --known")

    findings = []
    source_labels = []
    try:
        if args.display_status:
            source_labels.append("display_status")
            item = parse_display_status(read_input(args.display_status))
            if item:
                findings.append(item)
        if args.system_version:
            source_labels.append("system_version")
            item = parse_system_version(read_input(args.system_version))
            if item:
                findings.append(item)
        if args.dmesg:
            source_labels.append("dmesg")
            for item in parse_sdk_lines(read_input(args.dmesg), "dmesg"):
                item["source"] = "vo_library_log" if item.get("module") == "libax_vo.so" else "dmesg"
                findings.append(item)
        if args.text:
            source_labels.append("text")
            item = parse_customer_text(args.text)
            if item:
                findings.append(item)
        manifest = load_manifest()
    except (OSError, ValueError, KeyError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    result = build_result(findings, manifest, args.known)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        human_output(result)
    if findings or args.known:
        return 0
    # 2=输入里没有版本痕迹；3=给了文件但没解析出版本（未执行成功）
    return 3 if source_labels else 2


if __name__ == "__main__":
    sys.exit(main())
