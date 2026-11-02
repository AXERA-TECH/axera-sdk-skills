#!/usr/bin/env python3
"""Validate the AX dataflow log bundle before root-cause analysis."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Artifact:
    filename: str
    description: str
    marker_groups: tuple[tuple[str, ...], ...]


ARTIFACTS = (
    Artifact(
        "serial.log",
        "应用启动至异常后的连续串口",
        (("APP Ver:", "SDK Ver:", "[SDK version]"),),
    ),
    Artifact(
        "syslog.log",
        "覆盖复现窗口的板端 syslog",
        (("Kernel:", "AXLOG", "[SYS]", "[IVPS]", "[VIN]", "[VENC]"),),
    ),
    Artifact("logctl.proc", "调级后的 /proc/ax_proc/logctl", ()),
    Artifact(
        "vin.proc",
        "VIN attr/statistics/mode/ife_itp_hsk",
        (("VIN GLB ATTR", "VIN DEV ATTR"), ("VIN DEV STATISTICS", "VIN PIPE STATISTICS")),
    ),
    Artifact(
        "ivps.proc",
        "IVPS 与 ivps_sched",
        (("IVPS VERSION",), ("IVPS SCHED DEBUG",)),
    ),
    Artifact(
        "venc.proc",
        "VENC proc",
        (("VENC CHN ATTR",), ("VENC CHN STATUS",)),
    ),
    Artifact(
        "link.proc",
        "link_table/link_table_kernel/vin_ivps_mode/syncagent",
        (("Link Table V2",), ("Link Table Kernel V2",)),
    ),
)

LOGCTL_EXPECTED = {"VIN": (17, 6), "IVPS": (13, 6), "VENC": (7, 6)}

CAPTURE_COMMANDS = {
    "logctl.proc": """echo ulog 17 6 > /proc/ax_proc/logctl
echo ulog 13 6 > /proc/ax_proc/logctl
echo ulog 7 6 > /proc/ax_proc/logctl
cat /proc/ax_proc/logctl > /tmp/ax-dataflow-input/logctl.proc""",
    "vin.proc": """{
  for node in attr statistics mode ife_itp_hsk; do
    echo \"===== /proc/ax_proc/vin/$node =====\"
    cat \"/proc/ax_proc/vin/$node\"
  done
} > /tmp/ax-dataflow-input/vin.proc""",
    "ivps.proc": """{
  for node in /proc/ax_proc/ivps /proc/ax_proc/ivps_sched; do
    echo \"===== $node =====\"
    cat \"$node\"
  done
} > /tmp/ax-dataflow-input/ivps.proc""",
    "venc.proc": "cat /proc/ax_proc/venc > /tmp/ax-dataflow-input/venc.proc",
    "link.proc": """{
  for node in /proc/ax_proc/link_table /proc/ax_proc/link_table_kernel \\
              /proc/ax_proc/sys/vin_ivps_mode /proc/ax_proc/syncagent; do
    echo \"===== $node =====\"
    cat \"$node\"
  done
} > /tmp/ax-dataflow-input/link.proc""",
    "syslog.log": """LOGSERVICE_PID=$(pidof logserviced | awk '{print $1}')
SYSLOG_PATH=
for fd in /proc/$LOGSERVICE_PID/fd/*; do
  path=$(readlink \"$fd\")
  case \"$path\" in /tmp/data/AXSyslog/syslog/*.log) SYSLOG_PATH=$path; break;; esac
done
[ -n \"$SYSLOG_PATH\" ] || { echo \"未找到 logserviced 当前 syslog\" >&2; exit 1; }
cp \"$SYSLOG_PATH\" /tmp/ax-dataflow-input/syslog.log""",
    "serial.log": "通过当前板卡会话从应用启动前开启串口录制，持续到首次异常及传播现象出现，保存为 serial.log。",
}


def validate_logctl(text: str) -> list[str]:
    rows: dict[str, tuple[int, int]] = {}
    pattern = re.compile(r"^\s*(VIN|IVPS|VENC)\s+(\d+)\s+(\d+)\s+\d+\s*$", re.MULTILINE)
    for module, module_id, user_level in pattern.findall(text):
        rows[module] = (int(module_id), int(user_level))

    issues = []
    for module, expected in LOGCTL_EXPECTED.items():
        actual = rows.get(module)
        if actual is None:
            issues.append(f"logctl.proc 未找到 {module} 的 level(U)")
        elif actual != expected:
            issues.append(
                f"logctl.proc 中 {module} 为 id={actual[0]}, level(U)={actual[1]}，"
                f"期望 id={expected[0]}, level(U)={expected[1]}"
            )
    return issues


def validate(input_dir: Path) -> tuple[list[str], set[str]]:
    issues: list[str] = []
    recapture: set[str] = set()

    if not input_dir.is_dir():
        return [f"输入目录不存在或不是目录：{input_dir}"], {item.filename for item in ARTIFACTS}

    for artifact in ARTIFACTS:
        path = input_dir / artifact.filename
        if not path.is_file():
            issues.append(f"缺少 {artifact.filename}：{artifact.description}")
            recapture.add(artifact.filename)
            continue
        try:
            size = path.stat().st_size
        except OSError as error:
            issues.append(f"无法检查 {artifact.filename}：{error}")
            recapture.add(artifact.filename)
            continue
        if size == 0:
            issues.append(f"{artifact.filename} 为空：{artifact.description}")
            recapture.add(artifact.filename)
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            issues.append(f"无法读取 {artifact.filename}：{error}")
            recapture.add(artifact.filename)
            continue
        for alternatives in artifact.marker_groups:
            if not any(marker in text for marker in alternatives):
                choices = " / ".join(alternatives)
                issues.append(f"{artifact.filename} 缺少内容标记：{choices}")
                recapture.add(artifact.filename)

        if artifact.filename == "logctl.proc":
            logctl_issues = validate_logctl(text)
            issues.extend(logctl_issues)
            if logctl_issues:
                recapture.add(artifact.filename)

    return issues, recapture


def print_capture_plan(recapture: set[str]) -> None:
    print("\n补采指令（板端先执行 mkdir -p /tmp/ax-dataflow-input）：")
    print("\n[采集前 userlog 门禁]")
    print(CAPTURE_COMMANDS["logctl.proc"])
    for artifact in ARTIFACTS:
        if artifact.filename == "logctl.proc" or artifact.filename not in recapture:
            continue
        print(f"\n[{artifact.filename}]")
        print(CAPTURE_COMMANDS[artifact.filename])
    print("\n将板端文件传回输入目录后重新运行本检查。")
    if {"serial.log", "syslog.log"} & recapture:
        print("serial.log 或 syslog.log 缺失时必须重新复现并采集完整一组，不能与旧轮次 proc 混用。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="包含七项 AX dataflow 输入的目录")
    args = parser.parse_args()

    issues, recapture = validate(args.input_dir)
    if not issues:
        print(f"PASS: {args.input_dir} 的 7 项 AX dataflow 输入完整。")
        return 0

    print(f"INCOMPLETE: {args.input_dir} 未通过输入完整性门禁。")
    for issue in issues:
        print(f"- {issue}")
    print_capture_plan(recapture)
    return 2


if __name__ == "__main__":
    sys.exit(main())
