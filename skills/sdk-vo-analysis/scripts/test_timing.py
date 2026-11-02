#!/usr/bin/env python3
"""sdk-vo-analysis 时序脚本单元测试（标准库 unittest，无第三方依赖）。

运行：
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_timing.py
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts -p 'test_*.py'
"""
from __future__ import annotations

import contextlib
import inspect
import io
import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import check_vo_timing as chk
import gen_vo_timing as gen
import timing_common as tc


def valid_bt656_sdr():
    """与已验证表 1920x1080@30f_bt656 一致的合法参数（显式 bDlbClk=0）。"""
    return {
        "bIop": 1, "u16Vact": 1080, "u16Vbb": 36, "u16Vfb": 4,
        "u16Hact": 1920, "u16Hbb": 148, "u16Hfb": 88, "u16Hpw": 44,
        "u16Vpw": 5, "u32Pclk": 148500, "bIdv": 1, "bIhs": 1, "bIvs": 1,
        "bDlbClk": 0,
    }


def serial_640x480(fps):
    """AX615D 串行 sRGB 640x480 时序：htotal=800、vtotal=500，pclk 决定配置公式刷新率。

    fps=45 → pclk=54000（÷3 后 45Hz，越过 640x480@30 上限）；
    fps=30 → pclk=36000（÷3 后 30Hz，刚好在上限内）。两者 pclk 均精确命中档位表。
    """
    if fps not in (30, 45):
        raise ValueError("仅用于 30/45fps 两个档位")
    return {
        "bIop": 1, "u16Vact": 480, "u16Vbb": 10, "u16Vfb": 9,
        "u16Hact": 640, "u16Hbb": 40, "u16Hfb": 96, "u16Hpw": 24,
        "u16Vpw": 1, "u32Pclk": 54000 if fps == 45 else 36000,
        "bIdv": 1, "bIhs": 1, "bIvs": 1, "bDlbClk": 0,
    }


def serial_640x480_x2():
    """AX615D 串行 sRGB ×2（srgb565）640x480@30：htotal=1000、vtotal=600、pclk=36000。"""
    return {
        "bIop": 1, "u16Vact": 480, "u16Vbb": 20, "u16Vfb": 99,
        "u16Hact": 640, "u16Hbb": 40, "u16Hfb": 296, "u16Hpw": 24,
        "u16Vpw": 1, "u32Pclk": 36000, "bIdv": 1, "bIhs": 1, "bIvs": 1,
        "bDlbClk": 0,
    }


def refresh_fps(params, intf, fmt):
    """取配置公式刷新率；None（关键字段缺失）视为测试失败。"""
    _, _, fps, _ = tc.refresh_formula(params, intf, fmt)
    if fps is None:
        raise AssertionError(f"刷新率不应为 None: intf={intf} fmt={fmt}")
    return fps


def run_main(module, argv):
    """执行脚本 main()，返回 (退出码, stdout 文本)。"""
    buf = io.StringIO()
    old_argv = sys.argv
    try:
        sys.argv = [module.__name__] + argv
        with contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            code = module.main()
    finally:
        sys.argv = old_argv
    return code, buf.getvalue()


