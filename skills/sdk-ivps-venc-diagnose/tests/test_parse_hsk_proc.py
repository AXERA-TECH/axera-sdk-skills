import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from parse_hsk_proc import hsk_widths, parse, progress_verdict, tokenize

# 板端真实采样：link_table / syncagent / ivps / venc / jenc 各一次 cat，
# SDK 版本 V3.13.0，含 `/root #` 提示符、`[...]` 列表字段和 `%d :%d` 粘连字段。
FIXTURE = ROOT / "tests" / "fixtures" / "hsk_proc_single_sample.txt"
SAMPLE = FIXTURE.read_text(encoding="utf-8")


def with_prompts_removed(text):
    return "\n".join(line for line in text.splitlines()
                     if "/proc/ax_proc" not in line) + "\n"


def second_sample(text):
    """按行号推进 venc chn0 与 ivps chn0/flt1 的计数，合成第二轮采样。

    只用于验证 S1 -> S2 差分分支；除这三行外的通道计数器保持不变，因此会被判为停滞。
    行号断言保证 fixture 变动时测试直接失败，而不是静默失效。
    """
    lines = text.splitlines()

    def bump(index, old, new, count=1):
        assert lines[index].count(old) == count, lines[index]
        lines[index] = lines[index].replace(old, new)

    def bump_first(index, old, new, count):
        """该行有两个同名计数（HoldCnt/ReleaseCnt）时只推进前一个。"""
        assert lines[index].count(old) == count, lines[index]
        lines[index] = lines[index].replace(old, new, 1)

    bump(164, "2004069", "2004169", 2)   # VENC CHN STATUS 2 chn0: FrmRecv / SubMitCnt
    bump(147, "2004069", "2004169", 1)   # VENC CHN HSK STATUS chn0: hskCnt
    bump(91, "2003984", "2004084", 3)    # IVPS FILTER STATE chn0/flt1: TotalCnt/InCnt/OutCnt
    bump_first(54, "53052648", "53052649", 2)   # syncagent sess2 INFO: 只涨 HoldCnt[0]
    return "\n".join(lines) + "\n"


def two_samples():
    return ("===== SAMPLE 1 2026-09-11 10:00:00 =====\n" + SAMPLE +
            "===== SAMPLE 2 2026-09-11 10:00:05 =====\n" + second_sample(SAMPLE))


def channel_of(sample, module, identifier):
    return next(item for item in sample[module]["channels"] if item["id"] == identifier)


def hsk_of(sample, module, identifier):
    return next(item for item in sample["hsk_channels"]
                if item["module"] == module and item["chn"] == identifier)


