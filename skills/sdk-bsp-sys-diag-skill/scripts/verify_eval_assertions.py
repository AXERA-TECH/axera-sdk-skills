#!/usr/bin/env python3
"""
verify_eval_assertions.py — 规范化断言评测脚本

功能：
1. 读取 evals/evals.json 中定义的评测用例及 assertion 规则。
2. 自动化检验指定输出报告（如 with_skill / without_skill 产物）是否满足各条断言要求。
3. 提供严格且具备语义容错的标准化正则/关键词匹配逻辑。
4. 输出结构化的评测报告（支持终端彩色高亮与 JSON 汇总输出），并返回规范的退出码（全部通过返回 0，未通过返回 1）。

用法：
    # 评测单个输出文件（针对指定 eval_id）：
    python3 scripts/verify_eval_assertions.py --eval-id 1 --file path/to/diagnosis.md

    # 批量评测 workspace 下的输出（如 iteration-2）：
    python3 scripts/verify_eval_assertions.py --workspace ../sdk-bsp-sys-diag-skill-workspace/iteration-2

    # 导出规范化 JSON 评测报告：
    python3 scripts/verify_eval_assertions.py --workspace ../sdk-bsp-sys-diag-skill-workspace/iteration-2 --json-out report.json
"""

import os
import sys
import json
import re
import argparse
from typing import Dict, List, Tuple, Any

# ANSI 颜色定义
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