class TestNormalizeAndCapability(unittest.TestCase):
    def test_srgb_alias_normalized_to_dpi(self):
        self.assertEqual(tc.normalize_interface("SRGB"), "dpi")
        self.assertEqual(tc.normalize_interface(" srgb "), "dpi")
        self.assertEqual(tc.normalize_interface("bt656"), "bt656")

    def test_format_resolution_never_assumes_dpi_parallel(self):
        self.assertEqual(tc.resolve_format("bt1120", None), "yuv422")
        self.assertEqual(tc.resolve_format("srgb", "SRGB565"), "srgb565")
        for value in (None, "  "):
            with self.assertRaises(tc.TimingError) as ctx:
                tc.resolve_format("dpi", value)
            self.assertEqual(ctx.exception.code, "missing_format")
        errors = tc.capability_errors("dpi")
        self.assertTrue(any("缺少输出格式" in e for e in errors))
        with self.assertRaises(tc.TimingError):
            tc.refresh_formula(valid_bt656_sdr(), "dpi")
        with self.assertRaises(tc.TimingError):
            tc.refresh_factor("srgb", None, 0)

    def test_capability_interface_format(self):
        self.assertEqual(tc.capability_errors("bt656", "yuv422"), [])
        self.assertTrue(tc.capability_errors("bt1120", "rgb565"))
        self.assertEqual(tc.capability_errors("dpi", "rgb565"), [])
        self.assertEqual(tc.capability_errors("srgb", "srgb888a"), [])
        self.assertTrue(tc.capability_errors("dpi", "yuv422"))
        self.assertTrue(tc.capability_errors("dsi", "yuv422"))

    def test_capability_ax615d_distinguishes_serial_srgb_and_parallel_dpi(self):
        self.assertTrue(tc.capability_errors("bt1120", "yuv422", "AX615D"))
        self.assertTrue(tc.capability_errors("dpi", "rgb565", "AX615D"))
        self.assertEqual(tc.capability_errors("dpi", "srgb565", "AX615D"), [])
        self.assertEqual(
            tc.capability_errors("srgb", "srgb888", "ax615d", 640, 480, 30), [])
        self.assertTrue(
            tc.capability_errors("srgb", "srgb888", "ax615d", 800, 480, 30))
        self.assertTrue(
            tc.capability_errors("srgb", "srgb888", "ax615d", 640, 480, 60))
        self.assertEqual(tc.capability_errors("bt1120", "yuv422", "AX615Q"), [])
        self.assertEqual(tc.capability_errors("dpi", "rgb565", "AX615Q"), [])
        self.assertTrue(tc.capability_errors("dpi", "rgb565", "AX620"))
        self.assertEqual(tc.capability_errors("bt1120", "yuv422"), [])

    def test_serial_and_parallel_sets_match_factor_table(self):
        self.assertEqual(tc.PARALLEL_DPI_FMTS, frozenset({"rgb565"}))
        self.assertIn("srgb888b", tc.SERIAL_SRGB_FMTS)
        self.assertNotIn("rgb565", tc.SERIAL_SRGB_FMTS)


class TestValidateTiming(unittest.TestCase):
    def test_valid_params_pass(self):
        self.assertEqual(tc.validate_timing(valid_bt656_sdr()), [])
        self.assertEqual(
            tc.validate_timing(dict(valid_bt656_sdr(), u8DelaySel=4)), [])

    def test_missing_bdlbclk_is_error_not_sdr_default(self):
        params = valid_bt656_sdr()
        params.pop("bDlbClk")
        errors = tc.validate_timing(params)
        self.assertTrue(errors)
        self.assertTrue(any("bDlbClk" in e for e in errors))
        self.assertEqual(tc.validate_timing(params, require_all=False), [])

    def test_missing_optional_delay_sel_is_allowed(self):
        self.assertNotIn("u8DelaySel", valid_bt656_sdr())
        self.assertEqual(tc.validate_timing(valid_bt656_sdr()), [])

    def test_bool_fields_must_be_0_or_1(self):
        self.assertEqual(tc.validate_timing(dict(valid_bt656_sdr(), bIop=True)), [])
        errors = tc.validate_timing(dict(valid_bt656_sdr(), bIop=2))
        self.assertTrue(any("bIop" in e for e in errors))
        errors = tc.validate_timing(dict(valid_bt656_sdr(), bDlbClk=-1))
        self.assertTrue(any("bDlbClk" in e for e in errors))

    def test_bit_widths(self):
        self.assertTrue(tc.validate_timing(dict(valid_bt656_sdr(), u16Hpw=70000)))
        self.assertTrue(tc.validate_timing(dict(valid_bt656_sdr(), u16Vbb=-1)))
        self.assertTrue(tc.validate_timing(dict(valid_bt656_sdr(), u32Pclk=0)))
        self.assertTrue(tc.validate_timing(
            dict(valid_bt656_sdr(), u32Pclk=4294967296)))
        self.assertTrue(tc.validate_timing(dict(valid_bt656_sdr(), u8DelaySel=256)))
        self.assertTrue(tc.validate_timing(
            dict(valid_bt656_sdr(), u8DelaySel="3")))

    def test_size_constraints_from_header(self):
        self.assertEqual(
            tc.validate_resolution(tc.HACT_MIN, tc.VACT_MIN), [])
        self.assertEqual(
            tc.validate_resolution(tc.HACT_MAX, tc.VACT_MAX), [])
        self.assertTrue(tc.validate_resolution(15, 480))
        self.assertTrue(tc.validate_resolution(3841, 480))
        self.assertTrue(tc.validate_resolution(1921, 480))
        self.assertTrue(tc.validate_resolution(1920, 3))
        self.assertTrue(tc.validate_resolution(1920, 8191))
        self.assertTrue(tc.validate_resolution(1920, 481))

    def test_float_and_non_dict_rejected(self):
        errors = tc.validate_timing(dict(valid_bt656_sdr(), u16Hact=1920.0))
        self.assertTrue(any("u16Hact" in e for e in errors))
        self.assertTrue(tc.validate_timing([1, 2]))
        self.assertTrue(tc.validate_timing("{}"))

    def test_resolution_errors_reported_without_crash(self):
        # 回归：旧实现的分辨率校验循环会在首个字段后 break（hact 错误被吞掉）
        errors = tc.validate_timing({"u16Hact": 15, "u16Vact": 3},
                                    require_all=False)
        self.assertTrue(any("u16Hact" in e for e in errors))
        self.assertTrue(any("u16Vact" in e for e in errors))
        self.assertEqual(len(errors), len(set(errors)))


