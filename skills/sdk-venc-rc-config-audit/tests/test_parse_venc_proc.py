import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from parse_venc_proc import parse


PROC = """[SDK version]: test
-------- VENC CHN ATTR 1 -----------------------------------------------------------
ID Pid Type Profile Level wSrc hSrc Strd0 Strd1 maxW maxH CropEn PixFmt link Range BufMode StrmBufSize(KB)
0 255 H264 High 52 2688 1520 2688 2688 2688 1520 N NV12 Y FULL Ring 1500
-------- VENC CHN RC ATTR 1 -----------------------------------------------------------
ID RcMode SrcFr DstFr TargetBitRate MaxBitRate MinQp MaxQp MinIQp MaxIQp IQpDelta IpropMax IpropMin StartQp QpDltRng SvcEn ChgPos StillPercent MaxStillQp
0 CBR 30 30 4096 - 10 48 10 48 0 100 1 -1 10 N - - -
-------- VENC CHN GOP ATTR  -----------------------------------------------------------
ID GopMode Gop LtrGop LtrRefType SpGop SpRefType
0 NormalP 60 - - - -
-------- VENC CHN RC ATTR 3 -----------------------------------------------------------
ID BlkRcSize SliceIQp SlicePQp CbQPOffset CrQPOffset MotionSen MotionAlpha StaticIPer CtbRc CtbRcQpDelRng UpperLimit Alpha Beta WeightSum
0 2 [10,51] [10,51] -6 -6 8 128 0 N 3 10 - - -
-------- VENC CHN RJ&SupFrm ATTR  -----------------------------------------------------------
ID RJEn RJThr(bps) RJMode RJGaps RJSkipIntv SupFrmEn SupPri SupThrI SupThrP
0 N - - - - N - - -
-------- VENC CHN STATUS 2 -----------------------------------------------------------
VeChn bRecv FrmRecv RecvFps DiscardedNum SubMitCnt SubMitFail RecvBsCnt BsFrmCnt OutFps BitRate(kbps) WaitEncFail SeqDiscont
0 Y 1062 30.7 0 1062 0 1062 1062 29.8 4120 0 0
"""

# QpDltRng 有两种形态：两列 QpDltRngMin/QpDltRngMax，或单列 QpDltRng（仅上界）。
TWO_COL_PROC = """[SDK version]: test
-------- VENC CHN RC ATTR 1 -----------------------------------------------------------
ID RcMode SrcFr DstFr TargetBitRate MaxBitRate MinQp MaxQp MinIQp MaxIQp IQpDelta IpropMax IpropMin StartQp QpDltRngMin QpDltRngMax SvcEn ChgPos StillPercent MaxStillQp
0 CBR 25 25 3072 - 10 51 10 51 1 35 25 -1 -3 3 N - - -
1 CBR 25 25 512 - 11 43 10 43 -9 35 25 36 -3 3 N - - -
"""

# 按 proc 实际输出的字段宽度对齐构造，不使用板端真实数据：
# QPMAP1/2 为 "%-5d%-7s%-8d%-8d%-#13llx%-13x%-8s%-9d"，LocalMap 无 Finely 列，
# SVC PARAM 续行前 10 列留空，SVC REGION 续行前 4 列留空。
SVC_QPMAP = """-------- VENC CHN USER QPMAP1 INFO -----------------------------------------------------------
ID   Finely MbWidth MapSize QpMapPhyAddr QpMapVirAddr UseMbuf BlkId
0    Y      168     10080   0x8a1c0000   0xffff8a1c   N       -1
-------- VENC CHN USER QPMAP2 INFO -----------------------------------------------------------
ID   Finely MbWidth MapSize QpMapPhyAddr QpMapVirAddr UseMbuf BlkId
0    Y      168     10080   0x8a1d0000   0xffff8a1d   Y       3
-------- VENC CHN USER LocalMap INFO -----------------------------------------------------------
ID   MbWidth MapSize QpMapPhyAddr QpMapVirAddr UseMbuf BlkId
0    168     10080   0x8a1e0000   0xffff8a1e   N       -1
-------- VENC CHN SVC PARAM INFO -----------------------------------------------------------
ID  AbsQp Sync Adapt RIdx WIdx IsFull BgIQp BgPQp TypeNum TypeId IQp  PQp
0   N     Y    N     0    1    N      6     6     3       0      -8   -8
                                                          1      -4   -4
                                                          2      0    0
-------- VENC CHN SVC REGION INFO -----------------------------------------------------------
ID   ResIdx RectNum Pts           RectIdx Type X     Y     Width Height
0    0      3       0x1a2b3c4d    0       0    64    64    320   240
                                  1       1    448   256   320   240
                                  2       2    832   448   320   240
"""