class RealSampleTest(unittest.TestCase):
    def setUp(self):
        self.result = parse(SAMPLE)
        self.sample = self.result["samples"][0]

    def test_reads_all_modules_and_sdk_version(self):
        self.assertEqual(self.result["environment"]["sdk_version"],
                         "ax_sys V3.13.0_20260910110137 Sep 10 2026 12:18:38 JK")
        self.assertEqual(sorted(self.result["environment"]["module_versions"]),
                         ["ax_ivps", "ax_sys", "ax_venc"])
        self.assertEqual(self.sample["modules_found"],
                         ["ivps", "jenc", "link_table", "syncagent", "venc"])
        self.assertEqual(self.result["environment"]["sample_count"], 1)
        self.assertFalse(self.result["environment"]["sample_marker_present"])

    def test_healthy_sample_reports_no_issues(self):
        # 现场是正常运行的链路：字段若错位或误判越界，这里会立刻暴露。
        # 允许的「提示」只有两条：这份采样没带 link_table_kernel（采集命令后来才补上该项）、
        # 以及 link_table 里确实存在 4 条 SW_Offline 链路（不是 HSK 绑定，如实列出）。
        self.assertEqual([issue["field"] for issue in self.result["issues"]],
                         ["模块 link_table_kernel", "link_table 非 HSK 链路"])

    def test_parses_without_prompt_lines(self):
        result = parse(with_prompts_removed(SAMPLE))
        self.assertEqual(result["samples"][0]["modules_found"],
                         ["ivps", "jenc", "link_table", "syncagent", "venc"])
        self.assertEqual([issue["field"] for issue in result["issues"]],
                         ["模块 link_table_kernel", "link_table 非 HSK 链路"])

    def test_link_table_keeps_only_hsk_links(self):
        links = self.sample["topology"]["hsk_links"]
        self.assertEqual([(link["src"]["module"], link["dst"]["chn"]) for link in links],
                         [("IVPS", 0), ("IVPS", 1)])
        self.assertEqual({link["mode"] for link in links}, {"SW_Low_Mem"})
        self.assertEqual({link["line"] for link in links}, {128})
        # SW_Offline 的 IVPS 0/2 -> VENC 0/2 不计入 HSK 形态。
        self.assertEqual(len(self.sample["link_table"]["links"]), 6)

    def test_identifies_topology_forms(self):
        forms = self.sample["topology"]["forms"]
        # link_table 把 JENC 分支也打印成 VENC，目的通道在 venc proc 里不存在时按 jenc 侧归一；
        # IVPS 0/1 因此落到 jenc chn1（srcNum=2 的二对一），不另算一对一。
        self.assertEqual([form["form"] for form in forms], ["一对一", "二对一"])
        self.assertIn("VENC 0/0", forms[0]["evidence"])
        self.assertIn("jenc chn1", forms[-1]["evidence"])
        # 二对一的依据要落到 link_table 的绑定关系上，不能只写 srcNum=2。
        self.assertIn("link_table 绑定", forms[-1]["evidence"])
        self.assertIn("IVPS 0/1 -> VENC 0/1", forms[-1]["evidence"])
        self.assertIn("实为 JENC chn1", forms[-1]["evidence"])

    def test_unified_venc_naming_does_not_raise_issue(self):
        # link_table 对用户侧统一用 VENC 打印 H.26x 与 JENC，这是命名约定而不是异常：
        # 只要目的通道能在某一侧编码 proc 里找到，就不产生提示。
        self.assertEqual([issue for issue in self.result["issues"]
                          if issue["field"] == "link_table 目的通道"], [])

    def test_unresolvable_consumer_channel_is_only_a_hint(self):
        # 两侧编码 proc 都没有该通道时才提示：ModId 和通道号都对不上，消费端无法确认。
        text = SAMPLE.replace("(IVPS       0       1) -> (VENC     0       1)",
                              "(IVPS       0       1) -> (VENC     0       5)")
        sample = parse(text)["samples"][0]
        issues = [issue for issue in sample["issues"]
                  if issue["field"] == "link_table 目的通道"]
        self.assertEqual(len(issues), 1)
        self.assertIn("IVPS 0/1 -> VENC 0/5", issues[0]["message"])
        # 该链路不进形态；二对一由编码侧 srcNum=2 给出，只是绑定关系无从引用。
        forms = sample["topology"]["forms"]
        self.assertEqual([form["form"] for form in forms], ["一对一", "二对一"])
        self.assertIn("绑定待确认", forms[-1]["evidence"])
        self.assertIn("link_table_kernel", issues[0]["message"])
        # IVPS 0/0 的 VENC chn0 真实存在，仍按一对一计入。
        self.assertEqual(len(self.sample["topology"]["forms"]), 2)

    def test_syncagent_session_and_bracket_columns(self):
        sessions = self.sample["syncagent"]["sessions"]
        self.assertEqual([session["sess_id"] for session in sessions], [0, 1, 2])
        self.assertEqual([session["state"] for session in sessions], [2, 2, 2])
        self.assertEqual([session["con_wait"] for session in sessions], [0, 1, 0])
        self.assertEqual(sessions[0]["init_val"], 17920)
        # SESSION 只留 SessId/State/ConWait/InitVal；HoldCnt/ReleaseCnt 每列各是一个 `[...]` 列表。
        self.assertEqual(sorted(sessions[0]), ["con_wait", "connects", "info", "init_val",
                                               "sess_id", "state"])
        self.assertEqual(sessions[2]["info"]["HoldCnt"], [53052648, 53052646])
        self.assertEqual(sessions[2]["info"]["ReleaseCnt"], [53052648, 53052646])

    def test_syncagent_connect_expands_numbered_bracket_group(self):
        connects = self.sample["syncagent"]["sessions"][0]["connects"]
        self.assertEqual(len(connects), 4)
        update = connects[0]
        self.assertEqual((update["ConId"], update["State"], update["Type"]), (0, 2, "update"))
        self.assertEqual((update["Cons"], update["ChnId"]), ("MM_VENC", 70))
        self.assertEqual(update["RegVal"], 19456)
        # OppWaitChn 是列表列；RegVal0..2 是三个独立列，都来自同一个 `[...]` 块。
        self.assertEqual(update["OppWaitChn"], [26, 255])
        self.assertEqual([update["RegVal0"], update["RegVal1"], update["RegVal2"]],
                         [17920, 16384, 14848])
        self.assertEqual([update["InitVal0"], update["InitVal1"], update["InitVal2"]],
                         [17920, 16384, 14848])
        self.assertEqual(update["SyncAddr"], "0x43c45800")
        # CONNECT 的 RegAddr/SliceNum 用不到（sliceNum 取编码器 HSK STATUS 那份）。
        self.assertNotIn("RegAddr", update)
        self.assertNotIn("SliceNum", update)

    def test_venc_hsk_status_merges_two_tables(self):
        channel = channel_of(self.sample, "venc", 0)
        hsk = channel["hsk"]
        self.assertEqual((hsk["bHsk"], hsk["EncH"], hsk["srcNum"], hsk["minhskLin"]),
                         ("Y", 1520, 1, 16))
        self.assertEqual((hsk["conId"], hsk["waitId"], hsk["upId"]), (8, 34, 70))
        self.assertEqual((hsk["initVal"], hsk["syncVal"]), (22528, 24064))
        self.assertEqual((hsk["hskCnt"], hsk["errDropCnt"]), (2004069, 0))
        # 第二张表的 `%d :%d` 字段和物理地址。
        self.assertEqual(channel["hsk_wait"]["douWa"], 0)
        self.assertEqual(channel["hsk_info"]["waReInfo0"], {"idx": 1, "val": 24064})
        self.assertEqual(channel["hsk_info"]["upReInfo"], {"idx": 0, "val": 24064})
        self.assertEqual(channel["hsk_info"]["waWaPhy0"], "0x43c45000")
        self.assertEqual(channel["hsk_info"]["waUpPhy0"], "0x43c45800")

    def test_hsk_status_keeps_only_referenced_fields(self):
        channel = channel_of(self.sample, "venc", 0)
        # 第 2 节/第 3 节/第 5 节只用到握手寄存器、参与同步的源数量和丢帧线索。
        self.assertEqual(sorted(channel["hsk"]),
                         ["EncH", "bFrmDrop", "bHsk", "conId", "errDropCnt", "hskCnt",
                          "initVal", "minhskLin", "sliceNum", "srcNum", "syncVal", "upId",
                          "waitId"])
        # 第二张表只留等待分支关系；地址与 `索引:值` 字段在 hsk_info 里。
        self.assertEqual(sorted(channel["hsk_wait"]),
                         ["cntWa", "douWa", "opUpChn0", "opUpChn1", "opWaChn0", "opWaChn1"])

    def test_only_hsk_related_encoder_tables_are_kept(self):
        channel = channel_of(self.sample, "venc", 0)
        # `CHN ATTR 2` 只留编码宽高、序号和 PTS；`EncH` 供第 3 节的 ceil(EncH/64)*64 核对。
        self.assertEqual(channel["frame"], {"ID": 0, "EncW": 2688, "EncH": 1520,
                                            "SeqNum": 2004084, "PTS": 97601928104})
        # GOP / CHN ATTR 1（Profile/Stride/Crop/PixFmt）等不参与诊断，不解析。
        for key in ("attr", "attr2", "rc2", "rc3", "gop", "status1"):
            self.assertNotIn(key, channel)
        self.assertNotIn("CropEn", channel["frame"])

    def test_parses_rc_framerate_for_both_encoders(self):
        # 第 5 节：码控帧率是区分「配置低帧率」与「真停滞」的唯一依据，务必解析。
        venc = channel_of(self.sample, "venc", 0)["rc"]
        self.assertEqual(venc, {"ID": 0, "RcMode": "CBR", "SrcFr": 30, "DstFr": 30,
                                "TargetBitRate": 4096})
        # JENC 的表没有 `TargetBitRate`，标题也不带 `1`，两者不能共用白名单。
        jenc = channel_of(self.sample, "jenc", 1)["rc"]
        self.assertEqual(jenc, {"ID": 1, "RcMode": "-", "SrcFr": 1, "DstFr": 1})

    def test_venc_stream_buf_status_keeps_only_progress_fields(self):
        row = channel_of(self.sample, "venc", 0)["stream_buf"]
        self.assertEqual(row["ReadCycle"], 2004069)
        self.assertEqual(row["AvalRSize"], 0)
        self.assertEqual(row["HwUsed"], "N")
        for name in ("PhyAddr", "VirtAddr", "BuffSize", "RollbackWr", "RollbackCycle",
                     "ReadPtr", "WritePtr", "AvalWSize"):
            self.assertNotIn(name, row)

    def test_jenc_stream_buf_has_no_hw_used_column(self):
        # JENC 侧对应列是 `BufBusy`，两个模块不能共用同一份白名单。
        row = channel_of(self.sample, "jenc", 1)["stream_buf"]
        self.assertEqual(row["ReadCycle"], 66806)
        self.assertEqual(sorted(row), ["AvalRSize", "ReadCycle", "VeChn", "WriteCycle"])

    def test_jenc_frame_list_is_module_level(self):
        # FRAME LIST STATUS 没有通道号列，不能把它误当成 jenc chn0；第 3.2 节用 busyCnt/freeCnt/HwState。
        self.assertEqual(self.sample["jenc"]["frame_list"],
                         {"busyCnt": 0, "freeCnt": 10, "HwState": "IDLE"})
        self.assertEqual([channel["id"] for channel in self.sample["jenc"]["channels"]], [1, 15])
        self.assertEqual(self.sample["venc"]["frame_list"], {})

    def test_derives_handshake_height_and_cross_checks(self):
        for module, identifier in (("venc", 0), ("jenc", 1)):
            derived = hsk_of(self.sample, module, identifier)["derived"]
            self.assertEqual(derived["handshake_height"], 1536)
            self.assertEqual(derived["expected_height_from_enc_h"], 1536)
            self.assertTrue(derived["height_matches_enc_h"])
            self.assertEqual(derived["slice_num_x_minhsk_lin"], 1520)
            self.assertTrue(derived["slice_check_matches_enc_h"])

    def test_non_hsk_channel_is_not_derived(self):
        entry = hsk_of(self.sample, "jenc", 15)
        self.assertEqual(entry["derived"], {"hsk_enabled": False})
        self.assertIsNone(entry["session"])

    def test_maps_encoder_channel_to_syncagent_connection(self):
        mapping = hsk_of(self.sample, "venc", 0)["session"]
        self.assertEqual(mapping["sess_ids"], [0])
        self.assertEqual([item["con_id"] for item in mapping["up_connects"]], [0])
        self.assertEqual([item["con_id"] for item in mapping["wait_connects"]], [1])
        self.assertEqual(mapping["wait_branch_count"], 1)
        # waWaPhy0/waUpPhy0 与 syncagent SyncAddr 必须互相对得上。
        self.assertTrue(mapping["sync_addr_match"])

    def test_multi_wait_branch_marks_two_to_one(self):
        mapping = hsk_of(self.sample, "jenc", 1)["session"]
        self.assertEqual(mapping["sess_ids"], [1])
        self.assertEqual(mapping["wait_branch_count"], 2)
        self.assertEqual([item["cons"] for item in mapping["wait_connects"]], ["MM_JENC", "MM_JENC"])
        self.assertEqual([item["double_wait"] for item in mapping["wait_connects"]], [1, 0])
        self.assertEqual(mapping["form_hint"], "二对一")
        self.assertTrue(mapping["sync_addr_match"])

    def test_session_progress_uses_16bit_ring_arithmetic(self):
        checks = self.sample["session_checks"]
        self.assertEqual(checks[0]["derived"]["height_from_encoder"], 1536)
        self.assertEqual([item["progress"] for item in checks[0]["connects"]], [1536] * 4)
        self.assertTrue(all("syncVal" in item["verdict"] for item in checks[0]["connects"]))
        # InitVal=0 的 ISP session 是自由计数，不套用 initVal -> syncVal 公式。
        self.assertEqual(checks[2]["connects"], [])
        self.assertIn("InitVal=0", checks[2]["derived"]["note"])

    def test_ivps_keeps_only_progress_columns(self):
        self.assertEqual(sorted(self.sample["ivps"]), ["chn_info", "filter_state"])
        rows = self.sample["ivps"]["filter_state"]
        self.assertEqual(len(rows), 8)
        first = rows[0]
        self.assertEqual((first["GrpId"], first["ChnId"], first["FltId"], first["Engine"]),
                         (0, -1, 0, "GDC"))
        self.assertEqual((first["TotalCnt"], first["InCnt"], first["OutCnt"]),
                         (2003985, 2003985, 2003985))
        # 表头的 `Src : Dst` 与 `TimeCur/TimeAve` 属于抽帧与耗时统计，不保留；
        # `En` 也没在 SKILL.md 里用上。
        self.assertEqual(sorted(first), ["ChnId", "Engine", "Fail1", "Fail2", "FltId",
                                        "GrpId", "InCnt", "OutCnt", "TotalCnt"])
        by_filter = {row["FltId"]: row for row in rows}
        self.assertEqual(by_filter[3]["OutCnt"], 66800)
        self.assertEqual(by_filter[6]["OutCnt"], 667995)

    def test_ivps_chn_info_keeps_output_backlog(self):
        # 第 5 节用 `OutSts`/`OutDepth` 判断输出积压，它们在 IVPS CHN INFO 而不是 FILTER STATE。
        rows = self.sample["ivps"]["chn_info"]
        self.assertEqual([row["ChnId"] for row in rows], [0, 1, 2, 3, 4])
        self.assertEqual((rows[3]["OutDepth"], rows[3]["OutSts"]), (1, 0))
        self.assertEqual(rows[0]["OutFps"], 29.99)
        # `FrcMode`/`Frc(src:dst)` 是 IVPS 抽帧配置：低 OutFps 是不是故障要靠它区分。
        self.assertEqual(sorted(rows[0]),
                         ["ChnId", "Frc(src:dst)", "FrcMode", "GrpId",
                          "OutDepth", "OutFps", "OutSts"])
        self.assertEqual((rows[1]["FrcMode"], rows[1]["Frc(src:dst)"]), ("RATIO", "30.0:1.0"))

    def test_collects_counters_for_stall_comparison(self):
        counters = self.sample["counters"]
        self.assertEqual(counters["venc/chn0/hskCnt"], 2004069)
        self.assertEqual(counters["venc/chn0/Send2EncCnt"], 2004069)
        self.assertEqual(counters["venc/chn0/EncSucCnt"], 2004068)
        self.assertEqual(counters["venc/chn0/ErrorCnt"], 0)
        self.assertEqual(counters["venc/chn0/ReadCycle"], 2004069)
        self.assertEqual(counters["jenc/chn1/SubmitCnt"], 66807)
        self.assertEqual(counters["jenc/chn1/FrmRecv"], 66807)
        self.assertEqual(counters["ivps/grp0/chn3/flt6/OutCnt"], 667995)
        self.assertEqual(counters["syncagent/sess2/HoldCnt[0]"], 53052648)
        # 被裁剪的字段和通道号列不进入计数器。
        self.assertNotIn("venc/chn0/DropBsCnt", counters)
        self.assertNotIn("venc/chn0/ChnId", counters)
        self.assertNotIn("jenc/chn1/busyCnt", counters)