class TestRefresh(unittest.TestCase):
    def test_bt656_sdr_and_ddr(self):
        params = valid_bt656_sdr()
        htotal, vtotal, _, notes = tc.refresh_formula(params, "bt656", "yuv422")
        self.assertEqual((htotal, vtotal, notes), (2200, 1125, []))
        self.assertAlmostEqual(tc.actual_refresh(params, "bt656", "yuv422")[2], 30.0)
        ddr = dict(valid_bt656_sdr(), bDlbClk=1, u32Pclk=74250)
        self.assertAlmostEqual(refresh_fps(ddr, "bt656", "yuv422"), 30.0)

    def test_bt1120_and_dpi_not_divided_by_two(self):
        self.assertAlmostEqual(
            refresh_fps(valid_bt656_sdr(), "bt1120", "yuv422"), 60.0)
        self.assertAlmostEqual(
            refresh_fps(valid_bt656_sdr(), "dpi", "rgb565"), 60.0)

    def test_dpi_serial_multipliers_unified_with_srgb_alias(self):
        base = valid_bt656_sdr()
        self.assertAlmostEqual(refresh_fps(base, "dpi", "srgb565"), 30.0)
        self.assertAlmostEqual(refresh_fps(base, "srgb", "srgb666"), 30.0)
        self.assertAlmostEqual(refresh_fps(base, "srgb", "srgb565s"), 20.0)
        self.assertAlmostEqual(refresh_fps(base, "srgb", "srgb888"), 20.0)
        self.assertAlmostEqual(refresh_fps(base, "srgb", "srgb888a"), 15.0)
        self.assertAlmostEqual(refresh_fps(base, "srgb", "srgb888b"), 15.0)
        self.assertEqual(tc.refresh_factor("srgb", "srgb888a", 0), 4)
        self.assertEqual(tc.refresh_factor("bt656", "yuv422", 0), 2)
        self.assertEqual(tc.refresh_factor("bt656", "yuv422", 1), 1)
        self.assertEqual(tc.refresh_factor("bt1120", "yuv422", 0), 1)

    def test_missing_bdlbclk_never_defaults_to_sdr(self):
        params = valid_bt656_sdr()
        params.pop("bDlbClk")
        _, _, fps, notes = tc.refresh_formula(params, "bt656", "yuv422")
        self.assertIsNone(fps)
        self.assertTrue(any("bDlbClk" in n for n in notes))
        with self.assertRaises(tc.TimingError):
            tc.actual_refresh(params, "bt656", "yuv422")

    def test_illegal_format_raises(self):
        with self.assertRaises(tc.TimingError):
            tc.refresh_formula(valid_bt656_sdr(), "bt656", "rgb565")
        with self.assertRaises(tc.TimingError):
            tc.refresh_formula(valid_bt656_sdr(), "dpi", "yuv422")
        with self.assertRaises(tc.TimingError):
            tc.refresh_formula(valid_bt656_sdr(), "dsi", "yuv422")

    def test_refresh_factor_requires_explicit_dbl(self):
        # 不允许隐式默认 SDR：dbl 必须是显式参数（无默认值）
        dbl = inspect.signature(tc.refresh_factor).parameters["dbl"]
        self.assertIs(dbl.default, inspect.Parameter.empty)