class ParseProcTest(unittest.TestCase):
    def test_normalizes_rc_gop_and_status(self):
        result = parse(PROC)
        channel = result["channels"][0]
        self.assertEqual(channel["codec"], "H264")
        self.assertEqual(channel["rc"]["RcMode"], "CBR")
        self.assertEqual(channel["gop"]["gop"], 60)
        self.assertEqual(channel["rc_attr3"]["MotionSen"], 8)
        self.assertEqual(channel["status"]["bitrate_kbps"], 4120)
        self.assertAlmostEqual(channel["status"]["target_deviation_percent"], 0.59, places=1)
        self.assertIn("rj_superframe", channel)
        self.assertFalse(result["issues"])

    def test_marks_single_column_qp_delta_range(self):
        # 单列形态只代表上界，Min 视为未知。
        channel = parse(PROC)["channels"][0]
        self.assertEqual(channel["rc"]["QpDltRngShape"], "single")
        self.assertEqual(channel["rc"]["QpDltRng"], 10)

    def test_parses_two_column_qp_delta_range(self):
        channels = parse(TWO_COL_PROC)["channels"]
        self.assertEqual(channels[0]["rc"]["QpDltRngShape"], "min_max")
        self.assertEqual(channels[0]["rc"]["QpDltRngMin"], -3)
        self.assertEqual(channels[0]["rc"]["QpDltRngMax"], 3)
        self.assertNotIn("QpDltRng", channels[0]["rc"])
        self.assertEqual(channels[1]["rc"]["QpDltRngMin"], -3)

    def test_flags_two_column_qp_delta_range_out_of_range(self):
        text = TWO_COL_PROC.replace("-1 -3 3 N", "-1 -3 20 N")
        issues = parse(text)["issues"]
        self.assertTrue(any(issue["field"] == "QpDltRngMax" for issue in issues))
        self.assertTrue(any("[0,16]" in issue["message"] for issue in issues))

    def test_flags_single_column_qp_delta_range_out_of_range(self):
        text = PROC.replace(" -1 10 N ", " -1 20 N ")
        issues = parse(text)["issues"]
        self.assertTrue(any(issue["field"] == "QpDltRng" for issue in issues))

    def test_ignores_node_count_table_after_status2(self):
        text = PROC + """
VeChn NodeCnt BusyNod FreeNod UserNod
0 64 0 64 0
"""
        channel = parse(text)["channels"][0]
        self.assertEqual(channel["status"]["recv_fps"], 30.7)
        self.assertEqual(channel["status"]["out_fps"], 29.8)
        self.assertEqual(channel["status"]["bitrate_kbps"], 4120)

    def test_reports_sdk_version_from_proc_banner(self):
        result = parse(PROC.replace("[SDK version]: test", "[SDK version]: AX615_V3.0.0"))
        self.assertEqual(result["environment"]["sdk_version"], "AX615_V3.0.0")
        self.assertEqual(result["environment"]["sdk_version_source"], "proc [SDK version]")

    def test_flags_missing_sdk_version(self):
        result = parse(PROC.replace("[SDK version]: test\n", ""))
        self.assertEqual(result["environment"]["sdk_version"], "unknown")
        self.assertIsNone(result["environment"]["sdk_version_source"])
        self.assertEqual(result["issues"][0]["field"], "SDK version")
        self.assertEqual(result["issues"][0]["level"], "提示")

    def test_covers_vpu_controls_and_jpeg_rc(self):
        text = """-----H26X RC CTRL0--------------------------------------------------------------
ChnId RcMode BlockSize StatTime IQp[Min,Max] PQp[Min,Max] IQpFrame PQpFrame IPRation IdrQpDeltaRng FixQp
0 CBR 2 1 [10,48] [10,48] [10,51] [10,51] [1,100] [2,16] 30-30
-----H26X RC CTRL1--------------------------------------------------------------
ChnId RcFps TargetBit InitQp MotionSen MotionAlpha IntraQpDelta StillIBitPct CtuBitsRefEn CtuBitsRefQpDelta
0 30 4096 -1 8 128 0 0 0 3
-----H26X RC CTRL2--------------------------------------------------------------
ChnId ChangePos MinStillPct MaxStillQp ExtraBitPct LongTermUnit ShortTime LongTime LongBitRate Alpha Beta WeightSum
0 90 10 48 10 1 1 5 [512,4096] 16 16 64
-------- JENC CHN RC ATTR  ---------------------------
ID RcMode StatTime SrcFr DstFr Br(kbps) MinQp MaxQp FixedQp Qfactor
0 CBR 1 30 30 400 10 48 - -
"""
        result = parse(text)
        self.assertEqual(result["channels"][0]["vpu_rc"]["ctrl0"]["RcMode"], "CBR")
        self.assertEqual(result["channels"][0]["vpu_rc"]["ctrl1"]["MotionAlpha"], 128)
        self.assertEqual(result["channels"][0]["jpeg_rc"]["RcMode"], "CBR")
        self.assertIn("MJPEG CBR", result["coverage"]["api_modes"])

    def test_parses_qpmap_sections(self):
        channel = parse(SVC_QPMAP)["channels"][0]
        qpmap = channel["qpmap"]
        self.assertEqual(qpmap["map1"]["Finely"], "Y")
        self.assertEqual(qpmap["map1"]["MbWidth"], 168)
        self.assertEqual(qpmap["map2"]["BlkId"], 3)
        self.assertEqual(qpmap["map2"]["UseMbuf"], "Y")
        # LocalMap 没有 Finely 列，不能把后一列的值错位读成 Finely。
        self.assertNotIn("Finely", qpmap["local_map"])
        self.assertEqual(qpmap["local_map"]["MapSize"], 10080)
        # 地址保留 proc 打印的十六进制原样，便于与原始文本比对。
        self.assertEqual(qpmap["map1"]["QpMapPhyAddr"], "0x8a1c0000")

    def test_folds_svc_param_continuation_rows(self):
        channel = parse(SVC_QPMAP)["channels"][0]
        svc = channel["svc_param"]
        self.assertEqual(svc["AbsQp"], "N")
        self.assertEqual(svc["BgIQp"], 6)
        self.assertEqual(svc["TypeNum"], 3)
        self.assertEqual([entry["TypeId"] for entry in svc["types"]], [0, 1, 2])
        self.assertEqual([entry["IQp"] for entry in svc["types"]], [-8, -4, 0])

    def test_folds_svc_region_continuation_rows(self):
        channel = parse(SVC_QPMAP)["channels"][0]
        region = channel["svc_region"][0]
        self.assertEqual(region["ResIdx"], 0)
        self.assertEqual(region["RectNum"], 3)
        self.assertEqual(region["Pts"], "0x1a2b3c4d")
        self.assertEqual([rect["RectIdx"] for rect in region["rects"]], [0, 1, 2])
        # 续行以前会被当成新记录并整体错列，Type 会读到 X 的值。
        self.assertEqual([rect["Type"] for rect in region["rects"]], [0, 1, 2])
        self.assertEqual(region["rects"][2]["X"], 832)

    def test_svc_and_qpmap_sample_is_clean(self):
        issues = [issue for issue in parse(SVC_QPMAP)["issues"]
                  if issue["field"] != "SDK version"]
        self.assertFalse(issues)

    def test_flags_svc_qp_out_of_relative_range(self):
        text = SVC_QPMAP.replace("0      -8   -8", "0      -80  -8")
        issues = parse(text)["issues"]
        self.assertTrue(any("TYPE0 IQp" in issue["field"] for issue in issues))
        self.assertTrue(any("[-51,51]" in issue["message"] for issue in issues))

    def test_flags_svc_absolute_qp_out_of_range(self):
        text = SVC_QPMAP.replace("0   N     Y    N", "0   Y     Y    N")
        issues = parse(text)["issues"]
        # bAbsQp=Y 时 QP 必须落在 [0,51]，负的 deltaQp 即为非法。
        self.assertTrue(any("[0,51]" in issue["message"] for issue in issues))

    def test_flags_rect_count_mismatch(self):
        text = SVC_QPMAP.replace("0    0      3       0x1a2b3c4d",
                                 "0    0      4       0x1a2b3c4d")
        issues = parse(text)["issues"]
        self.assertTrue(any(issue["field"] == "SVC RectIdx" for issue in issues))

    def test_flags_unalignable_continuation_row(self):
        text = SVC_QPMAP.replace("                                  1       1    448   256   320   240",
                                 "                                  1       1    448")
        issues = parse(text)["issues"]
        self.assertTrue(any("续行字段数" in issue["message"] for issue in issues))


if __name__ == "__main__":
    unittest.main()
