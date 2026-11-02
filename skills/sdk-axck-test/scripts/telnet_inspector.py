import os
import telnetlib
import time
import re
import socket


class TelnetInspector:
    """Out-of-band board inspector using Telnet.

    Allows concurrent inspection of /proc, logs, and process states while
    axck_test or other foreground tools run on the serial console.
    """

    def __init__(
        self,
        host=None,
        port=23,
        username="root",
        password="12345",
        timeout=5.0,
    ):
        self.host = host or os.environ.get("AXCK_BOARD_IP", "127.0.0.1")
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.tn = None

    def connect(self, retries=3, delay=1.0):
        """Connect and authenticate to board Telnet daemon."""
        for attempt in range(1, retries + 1):
            try:
                self.tn = telnetlib.Telnet(
                    self.host, self.port, timeout=self.timeout
                )
                idx, match, text = self.tn.expect(
                    [b"login:", b"/root # ", b"/ # "], timeout=self.timeout
                )
                if b"login:" in text:
                    self.tn.write(self.username.encode("ascii") + b"\n")
                    idx, match, text = self.tn.expect(
                        [b"Password:", b"/root # ", b"/ # "], timeout=self.timeout
                    )
                    if b"Password:" in text and self.password:
                        self.tn.write(self.password.encode("ascii") + b"\n")
                    elif b"Password:" in text:
                        self.tn.write(b"\n")
                    self.tn.expect([b"/root # ", b"/ # "], timeout=self.timeout)
                return True
            except Exception as e:
                if attempt == retries:
                    raise ConnectionError(
                        f"Failed to connect to Telnet {self.host}:{self.port}: {e}"
                    )
                time.sleep(delay)
        return False

    def exec_cmd(self, cmd, timeout=5.0):
        """Execute a shell command and return clean output lines."""
        if not self.tn:
            raise RuntimeError("Telnet is not connected")
        # Flush pending buffer
        try:
            self.tn.read_very_eager()
        except Exception:
            pass

        self.tn.write(cmd.encode("utf-8") + b"\n")
        # Match shell prompt (handle varied prompts: /root #, /opt/bin #, / #)
        _, match, out = self.tn.expect([b"\r\n/root # ", b"\n/root # ", b"/root # ", b"\r\n/opt/bin # ", b"\n/opt/bin # ", b"/opt/bin # ", b"\r\n/ # ", b"\n/ # ", b"# "], timeout=timeout)
        text = out.decode("utf-8", errors="ignore")
        raw_lines = text.splitlines()
        clean = []
        for line in raw_lines[1:]:
            s = line.strip()
            # If prompt was attached at the end without newline, strip prompt
            if s.endswith("/root #"):
                s = s[:-7].strip()
            elif s.endswith("#"):
                s = s[:-1].strip()
            if s:
                clean.append(s)
        return clean

    def get_ivps_info(self):
        """Parse /proc/ax_proc/ivps CHN INFO and FILTER INFO tables.
        
        Note: CHN INFO OutputW/OutputH shows initial static pool configuration,
        while FILTER INFO DstW/DstH shows real-time active scaling resolution!
        """
        try:
            lines = self.exec_cmd("cat /proc/ax_proc/ivps")
        except Exception:
            return {}

        channels = {}
        in_chn = False
        in_flt = False

        for l in lines:
            if "CHN INFO" in l:
                in_chn = True
                continue
            if in_chn and "FILTER INFO" in l:
                in_chn = False
                in_flt = True
                continue
            if in_flt and "FILTER STATE" in l:
                in_flt = False
                break

            if in_chn:
                parts = l.split()
                if (
                    len(parts) >= 15
                    and parts[0].isdigit()
                    and parts[1].isdigit()
                ):
                    try:
                        grp = int(parts[0])
                        chn = int(parts[1])
                        w = int(parts[7])
                        h = int(parts[8])
                        in_fps = float(parts[13])
                        out_fps = float(parts[14])
                        channels[(grp, chn)] = {
                            "w": w,
                            "h": h,
                            "in_fps": in_fps,
                            "out_fps": out_fps,
                        }
                    except (ValueError, IndexError):
                        continue

            elif in_flt:
                parts = l.split()
                if (
                    len(parts) >= 6
                    and parts[0].isdigit()
                    and parts[1].isdigit()
                ):
                    try:
                        grp = int(parts[0])
                        chn = int(parts[1])
                        # DstW is index 4, DstH is index 5 in FILTER INFO
                        dst_w = int(parts[4])
                        dst_h = int(parts[5])
                        if (grp, chn) in channels:
                            channels[(grp, chn)]["w"] = dst_w
                            channels[(grp, chn)]["h"] = dst_h
                    except (ValueError, IndexError):
                        continue

        return channels

    def get_venc_info(self):
        """Parse /proc/ax_proc/venc attributes and status."""
        try:
            lines = self.exec_cmd("cat /proc/ax_proc/venc")
        except Exception:
            return {}

        channels = {}
        in_attr1 = False
        for l in lines:
            if "VENC CHN ATTR 1" in l:
                in_attr1 = True
                continue
            if in_attr1 and "VENC CHN ATTR 2" in l:
                break
            if in_attr1:
                parts = l.split()
                if len(parts) >= 8 and parts[0].isdigit():
                    try:
                        chn = int(parts[0])
                        vtype = parts[2]
                        w_src = int(parts[5])
                        h_src = int(parts[6])
                        channels[chn] = {
                            "type": vtype,
                            "w": w_src,
                            "h": h_src,
                            "recv_fps": 0.0,
                            "bitrate": 0.0,
                        }
                    except (ValueError, IndexError):
                        continue

        in_status2 = False
        for l in lines:
            if "VENC CHN STATUS 2" in l:
                in_status2 = True
                continue
            if in_status2 and ("NodeCnt" in l or "VENC CHN ATTR" in l):
                break
            if in_status2:
                parts = l.split()
                # VeChn bRecv FrmRecv RecvFps DiscardedNum SubMitCnt SubMitFail RecvBsCnt BsFrmCnt OutFps BitRate(kbps) ...
                if len(parts) >= 10 and parts[0].isdigit() and parts[1] in ("Y", "N"):
                    try:
                        chn = int(parts[0])
                        recv_fps = float(parts[3])
                        out_fps = float(parts[9])
                        bitrate = float(parts[10]) if len(parts) >= 11 else 0.0
                        if chn in channels:
                            channels[chn]["recv_fps"] = recv_fps
                            channels[chn]["out_fps"] = out_fps
                            channels[chn]["bitrate"] = bitrate
                    except (ValueError, IndexError):
                        continue

        return channels

    def get_venc_status0(self):
        """Parse VENC CHN STATUS 0 for encoding health metrics.

        Returns dict keyed by channel ID with:
          send_cnt, enc_suc_cnt, drop_bs_cnt, error_cnt,
          buf_full_cnt, timeout_cnt, send_fail
        These are cumulative counters; use two snapshots to compute deltas.
        """
        try:
            lines = self.exec_cmd("cat /proc/ax_proc/venc")
        except Exception:
            return {}

        status = {}
        in_status0 = False
        for l in lines:
            if "VENC CHN STATUS 0" in l:
                in_status0 = True
                continue
            if in_status0 and ("VENC CHN STATUS 1" in l or "VENC CHN ATTR" in l
                               or "VENC STREAM" in l or "VENC CHN HSK" in l):
                break
            if in_status0:
                parts = l.split()
                # Header: ChnId interChn AutoFps RatDrpCnt NoFreeCnt DiscardCnt
                #         NoNeedEnc Send2EncCnt Send2EncFail EncSucCnt ReEncCnt
                #         DropBsCnt ErrorCnt StopCnt BufFullCnt TimeOutCnt
                if len(parts) >= 13 and parts[0].isdigit():
                    try:
                        chn = int(parts[0])
                        status[chn] = {
                            "send_cnt": int(parts[7]),
                            "send_fail": int(parts[8]),
                            "enc_suc_cnt": int(parts[9]),
                            "re_enc_cnt": int(parts[10]),
                            "drop_bs_cnt": int(parts[11]),
                            "error_cnt": int(parts[12]),
                            "buf_full_cnt": int(parts[14]) if len(parts) >= 15 else 0,
                            "timeout_cnt": int(parts[15]) if len(parts) >= 16 else 0,
                        }
                    except (ValueError, IndexError):
                        continue
        return status

    def get_dmesg_errors(self):
        lines = self.exec_cmd("dmesg | grep -iE 'error|fail|oops|panic' 2>/dev/null")
        return [l for l in lines if l.strip() and not l.startswith("dmesg")][-20:]

    def get_process_pid(self, process_name):
        lines = self.exec_cmd(f"ps | grep {process_name} | grep -v grep 2>/dev/null")
        for l in lines:
            parts = l.split()
            if len(parts) >= 4 and parts[0].isdigit():
                pid = int(parts[0])
                cmd = parts[3]
                if cmd.startswith("[") and cmd.endswith("]"):
                    status_lines = self.exec_cmd(f"cat /proc/{pid}/status 2>/dev/null | grep State")
                    if any("zombie" in sl.lower() for sl in status_lines):
                        continue
                return pid
        return None

    def comm_scan_axck_pids(self, alive_only=True):
        """Deterministic axck PID discovery via /proc comm scan.

        Unlike `ps | grep`, this catches daemonized processes whose argv was
        cleared (shown as `[axck_service]` in ps) and is immune to ps format drift.

        alive_only=True (default) skips zombies (stat field #3 == 'Z'): a defunct
        process no longer holds the RPC ipc socket, so it must not be reported as
        a live residual (Case5 gate false-negative observed with reaped-but-unreaped
        daemon children whose /proc/<pid>/comm persists after exit).
        """
        cmd = (
            'for p in /proc/[0-9]*; do '
            'if [ "' + ('1' if alive_only else '0') + '" = "1" ]; then '
            's=$(awk \'{print $3}\' $p/stat 2>/dev/null); [ "$s" = "Z" ] && continue; fi; '
            'c=$(cat $p/comm 2>/dev/null); '
            'case "$c" in axck_test|axck_service) echo ${p#/proc/};; esac; done'
        )
        try:
            lines = self.exec_cmd(cmd)
        except Exception:
            return []
        pids = []
        for l in lines:
            s = l.strip()
            if s.isdigit():
                pids.append(int(s))
        return sorted(pids)

    def comm_kill_axck(self, sig=9):
        """Kill all axck_test/axck_service processes found by comm scan.

        Replaces `killall`, which can miss daemonized empty-argv processes.
        """
        cmd = (
            'for p in /proc/[0-9]*; do c=$(cat $p/comm 2>/dev/null); '
            f'case "$c" in axck_test|axck_service) kill -{sig} ${{p#/proc/}} 2>/dev/null;; esac; done'
        )
        try:
            self.exec_cmd(cmd)
            return True
        except Exception:
            return False

    def ipc_file_exists(self):
        """Check whether the nanomsg RPC socket file /tmp/axck.ipc exists."""
        try:
            lines = self.exec_cmd("ls /tmp/axck.ipc 2>/dev/null")
            return any("axck.ipc" in l for l in lines)
        except Exception:
            return False

    def grep_latest_service_log(self, patterns):
        """Grep the newest axck_service log for RPC failure patterns.

        Log filenames are date-prefixed (e.g. 1970-05-13_11-43-12.log), so
        lexical sort finds the newest even with a broken RTC.
        """
        try:
            names = self.exec_cmd("ls /opt/data/AXSyslog/axck_service/ 2>/dev/null")
            logs = [n.strip() for n in names if n.strip().endswith(".log")]
            if not logs:
                return []
            newest = sorted(logs)[-1]
            pat = "|".join(patterns)
            return self.exec_cmd(
                f'grep -nE "{pat}" /opt/data/AXSyslog/axck_service/{newest} 2>/dev/null'
            )
        except Exception:
            return []

    def get_mem_cmm_info(self):
        lines = self.exec_cmd("cat /proc/ax_proc/mem_cmm_info 2>/dev/null")
        return "\n".join(lines[:10])

    def get_memory_snapshot(self):
        """Fetch comprehensive memory metrics across CMM, Linux OS, and daemon process.

        Returns a dictionary:
        {
            "cmm_used_kb": int,
            "cmm_total_kb": int,
            "cmm_usage_pct": float,
            "os_avail_kb": int,
            "os_total_kb": int,
            "vm_rss_kb": int
        }
        """
        snapshot = {
            "cmm_used_kb": 0,
            "cmm_total_kb": 0,
            "cmm_usage_pct": 0.0,
            "os_avail_kb": 0,
            "os_total_kb": 0,
            "vm_rss_kb": 0,
        }
        cmd = (
            'tail -n 3 /proc/ax_proc/mem_cmm_info 2>/dev/null; '
            'grep -E "(MemTotal|MemAvailable)" /proc/meminfo; '
            'grep VmRSS /proc/$(pidof axck_service)/status 2>/dev/null'
        )
        try:
            lines = self.exec_cmd(cmd)
            for line in lines:
                l = line.strip()
                # Parse CMM_USE_INFO: total size=69632KB(68MB),used=46740KB...
                if "total size=" in l and "used=" in l:
                    m_total = re.search(r'total size=(\d+)KB', l)
                    m_used = re.search(r'used=(\d+)KB', l)
                    if m_total:
                        snapshot["cmm_total_kb"] = int(m_total.group(1))
                    if m_used:
                        snapshot["cmm_used_kb"] = int(m_used.group(1))
                    if snapshot["cmm_total_kb"] > 0:
                        snapshot["cmm_usage_pct"] = round(
                            snapshot["cmm_used_kb"] * 100.0 / snapshot["cmm_total_kb"], 1
                        )
                elif l.startswith("MemTotal:"):
                    parts = l.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        snapshot["os_total_kb"] = int(parts[1])
                elif l.startswith("MemAvailable:"):
                    parts = l.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        snapshot["os_avail_kb"] = int(parts[1])
                elif l.startswith("VmRSS:"):
                    parts = l.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        snapshot["vm_rss_kb"] = int(parts[1])
        except Exception:
            pass
        return snapshot

    def get_rgn_osd_info(self):
        """Parse /proc/ax_proc/rgn OSD INFO table."""
        try:
            lines = self.exec_cmd("cat /proc/ax_proc/rgn")
        except Exception:
            return {}

        osds = {}
        in_osd = False
        for l in lines:
            if "OSD INFO" in l:
                in_osd = True
                continue
            if in_osd and ("MOSAIC INFO" in l or "LINE INFO" in l or "RECT INFO" in l or "---" in l):
                if osds:
                    break
            if in_osd:
                parts = l.split()
                if len(parts) >= 6 and parts[0].isdigit():
                    try:
                        rgn_id = int(parts[0])
                        show = parts[1]
                        x0 = int(parts[2])
                        y0 = int(parts[3])
                        w = int(parts[4])
                        h = int(parts[5])
                        osds[rgn_id] = {
                            "show": show,
                            "x0": x0,
                            "y0": y0,
                            "w": w,
                            "h": h
                        }
                    except (ValueError, IndexError):
                        continue
        return osds

    def is_port_listening(self, port):
        """Check if TCP port is actively listening."""
        try:
            lines = self.exec_cmd(f"netstat -tulnp 2>/dev/null | grep ':{port} '")
            return len(lines) > 0
        except Exception:
            return False

    def list_files(self, path):
        """List files in directory stripping ANSI color codes."""
        try:
            lines = self.exec_cmd(f"ls -1 {path} 2>/dev/null")
            cleaned = []
            for l in lines:
                c = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', l).strip()
                if c:
                    cleaned.append(c)
            return cleaned
        except Exception:
            return []

    def get_audio_info(self):
        """Fetch Audio Input/Output hardware state from /proc/ax_proc/ai and ao.

        Returns:
            dict: {
                "ai_volume": float,
                "ai_mute": bool,
                "ao_volume": float
            }
        """
        res = {"ai_volume": 1.0, "ai_mute": False, "ao_volume": 0.0}
        try:
            lines = self.exec_cmd("cat /proc/ax_proc/ai 2>/dev/null | grep -A 2 -E 'VQE VOLCTL ATTR'")
            for l in lines:
                parts = l.strip().split()
                if len(parts) >= 3 and parts[2].replace('.', '', 1).isdigit():
                    vol = float(parts[2])
                    res["ai_volume"] = vol
                    res["ai_mute"] = (vol == 0.0)
                    break
        except Exception:
            pass
        return res

    def get_latest_file(self, dir_path):
        """Get the latest modified filename in a directory."""
        try:
            lines = self.exec_cmd(f"ls -t -1 {dir_path} 2>/dev/null | sed -n 1p")
            for l in lines:
                c = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', l).strip()
                if c and not c.startswith('.'):
                    return c
        except Exception:
            pass
        return None

    def check_file_magic(self, file_path, magic_bytes=b"\xff\xd8"):
        """Verify the first N bytes of a file using dd and base64."""
        n_bytes = len(magic_bytes)
        try:
            lines = self.exec_cmd(f"dd if={file_path} bs={n_bytes} count=1 2>/dev/null | base64")
            for l in lines:
                s = l.strip()
                # Skip echo line from telnet
                if "base64" in s or s.startswith('#'):
                    continue
                if s:
                    import base64
                    try:
                        raw = base64.b64decode(s)
                        if raw.startswith(magic_bytes):
                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        return False

    def get_tfcard_photo_count(self, cam_letter="F"):
        """Count photos in /mnt/tfcard/Photo/<Cam>/."""
        try:
            lines = self.exec_cmd(f"ls -1 /mnt/tfcard/Photo/{cam_letter}/ 2>/dev/null | wc -l")
            for l in lines:
                s = l.strip()
                if s.isdigit():
                    return int(s)
        except Exception:
            pass
        return 0

    def close(self):
        if self.tn:
            try:
                self.tn.close()
            except Exception:
                pass
            self.tn = None