class TestDatasetConsistency(unittest.TestCase):
    def test_dataset_issues_detects_mismatch(self):
        manifest = {"internalized_version": "V3.14.0"}
        datasets = {
            "a.json": {"sdk_version": "V3.13.0", "declared_count": 2,
                       "actual_count": 2},
            "b.json": {"sdk_version": "V3.14.0", "declared_count": 3,
                       "actual_count": 2},
            "c.json": {"sdk_version": "V3.14.0", "declared_count": 2,
                       "actual_count": 2},
        }
        issues = tc.dataset_issues(manifest, datasets)
        self.assertTrue(any("a.json" in i for i in issues))
        self.assertTrue(any("b.json" in i for i in issues))
        self.assertFalse(any("c.json" in i for i in issues))

    def test_real_reference_data_is_consistent(self):
        self.assertEqual(chk.data_consistency(), [])
        self.assertEqual(gen.data_consistency(), [])
        self.assertIn("V3.14.0", chk.load_version_hint())


class TestCompare(unittest.TestCase):
    def test_fixed_full_key_set_includes_bdlbclk_and_optional(self):
        self.assertEqual(chk.COMPARE_KEYS, tc.TIMING_KEYS)
        self.assertIn("bDlbClk", chk.COMPARE_KEYS)
        self.assertIn("u8DelaySel", tc.OPTIONAL_KEYS)

    def test_full_and_partial_matches_are_separated(self):
        cust = dict(valid_bt656_sdr(), u8DelaySel=0)
        entries = {
            "full": dict(cust),
            "partial": {k: v for k, v in cust.items() if k != "u8DelaySel"},
            "optional_diff": dict(cust, u8DelaySel=3),
        }
        similar, full, partial = chk.compare(entries, cust, limit=3)
        self.assertEqual(full, ["full"])
        names = [p[0] for p in partial]
        self.assertEqual(names, ["partial"])
        self.assertIn("u8DelaySel", partial[0][1])
        self.assertIn("u8DelaySel", partial[0][2])
        diff_map = {item[2]: item[3] for item in similar}
        self.assertEqual(diff_map["optional_diff"], {"u8DelaySel": (3, 0)})
        self.assertNotIn("optional_diff", names)

    def test_both_sides_missing_is_unknown(self):
        _, diffs, unknown, table_missing = chk._state_table({}, {})
        self.assertEqual(diffs, {})
        self.assertEqual(set(unknown), set(tc.TIMING_KEYS) | set(tc.OPTIONAL_KEYS))
        self.assertEqual(set(table_missing), set(unknown))

    def test_real_table_full_match_and_missing_field_partial(self):
        entries, _ = chk.load_sync_infos()
        exact = dict(entries["2560x1440@25f_bt1120"])
        _, full, partial = chk.compare(entries, exact, limit=3)
        self.assertIn("2560x1440@25f_bt1120", full)
        self.assertNotIn("2560x1440@25f_bt1120", [p[0] for p in partial])

        sdr = valid_bt656_sdr()  # 表内 1920x1080@30f_bt656 未记录 u8DelaySel
        _, full, partial = chk.compare(entries, sdr, limit=3)
        partial_names = [p[0] for p in partial]
        self.assertIn("1920x1080@30f_bt656", partial_names)
        self.assertNotIn("1920x1080@30f_bt656", full)

    def test_compare_sample_reports_unknown_and_optional_diff(self):
        samples, _, _ = chk.load_sample_infos()
        cust = dict(valid_bt656_sdr(), u8DelaySel=0)
        hits = chk.compare_sample(samples, cust, limit=2)
        by_index = {hit[2]: hit for hit in hits}
        self.assertIn(4, by_index)
        self.assertEqual(by_index[4][4], {})  # sample 第 4 条 u8DelaySel=0，全字段一致
        self.assertEqual(by_index[4][5], [])