class TwoSampleTest(unittest.TestCase):
    def setUp(self):
        self.result = parse(two_samples())
        self.deltas = self.result["deltas"][0]
        self.groups = {entry["group"]: entry for entry in self.deltas["groups"]}

    def test_splits_marked_samples(self):
        self.assertEqual(self.result["environment"]["sample_count"], 2)
        self.assertEqual(self.result["environment"]["sample_labels"], ["SAMPLE 1", "SAMPLE 2"])
        self.assertTrue(self.result["environment"]["sample_marker_present"])

    def test_reports_counter_deltas(self):
        by_key = {item["key"]: item for item in self.deltas["deltas"]}
        self.assertEqual(by_key["venc/chn0/FrmRecv"], {"key": "venc/chn0/FrmRecv",
                                                       "s1": 2004069, "s2": 2004169, "delta": 100})
        self.assertEqual(by_key["venc/chn0/hskCnt"]["delta"], 100)
        self.assertEqual(by_key["ivps/grp0/chn0/flt1/OutCnt"]["delta"], 100)

    def test_static_hints_are_reported_once_across_samples(self):
        # 缺 link_table_kernel、非 HSK 链路清单这类静态提示是每轮都会得出的，不能随轮次重复。
        fields = [issue["field"] for issue in self.result["issues"]]
        self.assertEqual(fields.count("模块 link_table_kernel"), 1)
        self.assertEqual(fields.count("link_table 非 HSK 链路"), 1)

    def test_stalled_only_when_every_progress_counter_is_flat(self):
        # venc/chn0 只推进了部分计数器，仍说明该通道在工作，不能判停滞。
        self.assertIn("venc/chn0", self.groups)
        self.assertEqual(sorted(self.groups["venc/chn0"]["changed"]), ["FrmRecv", "hskCnt"])
        self.assertNotIn("venc/chn0", self.deltas["stalled_groups"])
        self.assertNotIn("ivps/grp0/chn0/flt1", self.deltas["stalled_groups"])
        self.assertIn("jenc/chn1", self.deltas["stalled_groups"])
        self.assertIn("ivps/grp0/chn2/flt5", self.deltas["stalled_groups"])

    def test_flags_stalled_channel(self):
        messages = [issue["message"] for issue in self.result["issues"]
                    if issue["channel"] == "jenc/chn1" and issue["field"] == "S1 -> S2 计数"]
        self.assertEqual(len(messages), 1)
        self.assertIn("SubmitCnt", messages[0])

    def test_hold_release_growth_is_flagged(self):
        issues = parse(two_samples())["issues"]
        self.assertTrue(any(issue["field"] == "syncagent HoldCnt/ReleaseCnt"
                            and issue["level"] == "高风险" for issue in issues))


