#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evidence_collector.py - Fast and Robust Evidence Archiving for SDK-AXCK-TEST.
Complies with requirement:
- Test report + full evidence layout archived per task/case under NFS mounted path:
  Default: /tmp/test_archive/sdk-axck-test/<task_id>/
- Clears historical logs on the board before test start (/opt/data/AXSyslog/axck_* & dmesg & syslog).
- For each case: saves raw /proc/ax_proc/ snapshots (ivps, venc, mem_cmm_info) and metrics JSON.
- Finalizes with axck_logs (service & test logs), dmesg.txt, test_report.json, and summary.
"""

import os
import sys
import time
import datetime
import json
import base64


class EvidenceCollector:
    def __init__(self, inspector, nfs_base_path=None, task_name="test_task", nfs_server=None, nfs_remote_dir=None):
        self.inspector = inspector
        nfs_base = nfs_base_path or os.environ.get("AXCK_NFS_MOUNT_POINT", "/tmp/test_archive")
        self.nfs_base_path = f"{nfs_base.rstrip('/')}/sdk-axck-test"
        self.nfs_server = nfs_server or os.environ.get("AXCK_NFS_SERVER")
        self.nfs_remote_dir = nfs_remote_dir or os.environ.get("AXCK_NFS_DIR")
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.task_id = f"{task_name}_{timestamp_str}"
        # Local staging on ramdisk /tmp to guarantee 0ms latency and immune to NFS sync lag
        self.local_stage_dir = f"/tmp/ev_{self.task_id}"
        self.board_task_dir = f"{self.nfs_base_path}/{self.task_id}"

    def ensure_nfs_mounted(self):
        """Ensure NFS is mounted on the board if configured."""
        if not self.inspector:
            return False
        mount_point = self.nfs_base_path.split("/sdk-axck-test")[0]
        try:
            lines = self.inspector.exec_cmd(f"df -h {mount_point} 2>/dev/null")
            mounted = any(mount_point in l for l in lines)
            if not mounted and self.nfs_server and self.nfs_remote_dir:
                self.inspector.exec_cmd("nfs_load.sh >/dev/null 2>&1")
                self.inspector.exec_cmd(f"mkdir -p {mount_point} && mount -t nfs -o nolock,soft,timeo=30,tcp {self.nfs_server}:{self.nfs_remote_dir} {mount_point}")
                time.sleep(0.5)
                lines = self.inspector.exec_cmd(f"df -h {mount_point} 2>/dev/null")
                mounted = any(mount_point in l for l in lines)
            return mounted
        except Exception as e:
            print(f"[EvidenceCollector] Warning: check/mount NFS failed: {e}")
            return False

    def prepare_task_environment(self):
        """
        Step 1: Ensure NFS is ready and create staging folder.
        Step 2: Clear historical logs on board before test execution.
        """
        if not self.inspector:
            return False

        # 1. Mount NFS and prepare local staging
        self.ensure_nfs_mounted()
        self.inspector.exec_cmd(f"mkdir -p {self.local_stage_dir}/cases")

        # 2. Clean historical logs
        print("[EvidenceCollector] Clearing historical board logs (/opt/data/AXSyslog/* & dmesg) before test...")
        self.inspector.exec_cmd("rm -rf /opt/data/AXSyslog/axck_test/* /opt/data/AXSyslog/axck_service/*")
        self.inspector.exec_cmd("dmesg -c >/dev/null 2>&1 || true")
        self.inspector.exec_cmd("rm -rf /tmp/data/AXSyslog/syslog/* /var/log/syslog.log 2>/dev/null || true")
        return True

    def _write_remote_file(self, remote_path, content_str):
        """
        Write text file on board safely via temporary local file and base64.
        """
        b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")
        tmp_b64 = f"/tmp/_tmp_{int(time.time()*1000)}.b64"
        self.inspector.exec_cmd(f"rm -f {tmp_b64}")
        chunk_size = 512
        for i in range(0, len(b64), chunk_size):
            chunk = b64[i:i + chunk_size]
            self.inspector.exec_cmd(f"echo -n '{chunk}' >> {tmp_b64}")
        self.inspector.exec_cmd(f"base64 -d {tmp_b64} > {remote_path} && rm -f {tmp_b64}")

    def record_case_evidence(self, suite_name, case_name, case_tag, inputs, outputs, gates, raw_proc_needed=True):
        """
        Capture per-case evidence into local ramdisk staging folder (instantaneous).
        """
        if not self.inspector:
            return

        clean_tag = case_tag.replace(" ", "_").replace("/", "_").replace(".", "_")
        case_dir = f"{self.local_stage_dir}/cases/{clean_tag}"
        self.inspector.exec_cmd(f"mkdir -p {case_dir}")

        meta = {
            "suite": suite_name,
            "case_name": case_name,
            "case_tag": case_tag,
            "timestamp": time.time(),
            "inputs": inputs,
            "outputs": outputs,
            "gates": gates
        }
        meta_json = json.dumps(meta, indent=2, ensure_ascii=False)

        try:
            if raw_proc_needed:
                self.inspector.exec_cmd(f"cat /proc/ax_proc/ivps > {case_dir}/raw_ivps.txt 2>/dev/null || true")
                self.inspector.exec_cmd(f"cat /proc/ax_proc/venc > {case_dir}/raw_venc.txt 2>/dev/null || true")
                self.inspector.exec_cmd(f"cat /proc/ax_proc/mem_cmm_info > {case_dir}/raw_mem_cmm.txt 2>/dev/null || true")

            self._write_remote_file(f"{case_dir}/metrics.json", meta_json)
        except Exception as e:
            print(f"[EvidenceCollector] Error recording evidence for {case_name}: {e}")

    def finalize_task(self, report_payload, local_report_path=None):
        """
        Collect final logs, save full report, sync staging folder to NFS, and clean up staging.
        """
        if not self.inspector:
            return {}

        print(f"\n[EvidenceCollector] Finalizing task evidence at {self.board_task_dir}...")
        try:
            # 1. Archive board axck application logs into staging
            self.inspector.exec_cmd(f"mkdir -p {self.local_stage_dir}/axck_logs")
            self.inspector.exec_cmd(f"cp -rf /opt/data/AXSyslog/axck_service/* {self.local_stage_dir}/axck_logs/ 2>/dev/null || true")
            self.inspector.exec_cmd(f"cp -rf /opt/data/AXSyslog/axck_test/* {self.local_stage_dir}/axck_logs/ 2>/dev/null || true")

            # 2. Archive system dmesg into staging
            self.inspector.exec_cmd(f"dmesg > {self.local_stage_dir}/dmesg.txt 2>/dev/null || true")

            # 3. Save local report copy if requested FIRST
            if local_report_path:
                os.makedirs(os.path.dirname(os.path.abspath(local_report_path)), exist_ok=True)
                with open(local_report_path, "w", encoding="utf-8") as f:
                    json.dump(report_payload, f, indent=2, ensure_ascii=False)

            # 4. Copy whole staging directory to NFS archive
            self.inspector.exec_cmd(f"mkdir -p {self.board_task_dir}")
            self.inspector.exec_cmd(f"cp -rf {self.local_stage_dir}/* {self.board_task_dir}/ 2>/dev/null || true")
            # Remove staging directory
            self.inspector.exec_cmd(f"rm -rf {self.local_stage_dir}")

            # 5. Direct copy of recorded videos and captured photos to NFS archive (bypass ramdisk to prevent tmpfs overflow)
            print(f"[EvidenceCollector] Archiving recorded videos and captured photos to NFS media directory...")
            self.inspector.exec_cmd(f"mkdir -p {self.board_task_dir}/media", timeout=10.0)
            self.inspector.exec_cmd(f"cp -rf /mnt/tfcard/Normal/F/*.mp4 {self.board_task_dir}/media/ 2>/dev/null || true", timeout=60.0)
            self.inspector.exec_cmd(f"cp -rf /mnt/tfcard/Photo/F/*.jpg {self.board_task_dir}/media/ 2>/dev/null || true", timeout=60.0)
            self.inspector.exec_cmd(f"sync", timeout=30.0)

            return {
                "task_id": self.task_id,
                "evidence_dir_on_board": self.board_task_dir,
                "evidence_dir_on_nas": f"{self.nfs_remote_dir.rstrip('/')}/sdk-axck-test/{self.task_id}" if self.nfs_remote_dir else self.board_task_dir,
                "timestamp": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            print(f"[EvidenceCollector] Error finalizing task evidence: {e}")
            return {"task_id": self.task_id, "error": str(e)}