class TestCheckMain(unittest.TestCase):
    def test_valid_params_exit_zero(self):
        code, out = run_main(chk, ["--json", json.dumps(valid_bt656_sdr()),
                                   "--intf", "bt656"])
        self.assertEqual(code, 0)
        self.assertIn("数据版本一致性：OK", out)
        self.assertIn("完整匹配", out)
        self.assertIn("部分匹配", out)
        self.assertIn("1920x1080@30f_bt656", out)

    def test_full_match_section_with_optional_field(self):
        cust = dict(valid_bt656_sdr(), u8DelaySel=0)
        code, out = run_main(chk, ["--json", json.dumps(cust), "--intf", "bt656"])
        self.assertEqual(code, 0)
        self.assertIn("完整匹配（14 固定字段 + u8DelaySel 全部一致", out)

    def test_non_object_json_rejected(self):
        code, out = run_main(chk, ["--json", "[1,2]"])
        self.assertEqual(code, 2)
        self.assertIn("invalid_json", out)

    def test_missing_bdlbclk_rejected(self):
        params = valid_bt656_sdr()
        params.pop("bDlbClk")
        code, out = run_main(chk, ["--json", json.dumps(params)])
        self.assertEqual(code, 2)
        self.assertIn("bDlbClk", out)

    def test_illegal_format_rejected_all_paths(self):
        code, out = run_main(chk, ["--json", json.dumps(valid_bt656_sdr()),
                                   "--intf", "bt656", "--fmt", "rgb565"])
        self.assertEqual(code, 2)
        self.assertIn("YUV422", out)

    def test_dpi_alias_and_chip_gate(self):
        params = dict(valid_bt656_sdr(), u16Vact=480, u16Vbb=12, u16Vfb=9,
                      u16Hact=800, u16Hbb=39, u16Hfb=6, u16Hpw=24, u16Vpw=1,
                      u32Pclk=33000)
        code, out = run_main(chk, ["--json", json.dumps(params), "--intf", "srgb",
                                   "--fmt", "srgb565", "--chip", "AX615Q"])
        self.assertEqual(code, 0)
        self.assertIn("别名", out)
        code, out = run_main(chk, ["--json", json.dumps(params), "--intf", "dpi",
                                   "--fmt", "rgb565", "--chip", "ax615d"])
        self.assertEqual(code, 2)
        self.assertIn("并行 DPI", out)
        code, out = run_main(chk, ["--json", json.dumps(params), "--intf", "dpi"])
        self.assertEqual(code, 2)
        self.assertIn("缺少输出格式", out)
        code, _ = run_main(chk, ["--json", json.dumps(params), "--chip", "AX620"])
        self.assertEqual(code, 2)

    def test_ax615d_serial_srgb_fps_ceiling_enforced(self):
        # check 路径基准：按配置公式刷新率判定，>30fps 即能力错误，=30fps 通过
        code, out = run_main(chk, ["--json", json.dumps(serial_640x480(45)),
                                   "--intf", "srgb", "--fmt", "srgb888",
                                   "--chip", "AX615D"])
        self.assertEqual(code, 2)
        self.assertIn("capability", out)
        self.assertIn("640x480@30", out)
        code, out = run_main(chk, ["--json", json.dumps(serial_640x480(30)),
                                   "--intf", "srgb", "--fmt", "srgb888",
                                   "--chip", "AX615D"])
        self.assertEqual(code, 0)

    def test_file_input_and_non_object_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.json")
            with open(good, "w", encoding="utf-8") as f:
                json.dump(valid_bt656_sdr(), f)
            code, _ = run_main(chk, ["--file", good])
            self.assertEqual(code, 0)
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("[1, 2]")
            code, out = run_main(chk, ["--file", bad])
            self.assertEqual(code, 2)
            self.assertIn("invalid_json", out)