class GuardTest(unittest.TestCase):
    def test_flags_session_state_not_ready(self):
        text = SAMPLE.replace("0      0      2     0       17920", "0      0      1     0       17920")
        issues = parse(text)["issues"]
        self.assertTrue(any(issue["level"] == "高风险" and "State=1" in issue["message"]
                            for issue in issues))

    def test_flags_progress_beyond_handshake_height(self):
        # session 内各 ConId 读数一致时 InitVal 代表整组，进度越界才报同步异常。
        issues = parse(SAMPLE.replace("19456", "30000"))["issues"]
        self.assertTrue(any("大于握手高度" in issue["message"] for issue in issues))

    def test_skips_progress_when_connects_read_different_registers(self):
        # 一链多 ConId 落在不同寄存器、读数各不相同时，session InitVal 只对应其中一个寄存器，
        # 减出来的不是进度，不能报「大于握手高度」。
        text = SAMPLE.replace("[34   255] 1       19456", "[34   255] 1       30000")
        result = parse(text)
        self.assertFalse(any("大于握手高度" in issue["message"] for issue in result["issues"]))
        session = result["samples"][0]["session_checks"][0]
        self.assertIn("不套用进度公式", session["derived"]["note"])
        self.assertNotIn("progress", session["connects"][0])

    def test_flags_missing_modules_and_missing_version(self):
        only_venc = SAMPLE[SAMPLE.index("-------- VENC CHN ATTR 1"):SAMPLE.index("-------- JENC CHN ATTR 1")]
        result = parse(only_venc)
        missing = [issue["field"] for issue in result["issues"] if issue["field"].startswith("模块")]
        self.assertEqual(sorted(missing),
                         ["模块 ivps", "模块 jenc", "模块 link_table", "模块 syncagent"])
        self.assertEqual(result["samples"][0]["modules_found"], ["venc"])

        stripped = "\n".join(line for line in SAMPLE.splitlines()
                             if not line.startswith("[SDK version]"))
        result = parse(stripped)
        self.assertEqual(result["environment"]["sdk_version"], "unknown")
        self.assertIsNone(result["environment"]["sdk_version_source"])
        self.assertEqual(result["issues"][0]["field"], "SDK version")

    def test_flags_mismatched_handshake_height(self):
        # syncVal 24064 -> 24000：握手高度 1472 与 ceil(1520/64)*64=1536 不一致。
        text = SAMPLE.replace("22528   24064", "22528   24000")
        issues = parse(text)["issues"]
        self.assertTrue(any(issue["field"] == "venc HSK 高度" and "不一致" in issue["message"]
                            for issue in issues))

    def test_flags_unmappable_wait_and_up_id(self):
        text = SAMPLE.replace("  34     70   22528   24064", "  199    201   22528   24064")
        issues = parse(text)["issues"]
        self.assertTrue(any("找不到对应连接" in issue["message"] for issue in issues))


