#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
"""Evaluator-only checks for fastboot decisions; never part of runtime fixtures."""
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def load_input():
    request = json.loads(Path("request.json").read_text(encoding="utf-8"))
    inputs = [request["task"]]
    for attachment in request["attachments"]:
        path = Path(attachment)
        require(not path.is_absolute() and ".." not in path.parts, "Invalid attachment path")
        inputs.append(path.read_text(encoding="utf-8"))
    return "\n".join(inputs)


def validate(case_id, result, input_text):
    require(isinstance(result, dict), "Result must be an object")
    require(type(result.get("schema_version")) is int and result["schema_version"] == 1, "Invalid schema_version")
    require(result.get("phase") in {"Pre-Handover", "In-Handover", "Post-Handover", "Unknown"}, "Invalid phase")
    require(result.get("confidence") in {"supported", "suspected", "insufficient"}, "Invalid confidence")
    for key in ("diagnosis", "analysis"):
        require(isinstance(result.get(key), str) and result[key].strip(), "Missing " + key)
    evidence = result.get("evidence")
    require(isinstance(evidence, list) and evidence, "Missing input evidence")
    require(all(isinstance(e, str) and e.strip() and e in input_text for e in evidence), "Evidence must quote actual input")
    recommendations = result.get("recommendations")
    require(isinstance(recommendations, list) and recommendations, "Missing recommendations")
    operations = {"inspect", "configure", "initialize", "validate", "preserve", "request", "retain"}
    for item in recommendations:
        require(isinstance(item, dict), "Recommendation must be an object")
        require(item.get("operation") in operations, "Invalid recommendation operation")
        for key in ("target", "reason"):
            require(isinstance(item.get(key), str) and item[key].strip(), "Missing recommendation " + key)
    rejected = result.get("rejected_actions")
    require(isinstance(rejected, list) and all(isinstance(x, str) for x in rejected), "Invalid rejected_actions")

    def phase(expected):
        require(result["phase"] == expected, "Wrong handover phase")

    def quotes(*anchors):
        for anchor in anchors:
            require(any(anchor in e for e in evidence), "Missing decisive input evidence: " + anchor)

    def action(targets, allowed):
        if isinstance(targets, str):
            targets = {targets}
        if isinstance(allowed, str):
            allowed = {allowed}
        require(any(r["target"] in targets and r["operation"] in allowed for r in recommendations),
                "Missing recommendation: " + str(targets) + " / " + str(allowed))

    def reject(*names):
        require(set(names).issubset(rejected), "Unsafe alternative was not rejected")

    if case_id == 1:
        phase("Pre-Handover")
        quotes("rtos_i2c_claim_mask=0x7", "ax_i2c0 busy, rtos using", "handover request has not been sent")
        plan = result.get("i2c_plan", {})
        require(plan.get("rtos_channels") == [1] and plan.get("linux_channels") == [0], "Wrong I2C ownership plan")
        require(type(plan.get("claim_bitmap")) is int and plan["claim_bitmap"] == 2, "Wrong channel bitmap")
        require(type(plan.get("dummy_status_bits")) is int and plan["dummy_status_bits"] == 8, "Channel bitmap and register bit offset must be distinguished")
        require(plan.get("preserve_arbitration") is True, "Must retain Linux arbitration")
        action("rtos_i2c_claim_mask", "configure")
        action("AX_DUMMY_SW6_ADDR", {"inspect", "validate"})
        reject("bypass_i2c_arbitration")
    else:
        raise AssertionError("Unknown case id")

validate(1, json.loads(Path('out/result.json').read_text(encoding='utf-8')), load_input())
PY