class TestGenLookupAndThreshold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries, _ = gen.load_sync_infos()
        cls.reachable, cls.deriv, _ = gen.load_pclk_table()

    def test_untagged_entry_is_not_a_verified_hit(self):
        hits, skipped = gen.find_exact(self.entries, "bt656", 360, 240, 60)
        self.assertEqual(hits, [])
        self.assertTrue(any(name == "360x240@60f" for name, _ in skipped))
        self.assertIsNone(gen.intf_of_name("360x240@60f"))
        self.assertEqual(gen.intf_of_name("1920x1080@30f_bt656"), "bt656")

    def test_table_hit_requires_explicit_same_interface(self):
        hits, _ = gen.find_exact(self.entries, "bt1120", 1920, 1080, 30)
        self.assertEqual(hits, [])
        hits, _ = gen.find_exact(self.entries, "bt656", 1920, 1080, 30)
        self.assertEqual(hits[0][1], "1920x1080@30f_bt656")
        self.assertTrue(all(h[0] <= gen.FPS_TOLERANCE_RATIO for h in hits))

    def test_two_percent_threshold(self):
        hits, _ = gen.find_exact(self.entries, "bt1120", 2560, 1440, 25.4)
        self.assertTrue(hits)
        self.assertLessEqual(hits[0][0], gen.FPS_TOLERANCE_RATIO)
        hits, _ = gen.find_exact(self.entries, "bt1120", 2560, 1440, 26.0)
        self.assertEqual(hits, [])

    def test_entry_missing_fields_never_verified_hit(self):
        hits, skipped = gen.find_exact(self.entries, "bt656", 1920, 1080, 30)
        self.assertTrue(all("缺" not in reason for _, reason in skipped))
        incomplete = {"x_bt656": {"u16Hact": 1920, "u16Vact": 1080}}
        hits, skipped = gen.find_exact(incomplete, "bt656", 1920, 1080, 30)
        self.assertEqual(hits, [])
        self.assertTrue(any("表未记录字段" in reason for _, reason in skipped))

    def test_derive_candidates_are_validated_and_within_threshold(self):
        _, candidates, _, _ = gen.derive(
            self.entries, self.reachable, "dpi", 800, 480, 60, "rgb565")
        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertLessEqual(candidate["fps_error_ratio"],
                                 gen.FPS_TOLERANCE_RATIO)
            self.assertEqual(tc.validate_timing(candidate["params"]), [])
            self.assertIn(candidate["params"]["u32Pclk"], self.reachable)
            self.assertIn("复核通过", candidate["validity"])