class LinkKernelTest(unittest.TestCase):
    """`link_table_kernel` 的 Engine 列。

    行格式照抄 SDK 的打印语句（kernel/osdrv/private_drv/sys/syslink/src/
    ax_sys_link_proc_show.c 的 `ax_link_table_kernel_proc_read`），Engine 的枚举值取自
    header/external/ax_sys_api.h 的 AX_ENGINE_LOWLATENCY_E。链路本身是构造的，
    用来覆盖合并、ModId/Engine 冲突和缺失 kernel 表三种情况，不是板端采样。
    """

    USER_TABLE = """--------------------Link Table V2----------------------------------------------------
         Src            |          Dst               |                               |
(ModId   GrpId   ChnId) | (ModId   GrpId   ChnId)    |     Mode    |        line     |
-------------------------------------------------------------------------------------
(IVPS       0       0) -> (VENC     0       0)   Mode :   SW_Low_Mem    Line :   128
(IVPS       0       1) -> (VENC     0       1)   Mode :   SW_Low_Mem    Line :   128
(IVPS       0       1) -> (JENC     0       1)   Mode :   SW_Low_Mem    Line :   128
(IVPS       0       2) -> (VENC     0       2)   Mode :   SW_Offline    Line :     0
(IVPS       0       3) -> (VENC     0       3)   Mode :   SW_Low_Mem    Line :   128
(IVPS       0       4) -> (VENC     0       4)   Mode :   SW_Low_Mem    Line :   128
"""

    KERNEL_TABLE = """--------------------Link Table Kernel V2-------------------------------------------------------------------------
         Src            |          Dst               |                   Link Attribute                          |
(ModId   GrpId   ChnId) | (ModId   GrpId   ChnId)    |     Mode    |        line     |      Engine(src->dst)     |
-----------------------------------------------------------------------------------------------------------------
(IVPS       0       0) -> (VENC     0       0)   Mode :   SW_Low_Mem    Line :   128   Engine (1:VPP --> 4:VENC)
(IVPS       0       1) -> (VENC     0       1)   Mode :   SW_Low_Mem    Line :   128   Engine (1:VPP --> 4:VENC)
(IVPS       0       1) -> (JENC     0       1)   Mode :   SW_Low_Mem    Line :   128   Engine (1:VPP --> 3:JENC)
(IVPS       0       2) -> (VENC     0       2)   Mode :   SW_Offline    Line :     0   Engine (2:VPPVGP --> 4:VENC)
(IVPS       0       3) -> (VENC     0       3)   Mode :   SW_Low_Mem    Line :   128   Engine (1:VPP --> 7:DPU)
(IVPS       0       4) -> (VENC     0       4)   Mode :   SW_Low_Mem    Line :   128   Engine (1:VPP --> 3:JENC)
"""

    def links(self, *texts):
        sample = parse("".join(texts))["samples"][0]
        return sample["link_table"]["links"], sample["topology"]

    def test_merges_kernel_engine_into_user_links(self):
        links, _ = self.links(self.USER_TABLE, self.KERNEL_TABLE)
        # 两张表是同一批链路，合并后条数不变。
        self.assertEqual(len(links), 6)
        self.assertEqual(links[0]["engine"],
                         {"src_id": 1, "src": "VPP", "dst_id": 4, "dst": "VENC"})
        self.assertEqual(links[2]["engine"]["dst"], "JENC")

    def test_engine_decides_consumer_over_modid(self):
        # 最后一条 ModId 写的是 VENC，Engine 说 --JENC，按第 2 节必须算 JENC 分支。
        links, topology = self.links(self.USER_TABLE, self.KERNEL_TABLE)
        jpeg_branch = [link for link in links if link["dst"]["chn"] == 4][0]
        self.assertEqual(jpeg_branch["dst"]["module"], "VENC")
        self.assertEqual(topology["hsk_links"][-1]["consumer"], "JENC")
        self.assertEqual(topology["hsk_links"][-1]["engine"]["dst"], "JENC")

    def test_engine_filter_drops_non_encoder_consumer(self):
        # IVPS 0/3 的 Engine 是 DPU，不是编码分支，不计入 HSK 形态。
        _, topology = self.links(self.USER_TABLE, self.KERNEL_TABLE)
        consumers = {(link["src"]["chn"], link["consumer"])
                     for link in topology["hsk_links"]}
        self.assertNotIn((3, "DPU"), consumers)
        self.assertEqual(consumers, {(0, "VENC"), (1, "VENC"), (1, "JENC"), (4, "JENC")})

    def test_shared_source_with_kernel_engine_is_one_to_two(self):
        _, topology = self.links(self.USER_TABLE, self.KERNEL_TABLE)
        # 源 IVPS 0/0、0/4 各一个消费端，0/1 同时挂了 VENC 和 JENC。
        forms = [form["form"] for form in topology["forms"]]
        self.assertEqual(forms, ["一对一", "一对二", "一对一"])
        self.assertIn("VENC 0/1", topology["forms"][1]["evidence"])
        self.assertIn("JENC 0/1", topology["forms"][1]["evidence"])

    def test_kernel_table_alone_is_enough(self):
        # 只采到 kernel 表时仍能建出链路，且不产生「Engine 未知」的提示。
        result = parse(self.KERNEL_TABLE)
        self.assertEqual(len(result["samples"][0]["link_table"]["links"]), 6)
        self.assertEqual([issue["field"] for issue in result["issues"]
                          if issue["field"] == "模块 link_table_kernel"], [])

    def test_missing_kernel_table_is_reported(self):
        result = parse(self.USER_TABLE)
        self.assertTrue(any(issue["field"] == "模块 link_table_kernel"
                            and issue["level"] == "提示" for issue in result["issues"]))
        self.assertTrue(all("engine" not in link
                            for link in result["samples"][0]["link_table"]["links"]))


