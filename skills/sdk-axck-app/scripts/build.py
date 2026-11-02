"""
axck-tool build command
Inspects, dry-runs, and executes build tasks for camera-kit modules.
"""
import os
import sys
import subprocess
from typing import Dict, Any, List, Optional

VALID_MODULES = ["3rd", "com", "service", "client", "apps", "apps/test", "apps/dvcam"]
VALID_TARGETS = ["all", "install", "clean"]

def find_camera_kit_root(start_dir: str) -> Optional[str]:
    curr = os.path.abspath(start_dir)
    while curr and curr != "/":
        if os.path.exists(os.path.join(curr, "Makefile")) and os.path.exists(os.path.join(curr, "service")) and os.path.exists(os.path.join(curr, "client")):
            return curr
        # Check subfolder
        candidate = os.path.join(curr, "camera-kit")
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "Makefile")):
            return candidate
        curr = os.path.dirname(curr)
    return None

def inspect_build_env(ck_root: str) -> Dict[str, Any]:
    sdk_root = os.path.dirname(ck_root)
    build_dir = os.path.join(sdk_root, "build")
    project_mak = os.path.join(build_dir, "project.mak")
    config_mak = os.path.join(build_dir, "config.mak")
    
    current_project = os.environ.get("PROJECT", "Unknown")
    
    # Check available projects
    projects = []
    p_dir = os.path.join(build_dir, "projects")
    if os.path.isdir(p_dir):
        projects = [d for d in os.listdir(p_dir) if os.path.isdir(os.path.join(p_dir, d))]

    return {
        "camera_kit_root": ck_root,
        "sdk_root": sdk_root,
        "current_project": current_project,
        "available_projects": sorted(projects),
        "build_subdirs": ["3rd", "com", "service", "client", "apps"],
        "apps_subdirs": ["test", "dvcam"],
        "has_build_env": os.path.exists(config_mak)
    }

def run_build(
    ck_root: str,
    module: Optional[str] = None,
    target: str = "all",
    project: Optional[str] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    env_info = inspect_build_env(ck_root)
    env = os.environ.copy()
    if project:
        env["PROJECT"] = project

    make_cmd = ["make"]
    workdir = ck_root

    if module:
        if module in ["apps/test", "test"]:
            workdir = os.path.join(ck_root, "apps/test")
        elif module in ["apps/dvcam", "dvcam"]:
            workdir = os.path.join(ck_root, "apps/dvcam")
        elif module in ["3rd", "com", "service", "client", "apps"]:
            workdir = os.path.join(ck_root, module)
        else:
            return {
                "success": False,
                "error": f"Invalid module: '{module}'. Allowed: {VALID_MODULES}"
            }

    if target:
        make_cmd.append(target)

    cmd_str = f"cd {workdir} && PROJECT={env.get('PROJECT', '')} {' '.join(make_cmd)}"

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "command": cmd_str,
            "workdir": workdir,
            "target": target,
            "module": module or "all",
            "project": env.get("PROJECT")
        }

    try:
        proc = subprocess.run(
            make_cmd,
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True
        )
        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "command": cmd_str,
            "stdout": proc.stdout,
            "stderr": proc.stderr
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": cmd_str
        }