class TestGenMain(unittest.TestCase):
    def test_table_hit(self):
        code, out = run_main(gen, ["--intf", "bt656", "--res", "1920x1080",
                                   "--fps", "30"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["mode"], "table")
        self.assertEqual(payload["entry"], "1920x1080@30f_bt656")
        self.assertEqual(payload["fps_tolerance"], "≤2%（相对误差）")
        other = {m["entry"] for m in payload["other_matches"]}
        self.assertIn("1920x1080@30f_bt656_db-edge", other)

    def test_untagged_entry_never_reported_as_table(self):
        code, out = run_main(gen, ["--intf", "bt656", "--res", "360x240",
                                   "--fps", "60"])
        self.assertIn(code, (0, 1))
        if code == 0:
            self.assertNotEqual(json.loads(out).get("entry"), "360x240@60f")
        else:
            self.assertIn("360x240@60f", out)

    def test_derive_mode_within_threshold(self):
        code, out = run_main(gen, ["--intf", "dpi", "--fmt", "rgb565",
                                   "--res", "800x480", "--fps", "60"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["mode"], "derived")
        self.assertTrue(payload["candidates"])
        for candidate in payload["candidates"]:
            self.assertLessEqual(candidate["fps_error_ratio"],
                                 gen.FPS_TOLERANCE_RATIO)

    def test_dpi_missing_format_rejected(self):
        code, out = run_main(gen, ["--intf", "dpi", "--res", "800x480",
                                   "--fps", "60"])
        self.assertEqual(code, 2)
        self.assertIn("缺少输出格式", out)
        code, out = run_main(gen, ["--intf", "srgb", "--res", "640x480",
                                   "--fps", "30"])
        self.assertEqual(code, 2)
        self.assertIn("缺少输出格式", out)

    def test_no_solution_is_not_a_capability_proof(self):
        code, out = run_main(gen, ["--intf", "dpi", "--fmt", "rgb565",
                                   "--res", "3840x2160", "--fps", "60"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["code"], "no_solution")
        self.assertIn("不构成", payload["details"]["capability_note"])

    def test_chip_gate_and_missing_chip_marker(self):
        code, out = run_main(gen, ["--chip", "ax615d", "--intf", "dpi",
                                   "--fmt", "srgb565", "--res", "800x480",
                                   "--fps", "30"])
        self.assertEqual(code, 2)
        self.assertIn("640x480@30", out)
        code, out = run_main(gen, ["--intf", "bt656", "--res", "1920x1080",
                                   "--fps", "30"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["chip_unknown"])
        self.assertTrue(any("[chip]" in w for w in payload["warnings"]))

    def test_illegal_format_rejected(self):
        code, out = run_main(gen, ["--intf", "bt1120", "--res", "1920x1080",
                                   "--fps", "30", "--fmt", "rgb565"])
        self.assertEqual(code, 2)
        self.assertIn("YUV422", out)

    def test_json_non_object_and_invalid_fields_rejected(self):
        code, out = run_main(gen, ["--json", "[1]"])
        self.assertEqual(code, 2)
        self.assertIn("invalid_json", out)
        code, out = run_main(gen, ["--json", '{"intf":"bt656","hact":1920,'
                                           '"vact":1080,"fps":"30"}'])
        self.assertEqual(code, 2)
        self.assertIn("fps", out)
        code, out = run_main(gen, ["--json", '{"intf":"bt656","hact":1920.5,'
                                           '"vact":1080,"fps":30}'])
        self.assertEqual(code, 2)
        self.assertIn("整数", out)

    def test_verify_mode(self):
        params = dict(valid_bt656_sdr(), u8DelaySel=0)
        code, out = run_main(gen, ["--verify", "--intf", "bt656", "--json",
                                   json.dumps(params)])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["problems"], [])
        self.assertAlmostEqual(payload["actual_fps"], 30.0)

        bad = dict(params, u32Pclk=33300)  # 不在离散档位表
        code, out = run_main(gen, ["--verify", "--intf", "bt656", "--json",
                                   json.dumps(bad)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["status"], "invalid")

        no_dbl = {k: v for k, v in params.items() if k != "bDlbClk"}
        code, out = run_main(gen, ["--verify", "--json", json.dumps(no_dbl)])
        self.assertEqual(code, 2)
        self.assertIn("bDlbClk", out)

        code, out = run_main(gen, ["--verify", "--intf", "bt656", "--fmt",
                                   "rgb565", "--json", json.dumps(params)])
        self.assertEqual(code, 2)
        self.assertIn("YUV422", out)

    def test_verify_ax615d_serial_srgb_fps_ceiling(self):
        # 回归：verify 曾漏传 fps，AX615D 串行 sRGB 640x480@45 被判 status ok
        over = serial_640x480(45)
        code, out = run_main(gen, ["--verify", "--intf", "srgb", "--fmt",
                                   "srgb888", "--chip", "AX615D", "--json",
                                   json.dumps(over)])
        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["code"], "capability")
        self.assertIn("640x480@30", out)
        self.assertAlmostEqual(payload["details"]["actual_fps"], 45.0)

        # 闸门按配置公式刷新率：--fps 等额外输入不得替代
        code, out = run_main(gen, ["--verify", "--intf", "srgb", "--fmt",
                                   "srgb888", "--chip", "AX615D", "--fps",
                                   "30", "--json", json.dumps(over)])
        self.assertEqual(code, 2)
        self.assertIn("capability", out)

        # 上限内（=30fps）通过
        code, out = run_main(gen, ["--verify", "--intf", "dpi", "--fmt",
                                   "srgb888", "--chip", "ax615d", "--json",
                                   json.dumps(serial_640x480(30))])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["problems"], [])
        self.assertAlmostEqual(payload["actual_fps"], 30.0)

    def test_verify_capability_gate_spares_legal_paths(self):
        # AX615Q 不受 AX615D 串行上限约束
        code, out = run_main(gen, ["--verify", "--intf", "srgb", "--fmt",
                                   "srgb888", "--chip", "AX615Q", "--json",
                                   json.dumps(serial_640x480(45))])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], "ok")
        # AX615D 串行 sRGB ×2（srgb565）640x480@30 合法
        code, out = run_main(gen, ["--verify", "--intf", "dpi", "--fmt",
                                   "srgb565", "--chip", "AX615D", "--json",
                                   json.dumps(serial_640x480_x2())])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