class NonHskBindingTest(unittest.TestCase):
    """非 HSK 绑定链路的处理。

    HSK 只在 `SW_Low_Mem`/`SW_Low_Latency` 下启用（venc.c 的
    `VENC_CHECK_HSK_MODE`），`SW_Offline`/`HW_Online`/`Mode_Unset` 的链路没有握手
    寄存器可分析：脚本要把它们排除出形态统计，同时显式列出，不能静默丢弃。
    行格式同 `LinkKernelTest`，链路是构造的，不是板端采样。
    """

    MIXED_TABLE = """--------------------Link Table V2----------------------------------------------------
         Src            |          Dst               |                               |
(ModId   GrpId   ChnId) | (ModId   GrpId   ChnId)    |     Mode    |        line     |
-------------------------------------------------------------------------------------
(IVPS       0       0) -> (VENC     0       0)   Mode :   SW_Low_Mem    Line :   128
(IVPS       0       1) -> (VENC     0       1)   Mode :   SW_Offline    Line :     0
(IVPS       0       2) -> (VENC     0       2)   Mode :   HW_Online    Line :     0
(IVPS       0       3) -> (VENC     0       3)   Mode :   Mode_Unset    Line :     0
(IVPS       0       4) -> (VENC     0       4)   Mode :   SW_Low_Latency Line :   128
"""

    OFFLINE_TABLE = """--------------------Link Table V2----------------------------------------------------
         Src            |          Dst               |                               |
(ModId   GrpId   ChnId) | (ModId   GrpId   ChnId)    |     Mode    |        line     |
-------------------------------------------------------------------------------------
(IVPS       0       0) -> (VENC     0       0)   Mode :   SW_Offline    Line :     0
(IVPS       0       1) -> (JENC     0       1)   Mode :   SW_Offline    Line :     0
"""

    def hint(self, result):
        matched = [issue for issue in result["issues"]
                   if issue["field"] == "link_table 非 HSK 链路"]
        self.assertEqual(len(matched), 1)
        return matched[0]

    def test_only_low_mem_and_low_latency_are_hsk(self):
        topology = parse(self.MIXED_TABLE)["samples"][0]["topology"]
        self.assertEqual({link["mode"] for link in topology["hsk_links"]},
                         {"SW_Low_Mem", "SW_Low_Latency"})
        self.assertEqual({link["mode"] for link in topology["non_hsk_links"]},
                         {"SW_Offline", "HW_Online", "Mode_Unset"})

    def test_non_hsk_links_are_reported_not_dropped(self):
        issue = self.hint(parse(self.MIXED_TABLE))
        self.assertEqual(issue["level"], "提示")
        # 每条链路都要能被定位到，且 Mode 原样出现在提示里。
        for mode in ("SW_Offline", "HW_Online", "Mode_Unset"):
            self.assertIn(mode, issue["message"])
        self.assertIn("VENC 0/1", issue["message"])
        self.assertIn("SW_Low_Mem/SW_Low_Latency", issue["message"])

    def test_low_latency_link_counts_as_hsk(self):
        topology = parse(self.MIXED_TABLE)["samples"][0]["topology"]
        self.assertIn(("VENC", 0, 4), {(link["consumer"], link["dst"]["grp"],
                                        link["dst"]["chn"])
                                       for link in topology["hsk_links"]})

    def test_offline_only_sample_has_no_forms(self):
        # 全是 offline 绑定时不能凭空建出 HSK 形态，但必须给出提示而不是空报告。
        sample = parse(self.OFFLINE_TABLE)["samples"][0]
        self.assertEqual(sample["topology"]["hsk_links"], [])
        self.assertEqual(sample["topology"]["forms"], [])
        self.assertEqual(len(sample["topology"]["non_hsk_links"]), 2)