class AssertionChecker:
    """定义针对各类断言的可编程核验逻辑，消除自然语言模糊性。"""

    @staticmethod
    def check_eval_1(text: str) -> List[Tuple[str, bool, str]]:
        """
        Eval 1: av-exit-hang-getframe-then-memfree
        """
        results = []

        # 1. 抽出锚点 phyaddr=0x46620000
        cond1 = bool(re.search(r'0x46620000', text, re.IGNORECASE))
        results.append((
            "抽出锚点 phyaddr=0x46620000",
            cond1,
            "未在输出中找到物理地址 0x46620000" if not cond1 else "成功匹配 0x46620000"
        ))

        # 2. 指出用 /proc/ax_proc/mem_cmm_info 的 name=token 反查该地址 owner
        cond2 = bool(
            re.search(r'mem_cmm_info', text, re.IGNORECASE) and
            re.search(r'(name|token|owner|属主)', text, re.IGNORECASE)
        )
        results.append((
            "指出用 /proc/ax_proc/mem_cmm_info 的 name=token 反查该地址 owner",
            cond2,
            "缺少 mem_cmm_info 或 owner/name/token 反查指引" if not cond2 else "包含 proc 反查机制"
        ))

        # 3. 根因方向为取帧后误用 AX_SYS_MemFree / 跨所有权释放 CMM(与标杆案例同型)
        cond3 = bool(
            re.search(r'AX_SYS_MemFree', text) and
            re.search(r'(帧|IVPS|所有权|标杆|跨所有权|多余|误用)', text)
        )
        results.append((
            "根因方向为取帧后误用 AX_SYS_MemFree / 跨所有权释放 CMM(与标杆案例同型)",
            cond3,
            "缺少 AX_SYS_MemFree 误用或跨所有权释放说明" if not cond3 else "根因方向明确指出 MemFree 误用"
        ))

        # 4. 包含证据强度分级(强/中/弱)且诚实区分已证实与推断
        cond4 = bool(
            re.search(r'(强|中|弱)', text) and
            re.search(r'(证据|已证实|推断|假设)', text)
        )
        results.append((
            "包含证据强度分级(强/中/弱)且诚实区分已证实与推断",
            cond4,
            "缺少强/中/弱证据分级或证实/推断区分" if not cond4 else "包含证据分级与确信度评估"
        ))

        # 5. 抓日志建议 ramoops/pstore + axsyslog/logctl,不建议 loglevel=8 或通用 dmesg/var-log-syslog
        cond5_pos = bool(
            re.search(r'(ramoops|pstore)', text, re.IGNORECASE) or
            re.search(r'(axsyslog|logctl)', text, re.IGNORECASE)
        )
        cond5_neg = bool(
            re.search(r'不(要|建议|套用).*dmesg', text) or
            re.search(r'官方.*(axsyslog|ramoops)', text) or
            re.search(r'挂死.*(ramoops|pstore|栈)', text)
        )
        cond5 = cond5_pos or cond5_neg
        results.append((
            "抓日志建议 ramoops/pstore + axsyslog/logctl,不建议 loglevel=8 或通用 dmesg/var-log-syslog",
            cond5,
            "未提及官方抓取机制 ramoops/pstore/axsyslog" if not cond5 else "具备专用日志捕获推荐"
        ))

        # 6. 指出 backtrace 被截断需按官方补完整栈
        cond6 = bool(
            re.search(r'(backtrace|栈|调用栈)', text, re.IGNORECASE) and
            re.search(r'(截断|丢失|无|不可用|补全|抓完整|热重启)', text)
        )
        results.append((
            "指出 backtrace 被截断需按官方补完整栈",
            cond6,
            "未指出 backtrace 缺失/截断或未给补全指引" if not cond6 else "已指出堆栈缺失与补全方案"
        ))

        return results

    @staticmethod
    def check_eval_2(text: str) -> List[Tuple[str, bool, str]]:
        """
        Eval 2: no-log-but-callseq-getframe-then-memfree
        """
        results = []

        # 1. 判定调用序列末尾的 AX_SYS_MemFree 是错误的(违反配对铁律)
        cond1 = bool(
            re.search(r'AX_SYS_MemFree', text) and
            re.search(r'(错|多余|不应|删掉|违背|配对)', text)
        )
        results.append((
            "判定调用序列末尾的 AX_SYS_MemFree 是错误的(违反配对铁律)",
            cond1,
            "未判定末尾 MemFree 错误" if not cond1 else "明确判定末尾 MemFree 错误"
        ))

        # 2. 说明帧归 IVPS pool、ReleaseChnFrame 已归还、MemFree 只配自己 AX_SYS_MemAlloc
        cond2 = bool(
            re.search(r'(IVPS|pool)', text, re.IGNORECASE) and
            re.search(r'ReleaseChnFrame', text) and
            re.search(r'MemAlloc', text)
        )
        results.append((
            "说明帧归 IVPS pool、ReleaseChnFrame 已归还、MemFree 只配自己 AX_SYS_MemAlloc",
            cond2,
            "未讲清帧归属 pool、Release 已归还及 MemAlloc 配对" if not cond2 else "讲清所有权及配对原则"
        ))

        # 3. 因无日志给出官方抓取指引(axsyslog/ramoops/mem_cmm_info)而非假装已看到日志
        cond3 = bool(
            re.search(r'(没(有)?日志|无日志|手上暂(时)?没)', text) and
            re.search(r'(axsyslog|mem_cmm_info|ramoops|log-capture|抓取)', text, re.IGNORECASE)
        )
        results.append((
            "因无日志给出官方抓取指引(axsyslog/ramoops/mem_cmm_info)而非假装已看到日志",
            cond3,
            "未识别无日志或未给抓取指引" if not cond3 else "识别无日志并给出抓取指引"
        ))

        # 4. 给出修复:删掉末尾 MemFree,需 CPU 访问时 Mmap/Munmap 成对保留
        cond4 = bool(
            re.search(r'(删(除|掉)?.*MemFree|去掉.*MemFree)', text, re.IGNORECASE) and
            re.search(r'M(un)?map', text)
        )
        results.append((
            "给出修复:删掉末尾 MemFree,需 CPU 访问时 Mmap/Munmap 成对保留",
            cond4,
            "修复建议未提及删掉 MemFree 或 Mmap/Munmap 保留" if not cond4 else "给出准确修复方案"
        ))

        return results

    @staticmethod
    def check_eval_3(text: str) -> List[Tuple[str, bool, str]]:
        """
        Eval 3: double-free-own-buffer-npu
        """
        results = []

        # 1. 抽出锚点 phyaddr=0x48ab0000
        cond1 = bool(re.search(r'0x48ab0000', text, re.IGNORECASE))
        results.append((
            "抽出锚点 phyaddr=0x48ab0000",
            cond1,
            "未找到锚点地址 0x48ab0000" if not cond1 else "成功提取锚点 0x48ab0000"
        ))

        # 2. 判为对自己 buffer 的重复释放(double free)这一支,而非取帧误放
        cond2 = bool(
            re.search(r'(重复释放|double[- ]?free)', text, re.IGNORECASE) and
            re.search(r'(自己|自身|npu_in|非取帧)', text)
        )
        results.append((
            "判为对自己 buffer 的重复释放(double free)这一支,而非取帧误放",
            cond2,
            "未指明是对自身 buffer 的重复释放" if not cond2 else "准确命中重复释放分支"
        ))

        # 3. 指出 owner 反查会指向应用自己(token=npu_in)
        cond3 = bool(
            re.search(r'npu_in', text) and
            re.search(r'(token|owner|属主|自己)', text)
        )
        results.append((
            "指出 owner 反查会指向应用自己(token=npu_in)",
            cond3,
            "未指出 token=npu_in 归属应用自己" if not cond3 else "明确 owner 指向应用自身"
        ))

        # 4. 解释 ABA(释放后地址可能被复用,第二次 free 误伤他人)
        cond4 = bool(
            re.search(r'ABA', text, re.IGNORECASE) or
            (re.search(r'(复用|重新分配)', text) and re.search(r'(误伤|踩|他人|别人)', text))
        )
        results.append((
            "解释 ABA(释放后地址可能被复用,第二次 free 误伤他人)",
            cond4,
            "未解释 ABA 或地址复用导致的次生破坏" if not cond4 else "清晰解释 ABA 复用破坏机制"
        ))

        # 5. 用崩溃栈(__ax_cmm_block_release/ax_cmm_free)佐证崩在 CMM 释放路径
        cond5 = bool(
            re.search(r'(__ax_cmm_block_release|ax_cmm_free)', text)
        )
        results.append((
            "用崩溃栈(__ax_cmm_block_release/ax_cmm_free)佐证崩在 CMM 释放路径",
            cond5,
            "未引用关键崩溃栈函数" if not cond5 else "崩溃栈引用确切"
        ))

        # 6. 给出修复:释放即清零 + 单出口只释放一次
        cond6 = bool(
            re.search(r'(清零|NULL|0)', text) and
            re.search(r'(单出口|一次|避免重复|标志位)', text)
        )
        results.append((
            "给出修复:释放即清零 + 单出口只释放一次",
            cond6,
            "修复缺少置空/单出口等防重复规范" if not cond6 else "给出规范防范措施"
        ))

        return results

    @staticmethod
    def check_eval_4(text: str) -> List[Tuple[str, bool, str]]:
        """
        Eval 4: negative-venc-lowfps-not-cmm
        """
        results = []

        # 1. 判定现象不符合 CMM 错误释放的识别特征(非退出/无硬挂/日志无 ax_cmm_free/Block not found/pool 关键字)
        cond1 = bool(
            re.search(r'不(属于|符合|匹配|是)', text) and
            re.search(r'(CMM|错误释放|内存释放)', text)
        )
        results.append((
            "判定现象不符合 CMM 错误释放的识别特征",
            cond1,
            "未明确判定不符合 CMM 错误释放特征" if not cond1 else "明确识别非 CMM 错误释放"
        ))

        # 2. 未硬套 MemFree 或内存释放根因
        # 只要没有直接下结论说根因是 MemFree 导致崩溃即可
        cond2 = not bool(re.search(r'(根因(是|为)|结论[:：]).*调了.*MemFree', text))
        results.append((
            "未硬套 MemFree 或内存释放根因",
            cond2,
            "错误地将根因强加于 MemFree" if not cond2 else "克制合理，未过度归因"
        ))

        # 3. 如实说明本诊断路径(CMM 错误释放)不适用
        cond3 = bool(
            re.search(r'(不适用|退出阶段|本技能|路径)', text) and
            re.search(r'(克制|不套用|非本路径|其他方向|无需套用)', text)
        ) or cond1
        results.append((
            "如实说明本诊断路径(CMM 错误释放)不适用",
            cond3,
            "未说明路径不适用" if not cond3 else "如实说明该路径不适用"
        ))

        # 4. 建议转 VENC 码控/带宽/参考帧或 FRC 等方向
        cond4 = bool(
            re.search(r'(码控|QP|带宽|参考帧|FRC|丢帧|帧率)', text, re.IGNORECASE)
        )
        results.append((
            "建议转 VENC 码控/带宽/参考帧或 FRC 等方向",
            cond4,
            "未给出正确的 VENC 码控/带宽排查方向" if not cond4 else "给出准确的 VENC 业务排查方向"
        ))

        return results

    @staticmethod
    def check_eval_5(text: str) -> List[Tuple[str, bool, str]]:
        """
        Eval 5: cmm-partition-nomem-quick-diag
        """
        results = []

        # 1. 明确定性为 CMM 内存不足(NOMEM)
        cond1 = bool(
            re.search(r'(CMM.*内存不足|NOMEM|内存不足.*CMM|物理内存.*不足)', text, re.IGNORECASE)
        )
        results.append((
            "明确定性为 CMM 内存不足(NOMEM)",
            cond1,
            "未明确定性为 CMM 内存不足/NOMEM" if not cond1 else "准确判定 CMM 内存不足 (NOMEM)"
        ))

        # 2. 指出受影响的分区为 VIN0 且剩余容量不足以满足申请
        cond2 = bool(
            re.search(r'VIN0', text) and
            (re.search(r'(56|84480|容量|空间|不足|申请)', text))
        )
        results.append((
            "指出受影响的分区为 VIN0 且剩余容量不足以满足申请",
            cond2,
            "未指明 VIN0 分区或未提及容量不足以满足申请" if not cond2 else "明确指出 VIN0 分区容量不足"
        ))

        # 3. 引用关键日志特征(CMM partition memory isn't enough 或 0x80110180)
        cond3 = bool(
            re.search(r"CMM partition memory isn't enough", text, re.IGNORECASE) or
            re.search(r'0x80110180', text, re.IGNORECASE) or
            re.search(r'ax_block_alloc.*failed', text)
        )
        results.append((
            "引用关键日志特征(CMM partition memory isn't enough 或 0x80110180)",
            cond3,
            "缺少关键日志错误信息引用" if not cond3 else "具备关键报错日志与错误码引用"
        ))

        # 4. 未硬套为 CMM 错误释放或野指针踩内存
        cond4 = not bool(re.search(r'(根因(是|为)|结论[:：]).*(错误释放|野指针|双重释放|MemFree.*误用)', text))
        results.append((
            "未硬套为 CMM 错误释放或野指针踩内存",
            cond4,
            "错误地套用了 CMM 错误释放/野指针结论" if not cond4 else "克制合理，未过度归因于悬垂释放"
        ))

        # 5. 给出明确的转派或配置调整建议
        cond5 = bool(
            re.search(r'(转派|配置|加大|分区|调大|脚本|cmm\.sh|规划)', text)
        )
        results.append((
            "给出明确的转派或配置调整建议",
            cond5,
            "缺少转派或配置调整建议" if not cond5 else "给出明确的转派或参数/分区调整建议"
        ))

        return results


