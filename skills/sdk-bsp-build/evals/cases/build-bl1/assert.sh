#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
"""Evaluator-only decisions. Never install this module or expose it as a fixture."""
import json
from pathlib import Path

SDK = "/work/sdk/ax615"
PROJECT = "AX615_fastnor"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def validate(case_id, result):
    require(isinstance(result, dict), "Result must be an object")
    require(type(result.get("schema_version")) is int and result["schema_version"] == 1, "Invalid schema_version")
    require(result.get("sdk_root") == SDK, "Wrong SDK root")
    require(isinstance(result.get("analysis"), str) and result["analysis"].strip(), "Missing analysis")
    require(result.get("status") == "planned", "Offline evaluation must not claim execution")
    specs = {
        1: ("inspection", "build", ["plist"], None),
        2: ("full", "build", ["clean", "all", "install", "axp"], 64),
        3: ("module", "boot/bl1", ["clean", "all", "install"], 64),
        4: ("module", "kernel/linux", ["clean", "all", "install"], 64),
        5: ("fast AXP", "build/projects/" + PROJECT, ["clean", "all", "install", "axp"], None),
    }
    require(case_id in specs, "Unknown case id")
    workflow, cwd, targets, parallel = specs[case_id]
    project = None if case_id == 1 else PROJECT
    require(result.get("workflow") == workflow, "Wrong workflow")
    require("project" in result and result["project"] == project, "Wrong result project")
    commands = result.get("commands")
    require(isinstance(commands, list) and len(commands) == 1, "Expected exactly one command")
    command = commands[0]
    require(isinstance(command, dict), "Invalid command")
    require(command.get("cwd") == SDK + "/" + cwd, "Wrong command cwd")
    require("project" in command and command["project"] == project, "Wrong command project")
    require(command.get("targets") == targets, "Wrong target sequence")
    require("parallel" in command and command["parallel"] == parallel, "Wrong parallel setting")
    if parallel is not None:
        require(type(command["parallel"]) is int, "Parallel setting must be an integer")
    prerequisites = result.get("prerequisites", [])
    require(isinstance(prerequisites, list) and all(isinstance(p, str) for p in prerequisites), "Invalid prerequisites")
    if case_id == 1:
        require(not result.get("projects"), "Do not invent unexecuted plist output")
        require(not result.get("modules") and not result.get("conditional_modules"), "Only discover projects")
    else:
        require("project_confirmed_by_plist" in prerequisites, "Project must be confirmed by live plist")
    if case_id == 5:
        require("full_build_succeeded_for_same_project" in prerequisites, "Full build must succeed before fast AXP")
        require(result.get("full_build_project") == PROJECT, "Full build must match selected project")

validate(3, json.loads(Path('out/result.json').read_text(encoding='utf-8')))
PY
