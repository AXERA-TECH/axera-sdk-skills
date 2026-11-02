#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
board_driver.py - Self-contained OxideTerm / Serial Terminal automation driver for AXCK.
Follows the agent-skills specification:
- ZERO hardcoded tokens or connection IDs.
- Configurable via CLI arguments or environment variables:
  OXIDETERM_TOKEN, OXIDETERM_URL, OXIDETERM_CONNECTION_REF, OXIDETERM_TERMINAL_REF
- Automatic fallback discovery from local environment configuration (OpenCode config and a local session tracker file).
"""

import os
import sys
import json
import time
import re
import socket
import urllib.request
import urllib.error

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)


def _discover_default_token():
    """Discover OxideTerm token from environment or local OpenCode config."""
    env_token = os.environ.get("OXIDETERM_TOKEN", "").strip()
    if env_token:
        return env_token
    cfg_path = os.path.expanduser("~/.config/opencode/opencode.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            headers = cfg.get("mcp", {}).get("oxideterm", {}).get("headers", {})
            auth = headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                return auth[len("Bearer "):].strip()
        except Exception:
            pass
    return ""


def _discover_default_terminal():
    """Discover active terminal ref from environment or local session tracker."""
    env_term = os.environ.get("OXIDETERM_TERMINAL_REF", "").strip()
    if env_term:
        return env_term
    t_file = os.path.expanduser("~/scripts/.current_terminal")
    if os.path.exists(t_file):
        try:
            with open(t_file, "r", encoding="utf-8") as f:
                ref = f.read().strip()
                if ref:
                    return ref
        except Exception:
            pass
    return ""


class BoardSerialDriver:
    def __init__(self, token=None, url=None, connection_ref=None, terminal_ref=None):
        self.token = token or _discover_default_token()
        self.url = url or os.environ.get("OXIDETERM_URL", "http://127.0.0.1:3412/mcp")
        self.connection_ref = connection_ref or os.environ.get("OXIDETERM_CONNECTION_REF", "")
        self.terminal_ref = terminal_ref or _discover_default_terminal()

    def call_mcp(self, name, args):
        if not self.token:
            raise ValueError("OxideTerm token not provided. Pass --token, set OXIDETERM_TOKEN, or configure ~/.config/opencode/opencode.json.")
        req_body = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": "tools/call",
            "params": {"name": name, "arguments": args}
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(req_body).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.URLError as e:
            return {"error": str(e)}

    def get_board_ip(self, iface="eth0"):
        """Get board IP via serial ifconfig or environment variable."""
        env_ip = os.environ.get("AXCK_BOARD_IP")
        if env_ip:
            return env_ip
        # Fallback to reading ifconfig from terminal output
        lines = self.read_lines(limit=25, tail=True)
        for l in lines:
            m = re.search(r"inet addr:\s*([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", l)
            if m:
                return m.group(1)
        return None

    def acquire_terminal(self, title="AXCK-Console", cols=120, rows=40):
        if self.terminal_ref:
            st = self.call_mcp("terminals_state", {"terminal_ref": self.terminal_ref})
            if "result" in st:
                print(f"[Driver] Reusing active terminal: {self.terminal_ref}")
                return self.terminal_ref

        if not self.connection_ref:
            raise ValueError("connection_ref required to open a new terminal. Pass --connection-ref or set OXIDETERM_CONNECTION_REF.")

        res = self.call_mcp("terminals_open", {
            "title": title,
            "cols": cols,
            "rows": rows,
            "source": {
                "kind": "connection",
                "connection_ref": self.connection_ref
            }
        })
        outcome = res.get("result", {}).get("structuredContent", {}).get("outcome")
        if outcome == "completed":
            self.terminal_ref = res["result"]["structuredContent"]["data"]["terminal"]["terminal_ref"]
            print(f"[Driver] Acquired new terminal: {self.terminal_ref}")
            return self.terminal_ref
        
        err = res.get("result", {}).get("structuredContent", {}).get("error", str(res))
        raise RuntimeError(f"Failed to acquire terminal: {err}")

    def close_terminal(self):
        if not self.terminal_ref:
            return True
        res = self.call_mcp("terminals_close", {"terminal_ref": self.terminal_ref})
        self.terminal_ref = None
        return res

    def send(self, text, append_enter=True):
        if not self.terminal_ref:
            raise RuntimeError("Terminal not acquired.")
        # Ensure text is string and carriage return if needed
        txt = str(text)
        if append_enter and not txt.endswith("\n") and not txt.endswith("\r"):
            txt += "\r\n"
        return self.call_mcp("terminals_submit", {
            "terminal_ref": self.terminal_ref,
            "text": txt,
            "append_enter": False
        })

    def read_lines(self, limit=80, tail=False):
        """
        Read terminal lines.
        In OxideTerm MCP, lines is a list of strings [str, ...].
        tail=False reads from top (retains menus and headers).
        """
        if not self.terminal_ref:
            raise RuntimeError("Terminal not acquired.")
        res = self.call_mcp("terminals_read", {
            "terminal_ref": self.terminal_ref,
            "line_limit": limit,
            "tail": tail
        })
        raw_lines = res.get("result", {}).get("structuredContent", {}).get("data", {}).get("lines", [])
        clean_lines = []
        for line in raw_lines:
            if isinstance(line, dict):
                t = line.get("text", "")
            else:
                t = str(line)
            t = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', t)
            clean_lines.append(t)
        return clean_lines

    def get_current_menu(self):
        lines = self.read_lines(limit=80, tail=False)
        non_empty = [l.strip() for l in lines if l.strip()]

        # Check if currently waiting at a secondary interactive input prompt (NOT settled menu)
        full_text = "\n".join(non_empty)
        if any(p in full_text for p in [
            'select new front sub reslution:',
            'select front front main reslution:',
            'Input front venc type',
            'Input front sns mode',
            'Input front mirror',
            'Input front flip',
            'Input record time',
            'Input volume'
        ]):
            # If the last interactive prompt was not followed by a menu redraw or success
            last_lines = "\n".join(non_empty[-6:])
            if any(p in last_lines for p in [
                'select new front sub reslution:',
                'select front front main reslution:',
                'Input front venc type',
                'Input front sns mode',
                'Input front mirror',
                'Input front flip',
                'Input record time',
                'Input volume'
            ]):
                return 'prompt'

        for line in reversed(non_empty):
            if line.endswith('/ #') or line.endswith('#') or line.endswith('/opt/bin #') or '-/bin/sh:' in line:
                return 'shell'
            if 'Media api options:' in line:
                return 'media'
            if 'Storage api options:' in line:
                return 'storage'
            if 'Dtcf api options:' in line:
                return 'dtcf'
            if 'Device api options:' in line:
                return 'device'
            if 'Options:' in line or '1. Media api test.' in line:
                return 'main'

        # If top lines got scrolled off by recent logs, check presence across all buffer lines
        full_text = "\n".join(non_empty)
        if 'Media api options:' in full_text or '2. Get front FPS.' in full_text or '28. Capture image.' in full_text:
            return 'media'
        if 'Storage api options:' in full_text or '1. Get storage status' in full_text:
            return 'storage'
        if 'Dtcf api options:' in full_text or '1. Dump dtcf info' in full_text:
            return 'dtcf'
        if 'Device api options:' in full_text or '4. Query all status' in full_text:
            return 'device'
        if '1. Media api test.' in full_text:
            return 'main'

        return 'unknown'

    def wait_prompt(self, prompt_keywords, timeout=6.0, poll_interval=0.05):
        """
        Poll terminal until one of prompt_keywords appears.
        Replaces arbitrary time.sleep with event-driven synchronization.
        """
        if isinstance(prompt_keywords, str):
            prompt_keywords = [prompt_keywords]
        deadline = time.time() + timeout
        while time.time() < deadline:
            lines = self.read_lines(limit=80, tail=False)
            text = "\n".join(lines)
            for kw in prompt_keywords:
                if kw in text:
                    return True, text
            time.sleep(poll_interval)
        return False, "\n".join(self.read_lines(limit=80, tail=False))

    def wait_menu(self, expected_menu, timeout=8.0, poll_interval=0.08):
        """
        Poll terminal until get_current_menu() equals expected_menu.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            cur = self.get_current_menu()
            if cur == expected_menu:
                return True
            time.sleep(poll_interval)
        return False

    def send_interactive_choice(self, option_cmd, prompt_kw, sub_choice, settle_menu="media", timeout=6.0):
        """
        Reliable two-phase interactive menu execution with zero blind sleeping:
        1. Send parent option command (e.g. '11', '7', '8', '12', '32')
        2. Wait for sub-prompt keyword (e.g. 'Input front venc type', 'select front front main')
        3. Send sub_choice (e.g. '0', '1', '2')
        4. Wait for menu to settle back to expected menu
        """
        # Step 1: Send option
        self.send(str(option_cmd), append_enter=True)

        # Step 2: Wait for secondary prompt
        ok, text = self.wait_prompt(prompt_kw, timeout=timeout)
        if not ok:
            return False, f"Prompt '{prompt_kw}' not seen, timed out"

        # Step 3: Send sub-choice
        self.send(str(sub_choice), append_enter=True)

        # Step 4: Wait for menu to return
        if settle_menu:
            menu_ok = self.wait_menu(settle_menu, timeout=timeout)
            return menu_ok, text

        return ok, text

    def ensure_in_main_menu(self, max_retries=6):
        """
        Safely return to main menu.
        CRITICAL: Never send '0' if already in 'main', because '0' in main menu is 'Exit test.'!
        """
        deadline = time.time() + 15.0
        while time.time() < deadline:
            menu = self.get_current_menu()
            if menu == "main":
                return True
            if menu in ("media", "storage", "dtcf", "device"):
                self.send("0", append_enter=True)
                if self.wait_menu("main", timeout=2.5):
                    return True
            elif menu == "shell":
                print("  [Driver: AUTO-RECOVER] Shell detected, comm-scan killing axck processes and relaunching axck_test...")
                # comm-scan kill catches daemonized empty-argv axck_service that
                # killall misses; removing /tmp/axck.ipc prevents EADDRINUSE for the
                # service freshly spawned by the new axck_test (nanomsg nn_bind).
                self.send(
                    "for p in /proc/[0-9]*; do c=$(cat $p/comm 2>/dev/null); "
                    'case "$c" in axck_test|axck_service) kill -9 ${p#/proc/} 2>/dev/null;; esac; done; '
                    "rm -f /tmp/axck.ipc", append_enter=True)
                time.sleep(1.0)
                self.send("cd /opt/bin && ./axck_test -t 2 -l 2", append_enter=True)
                if self.wait_menu("main", timeout=12.0):
                    return True
            else:
                self.send("", append_enter=True)
                time.sleep(0.2)
        return self.get_current_menu() == "main"

    def navigate_to(self, target_menu, timeout=5.0):
        menu_map = {
            "main": 0,
            "media": 1,
            "storage": 2,
            "dtcf": 3,
            "device": 4
        }
        if target_menu not in menu_map:
            raise ValueError(f"Unknown target menu: {target_menu}")
        if target_menu == "main":
            return self.ensure_in_main_menu()

        cur = self.get_current_menu()
        if cur == target_menu:
            return True

        if not self.ensure_in_main_menu():
            return False

        self.send(str(menu_map[target_menu]), append_enter=True)
        return self.wait_menu(target_menu, timeout=timeout)

    def wait_keyword(self, keywords, timeout=8.0, poll_interval=0.06):
        if isinstance(keywords, str):
            keywords = [keywords]
        start_time = time.time()
        while time.time() - start_time < timeout:
            lines = self.read_lines(limit=45, tail=False)
            full_text = "\n".join(lines)
            for kw in keywords:
                if kw in full_text:
                    return True, full_text
            time.sleep(poll_interval)
        return False, "\n".join(self.read_lines(limit=45, tail=False))