CHECKER_MAP = {
    1: AssertionChecker.check_eval_1,
    2: AssertionChecker.check_eval_2,
    3: AssertionChecker.check_eval_3,
    4: AssertionChecker.check_eval_4,
    5: AssertionChecker.check_eval_5,
}


def evaluate_single_file(eval_id: int, file_path: str) -> Dict[str, Any]:
    if not os.path.isfile(file_path):
        return {
            "eval_id": eval_id,
            "file": file_path,
            "error": f"File not found: {file_path}",
            "passed": False,
            "assertions": []
        }

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    checker = CHECKER_MAP.get(eval_id)
    if not checker:
        return {
            "eval_id": eval_id,
            "file": file_path,
            "error": f"No checker defined for eval_id: {eval_id}",
            "passed": False,
            "assertions": []
        }

    raw_results = checker(content)
    all_pass = all(item[1] for item in raw_results)

    assertions_data = [
        {"name": name, "passed": passed, "detail": detail}
        for name, passed, detail in raw_results
    ]

    return {
        "eval_id": eval_id,
        "file": file_path,
        "passed": all_pass,
        "assertions": assertions_data
    }


def find_workspace_cases(workspace: str) -> List[Tuple[int, str, str]]:
    """扫描 workspace 目录寻找对应的输出文件 (eval_id, run_type, file_path)"""
    eval_id_map = {
        "av-exit-hang": 1,
        "no-log-callseq": 2,
        "double-free-npu": 3,
        "venc-lowfps-negative": 4
    }

    cases = []
    for root, dirs, files in os.walk(workspace):
        for f in files:
            if f.endswith(".md"):
                full_path = os.path.join(root, f)
                # 判断属于哪个 case
                for key, eid in eval_id_map.items():
                    if key in full_path:
                        run_type = "with_skill" if "with_skill" in full_path else (
                            "without_skill" if "without_skill" in full_path else "unknown"
                        )
                        cases.append((eid, run_type, full_path))
                        break
    return sorted(cases, key=lambda x: (x[0], x[1]))


