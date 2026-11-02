#!/usr/bin/env python3
"""Render a validated diagnosis verbatim, without inventing findings or acceptance."""
import argparse
import json
from pathlib import Path

from analyze import local_file, read_json
from validate_report import validate, validate_output


def render(data):
    lines = ["# AEC 诊断报告", "", "## 结论与证据", "", data["summary"], "",
             "处理状态：" + data["status"], "分类：" + data["classification"]]
    for item in data["evidence"]:
        lines.extend(["", "- " + item["observation"], "  出处：" + item["source"]])
    if data["hypotheses"]:
        lines.extend(["", "### 待验证解释", ""] + ["- " + h for h in data["hypotheses"]])
    lines.extend(["", "## 处理步骤"])
    for index, item in enumerate(data["actions"], 1):
        lines.extend(["", f"### {index}. " + item["change"], ""])
        for key, label in (("reason", "依据"), ("expected", "预期"),
                           ("falsifier", "反证"), ("rollback", "回退")):
            lines.append("- " + label + "：" + item[key])
    lines.extend(["", "## 复测结果"])
    for item in data["regression"]:
        lines.extend(["", "- " + item["scenario"] + "：" + item["status"],
                      "  判据：" + item["criterion"], "  证据或未执行原因：" + item["evidence"]])
    lines.extend(["", "## 缺项与下一步", ""])
    lines.extend("- " + item for item in data["missing_evidence"])
    if data["resolution_evidence"]:
        lines.extend(["", "### 解决依据", ""] + ["- " + x for x in data["resolution_evidence"]])
    # Keep optional model-authored fields too; never silently drop extra evidence.
    known = {"schema_version", "summary", "status", "classification", "evidence", "hypotheses",
             "actions", "regression", "missing_evidence", "resolution_evidence"}
    extra = {k: v for k, v in data.items() if k not in known}
    for field, keys in (("evidence", {"source", "observation"}),
                        ("actions", {"change", "reason", "expected", "falsifier", "rollback"}),
                        ("regression", {"scenario", "status", "criterion", "evidence"})):
        additions = {str(i): {k: v for k, v in row.items() if k not in keys}
                     for i, row in enumerate(data[field]) if set(row) - keys}
        if additions:
            extra[field] = additions
    if extra:
        lines.extend(["", "## 补充字段（diagnosis.json 原值）", ""])
        lines.extend("    " + line for line in json.dumps(
            extra, ensure_ascii=False, indent=2, allow_nan=False).splitlines())
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        base = args.out.resolve()
        data = validate(read_json(local_file(base, "diagnosis.json")), base)
        measurement = read_json(local_file(base, "measurements.json"))
        if not isinstance(measurement, dict) or measurement.get("status") not in ("measured", "needs_evidence"):
            raise ValueError("Invalid measurement status")
        if not local_file(base, "measurements.md").stat().st_size:
            raise ValueError("Empty measurements.md")
        # Existing reports need explicit removal by the caller before regeneration.
        with (base / "diagnosis.md").open("x", encoding="utf-8") as stream:
            stream.write(render(data))
        validate_output(base)
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
    print("PASS: diagnosis rendered and report structure validated; acoustic outcome requires independent verification")


if __name__ == "__main__":
    main()