class OfflineDiagnosisTest(unittest.TestCase):
    """`SW_Offline` 链路按第 3.2 节的业务计数差值定位卡死段。

    fixture 里 `IVPS 0/2 -> VENC 0/2` 就是 SW_Offline：上游是 grp0/chn2/flt5（VGP），
    下游是 venc chn2。每处改动都按行号加出现次数断言，fixture 变动时测试直接失败，
    而不是静默失效。行号是 1-based，与 `sed -n` 看到的一致。
    """

    # FILTER STATE grp0/chn2/flt5：TotalCnt / InCnt / OutCnt 都是 2003984。
    IVPS_TAIL = 96
    # VENC STREAM BUF STATUS chn2：ReadCycle / WriteCycle 2004068，AvalRSize 0。
    VENC_STREAM = 154
    # VENC CHN STATUS 2 chn2：FrmRecv / SubMitCnt / RecvBsCnt / BsFrmCnt 都是 2004068。
    VENC_STATUS2 = 166

    # 只涨 TotalCnt 与 InCnt，OutCnt 冻结 -> upstream_stall。
    IN_ONLY = (IVPS_TAIL, "VGP    2003984    0     0     2003984",
               "VGP    2004084    0     0     2004084", 1)
    # filter 整级推进。
    OUT_MOVES = (IVPS_TAIL, "VGP    2003984    0     0     2003984    2003984",
                 "VGP    2004084    0     0     2004084    2004084", 1)
    # 只涨 FrmRecv，SubMitCnt 冻结 -> downstream_stall。
    RECV_ONLY = (VENC_STATUS2, "Y     2004068       30.7", "Y     2004168       30.7", 1)
    # FrmRecv 与 SubMitCnt 一起涨。
    RECV_AND_SUBMIT = (VENC_STATUS2, "2004068", "2004168", 4)
    # 码流没被取走，AvalRSize 开始积累 -> stream_buf_backpressure。
    AVAL_GROWS = (VENC_STREAM, "2004068    0         203338", "2004068    4096      203338", 1)

    def two_samples(self, *edits):
        lines = SAMPLE.splitlines()
        for number, old, new, count in edits:
            self.assertEqual(lines[number - 1].count(old), count, lines[number - 1])
            lines[number - 1] = lines[number - 1].replace(old, new)
        return ("===== SAMPLE 1 =====\n" + SAMPLE +
                "===== SAMPLE 2 =====\n" + "\n".join(lines) + "\n")

    def link(self, *edits):
        return parse(self.two_samples(*edits))["samples"][1]["offline_links"][0]

    def test_exposes_upstream_and_downstream_counters(self):
        entry = parse(two_samples())["samples"][0]["offline_links"][0]
        self.assertEqual(entry["src"], {"module": "IVPS", "grp": 0, "chn": 2})
        self.assertEqual(entry["dst"], {"module": "VENC", "grp": 0, "chn": 2})
        self.assertEqual(entry["consumer"], "VENC")
        self.assertEqual((entry["upstream"]["filter"], entry["upstream"]["engine"]), (5, "VGP"))
        self.assertEqual(entry["upstream"]["in_cnt"], 2003984)
        self.assertEqual(entry["upstream"]["out_fps"], 29.99)
        # 配置帧率：IVPS 抽帧与编码码控都要带出来，低 OutFps 才分得清是配置还是停滞。
        self.assertEqual((entry["upstream"]["frc_mode"], entry["upstream"]["frc"]),
                         ("RATIO", "30.0:30.0"))
        self.assertEqual(entry["downstream"]["recv"], 2004068)
        self.assertEqual(entry["downstream"]["submit"], 2004068)
        self.assertEqual(entry["downstream"]["read_cycle"], 2004068)
        self.assertEqual((entry["downstream"]["rc_mode"], entry["downstream"]["src_fr"],
                          entry["downstream"]["dst_fr"]), ("CBR", 30, 30))
        self.assertEqual(entry["downstream"]["out_fps"], 30.7)
        self.assertEqual(entry["downstream"]["hw_used"], "N")

    def test_flat_upstream_and_encoder_is_no_input(self):
        # 单次采样拿不到差值，verdict 必须是 None 而不是默认判成卡死。
        self.assertIsNone(parse(two_samples())["samples"][0]["offline_links"][0]["verdict"])
        entry = self.link()
        self.assertEqual(entry["verdict"], "no_input")
        self.assertIn("VIN", entry["evidence"])

    def test_filter_input_without_output_is_upstream_stall(self):
        entry = self.link(self.IN_ONLY)
        self.assertEqual(entry["verdict"], "upstream_stall")
        self.assertIn("filter 5", entry["evidence"])

    def test_ivps_output_without_encoder_receive_is_dispatch_drop(self):
        entry = self.link(self.OUT_MOVES)
        self.assertEqual(entry["verdict"], "link_dispatch_drop")
        self.assertIn("FrmRecv", entry["evidence"])

    def test_encoder_receive_without_submit_is_downstream_stall(self):
        entry = self.link(self.OUT_MOVES, self.RECV_ONLY)
        self.assertEqual(entry["verdict"], "downstream_stall")
        self.assertIn("SubMitCnt", entry["evidence"])
        self.assertIn("BufFullCnt", entry["evidence"])

    def test_submit_without_read_is_stream_backpressure(self):
        entry = self.link(self.OUT_MOVES, self.RECV_AND_SUBMIT, self.AVAL_GROWS)
        self.assertEqual(entry["verdict"], "stream_buf_backpressure")
        self.assertIn("ReadCycle", entry["evidence"])

    def test_missing_downstream_proc_is_insufficient_evidence(self):
        # 有 link_table 但没有 venc proc 时不能硬判，只能说证据不足。
        without_venc = SAMPLE[:SAMPLE.index("-------- VENC CHN ATTR 1")]
        result = parse("===== SAMPLE 1 =====\n" + without_venc +
                       "===== SAMPLE 2 =====\n" + without_venc)
        entry = result["samples"][1]["offline_links"][0]
        self.assertEqual(entry["verdict"], "insufficient_evidence")
        self.assertIsNone(entry["downstream"])

    def test_stall_verdicts_become_issues_but_no_input_does_not(self):
        issues = [issue for issue in parse(self.two_samples(self.OUT_MOVES))["issues"]
                  if issue["field"].startswith("offline 链路")]
        self.assertEqual([issue["field"] for issue in issues], ["offline 链路 link_dispatch_drop"])
        self.assertEqual(issues[0]["level"], "高风险")
        self.assertEqual(issues[0]["channel"], "IVPS 0/2 -> VENC 0/2")
        # no_input 只作信息呈现，不写成现场问题。
        self.assertEqual([issue for issue in parse(self.two_samples())["issues"]
                          if issue["field"].startswith("offline 链路")], [])

    def test_non_offline_modes_get_no_verdict(self):
        text = SAMPLE.replace("(IVPS       0       2) -> (VENC     0       2)   Mode :   SW_Offline",
                              "(IVPS       0       2) -> (VENC     0       2)   Mode :   HW_Online")
        result = parse("===== SAMPLE 1 =====\n" + text + "===== SAMPLE 2 =====\n" + text)
        entry = result["samples"][1]["offline_links"][0]
        self.assertIsNone(entry["verdict"])
        self.assertIn("HW_Online", entry["evidence"])
        self.assertEqual([issue for issue in result["issues"]
                          if issue["field"].startswith("offline 链路")], [])