def main():
    parser = argparse.ArgumentParser(description="规范化断言评测脚本")
    parser.add_argument("--evals-json", default=None, help="evals.json 路径（可选）")
    parser.add_argument("--eval-id", type=int, choices=[1, 2, 3, 4, 5], help="针对单个用例执行断言 (1-5)")
    parser.add_argument("--file", help="待核验的 Markdown 报告文件路径")
    parser.add_argument("--workspace", help="待扫描评测的工作空间目录（如 iteration-2 目录）")
    parser.add_argument("--json-out", help="导出 JSON 汇总报告路径")

    args = parser.parse_args()

    # 确定默认根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, ".."))

    reports = []
    total_assertions = 0
    passed_assertions = 0

    if args.file:
        if not args.eval_id:
            print(f"{RED}错误：指定 --file 时必须同时指定 --eval-id{RESET}", file=sys.stderr)
            sys.exit(2)
        res = evaluate_single_file(args.eval_id, args.file)
        reports.append((f"Eval-{args.eval_id}", res))
    elif args.workspace:
        cases = find_workspace_cases(args.workspace)
        if not cases:
            print(f"{YELLOW}在工作空间 {args.workspace} 中未找到匹配的评测输出文件{RESET}")
            sys.exit(1)
        for eid, rtype, fpath in cases:
            res = evaluate_single_file(eid, fpath)
            reports.append((f"Eval-{eid} [{rtype}]", res))
    else:
        # 默认模式：自动寻找同级或上级的 workspace
        default_ws = os.path.abspath(os.path.join(repo_root, "..", "sdk-bsp-sys-diag-skill-workspace", "iteration-2"))
        if os.path.exists(default_ws):
            print(f"{CYAN}未指定参数，默认扫描: {default_ws}{RESET}\n")
            cases = find_workspace_cases(default_ws)
            for eid, rtype, fpath in cases:
                res = evaluate_single_file(eid, fpath)
                reports.append((f"Eval-{eid} [{rtype}]", res))
        else:
            parser.print_help()
            sys.exit(1)

    # 打印终端规范化报告
    print(f"\n{BOLD}{'='*30} 规范化断言评测结果 {'='*30}{RESET}\n")

    all_cases_passed = True

    for label, rep in reports:
        status_color = GREEN if rep["passed"] else RED
        status_str = f"{status_color}{'[PASS]' if rep['passed'] else '[FAIL]'}{RESET}"
        print(f"{BOLD}{label:<35}{RESET} {status_str} -> {rep['file']}")

        if "error" in rep and rep["error"]:
            print(f"  {RED}Error: {rep['error']}{RESET}")
            all_cases_passed = False
            continue

        if not rep["passed"]:
            all_cases_passed = False

        for a in rep["assertions"]:
            total_assertions += 1
            if a["passed"]:
                passed_assertions += 1
                icon = f"{GREEN}✓{RESET}"
            else:
                icon = f"{RED}✗{RESET}"
            print(f"    [{icon}] {a['name']:<65} ({a['detail']})")
        print()

    # 汇总统计
    print(f"{BOLD}{'='*78}{RESET}")
    pass_rate = (passed_assertions / total_assertions * 100) if total_assertions > 0 else 0
    print(f"断言通过率: {passed_assertions}/{total_assertions} ({pass_rate:.1f}%)")

    # 导出 JSON
    if args.json_out:
        summary_payload = {
            "summary": {
                "total_assertions": total_assertions,
                "passed_assertions": passed_assertions,
                "pass_rate_percent": round(pass_rate, 2),
                "all_passed": all_cases_passed
            },
            "cases": reports
        }
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(summary_payload, f, indent=2, ensure_ascii=False)
        print(f"JSON 报告已保存至: {args.json_out}")

    sys.exit(0 if all_cases_passed else 1)


if __name__ == "__main__":
    main()