class ArithmeticTest(unittest.TestCase):
    def test_wraps_at_65536(self):
        self.assertEqual(hsk_widths(65000, 1000), (65000, 1000, 1536))
        self.assertEqual(hsk_widths(22528, 24064)[2], 1536)

    def test_progress_verdicts(self):
        self.assertIn("尚未推进", progress_verdict(0, 1536))
        self.assertIn("握手区间", progress_verdict(736, 1536))
        self.assertIn("syncVal", progress_verdict(1536, 1536))
        self.assertIn("越界", progress_verdict(2000, 1536))
        self.assertIn("握手高度为 0", progress_verdict(0, 0))

    def test_tokenize_keeps_bracket_blocks_and_joins_colon(self):
        self.assertEqual(tokenize("1 :24064"), ["1:24064"])
        self.assertEqual(tokenize("0.0 :  0.0"), ["0.0:0.0"])
        self.assertEqual(tokenize("[26   255] 0       19456"), ["[26   255]", "0", "19456"])


class PipelineFlowTest(unittest.TestCase):
    """SKILL.md 第 3.2 节：冻结的计数要按帧流转复核，不能只看上游有没有动。

    fixture 里 `IVPS 0/0 -> VENC 0/0` 是 SW_Low_Mem：IVPS chn0/flt1 计数冻结、目的
    venc chn0 仍在收帧时，上游这一级不能判成停摆。行号是 1-based，与 `sed -n` 一致。
    """

    # FILTER STATE grp0/chn0/flt1：TotalCnt / InCnt / OutCnt 都是 2003984。
    IVPS_CHN0 = 92
    # VENC CHN STATUS 2 chn0：FrmRecv 与 SubMitCnt 都是 2004069。
    VENC_CHN0 = 165

    def two_samples(self, *edits):
        lines = SAMPLE.splitlines()
        for number, old, new, count in edits:
            self.assertEqual(lines[number - 1].count(old), count, lines[number - 1])
            lines[number - 1] = lines[number - 1].replace(old, new)
        return ("===== SAMPLE 1 =====\n" + SAMPLE +
                "===== SAMPLE 2 =====\n" + "\n".join(lines) + "\n")

    def hint(self, group, *edits):
        issues = parse(self.two_samples(*edits))["issues"]
        return next(issue["message"] for issue in issues if issue.get("channel") == group)

    def test_frozen_upstream_with_receiving_encoder_is_not_a_stall(self):
        # IVPS chn0/flt1 计数不变，但它绑定的 venc chn0 还在收帧 -> 帧流没有断。
        message = self.hint("ivps/grp0/chn0/flt1",
                            (self.VENC_CHN0, "2004069", "2004169", 2))
        self.assertIn("仍在收帧", message)
        self.assertIn("不能据此把这一级判成停摆", message)

    def test_frozen_upstream_without_downstream_flow_stays_a_stall_hint(self):
        message = self.hint("ivps/grp0/chn0/flt1")
        self.assertIn("全部不变", message)
        self.assertNotIn("仍在收帧", message)


if __name__ == "__main__":
    unittest.main()
