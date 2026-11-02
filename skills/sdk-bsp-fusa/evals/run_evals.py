#!/usr/bin/env python3
"""sdk-bsp-fusa 验收用例确定性校验器。

只做能被机械判定的事实检查（结构、隔离、编号纪律、跨平台串味），
不判语义对错——语义判定与盲测见 evals/README.md 与 SKILL.md 的「验收自检」。

用法：
    python3 run_evals.py                    # 跑全部检查
    python3 run_evals.py --list FUSA-001    # 预检单个 Case，只输出可读文件清单
    python3 run_evals.py --case FUSA-001    # 只做该 Case 的结构与隔离检查
"""
import argparse
import json
import os
import re
import sys

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(EVALS_DIR)
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
REFERENCES_DIR = os.path.join(SKILL_DIR, "references")

SKILL_NAME = "sdk-bsp-fusa"
CASE_ID_RE = re.compile(r"^FUSA-\d{3}$")

# 答案正文（必须输出的字段）里不允许出现的另一平台特征。
LINUX_ANSWER_FORBIDDEN = ["/proc/ax_diag", "QNX_V", "pidin ar", "hogs -n"]
QNX_ANSWER_FORBIDDEN = ["/sys/devices/platform/axdiag", "/sys/class/fusa", ".config", "defconfig"]

# Linux FAQ 编号不补零，QNX 补零；Linux 答案里出现补零编号即串味。
PADDED_FAQ_RE = re.compile(r"FAQ-0\d")

ANSWER_TEXT_FIELDS = ("root_cause", "required_concepts", "required_actions")
CASE_REQUIRED_KEYS = ("schema_version", "id", "title", "category", "source",
                      "analyzer", "platform", "input", "oracle", "separation")
ORACLE_REQUIRED_KEYS = ("root_cause", "required_concepts", "forbidden_conclusions",
                        "required_actions", "forbidden_actions", "evidence_signatures",
                        "expected_confidence", "evaluation_notes")

results = []  # (ok, label, detail)


def check(ok, label, detail=""):
    results.append((bool(ok), label, detail))
    return bool(ok)


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def case_dirs():
    if not os.path.isdir(EVALS_DIR):
        return []
    return sorted(name for name in os.listdir(EVALS_DIR)
                  if CASE_ID_RE.match(name) and os.path.isdir(os.path.join(EVALS_DIR, name)))


def parse_list_block(lines, key):
    """抓取 `key:` 下面同缩进的 `- item` 列表；遇同级新键或缩进回退即停。"""
    items = []
    key_indent = None
    collecting = False
    for line in lines:
        stripped = line.strip()
        if not collecting:
            match = re.match(r"^(\s*)%s:\s*$" % re.escape(key), line)
            if match:
                key_indent = len(match.group(1))
                collecting = True
            continue
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= key_indent:
            break
        item = re.match(r"^-\s*(\S+)\s*$", stripped)
        if item:
            items.append(item.group(1))
    return items


def parse_text_list(lines, key):
    """抓取 `key:` 下面同缩进的 `- 自由文本` 列表（允许含空格与冒号）。"""
    items = []
    key_indent = None
    collecting = False
    for line in lines:
        stripped = line.strip()
        if not collecting:
            match = re.match(r"^(\s*)%s:\s*$" % re.escape(key), line)
            if match:
                key_indent = len(match.group(1))
                collecting = True
            continue
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= key_indent:
            break
        item = re.match(r"^-\s*(.+?)\s*$", stripped)
        if item:
            items.append(item.group(1))
    return items


def parse_evidence_files(lines):
    """抓取 evidence_signatures 下的文件名键（形如 `  input/xxx.log:`）。"""
    files, collecting, base_indent = [], False, None
    for line in lines:
        if not collecting:
            match = re.match(r"^(\s*)evidence_signatures:\s*$", line)
            if match:
                collecting, base_indent = True, len(match.group(1))
            continue
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent:
            break
        match = re.match(r"^\s*([^\s#][^:]*):\s*$", line)
        if match:
            files.append(match.group(1).strip())
    return files


def lint_cross_platform(case_id, answer_text, forbidden_tokens, padded_faq=False):
    for token in forbidden_tokens:
        if token in answer_text:
            check(False, "%s 跨平台串味" % case_id, "答案正文出现另一平台特征 %r" % token)
            return
    if padded_faq and PADDED_FAQ_RE.search(answer_text):
        check(False, "%s FAQ 编号纪律" % case_id,
              "Linux 答案里出现补零编号 %s" % PADDED_FAQ_RE.search(answer_text).group(0))
        return
    check(True, "%s 无跨平台串味" % case_id)

def check_skill_package():
    if not os.path.isfile(SKILL_MD):
        return check(False, "SKILL.md", "SKILL.md 不存在")
    text = read(SKILL_MD)
    check(re.search(r"^name:\s*%s\s*$" % re.escape(SKILL_NAME), text, re.M) is not None,
          "SKILL.md 运行时名", "前置元数据 name 必须是 %s" % SKILL_NAME)
    check(re.search(r"^activation:\s*explicit\s*$", text, re.M) is not None,
          "SKILL.md 激活方式", "activation 必须是 explicit")
    match = re.search(r"^description:\s*(.+)$", text, re.M)
    check(match is not None and len(match.group(1).strip()) > 80,
          "SKILL.md description", "description 缺失或过短，会影响 skill 被发现")

    referenced = set(name for name in re.findall(r"references/([^\s`|)]+\.md)", text)
                     if not re.search(r"[<>*]", name))
    missing = sorted(name for name in referenced
                     if not os.path.isfile(os.path.join(REFERENCES_DIR, name)))
    check(not missing, "SKILL.md 参考文件完整性",
          "SKILL.md 引用但磁盘不存在：%s" % ", ".join(missing) if missing else "")

    check("evals/" in text and "验收自检" in text, "SKILL.md 验收入口",
          "SKILL.md 必须包含「验收自检」章节并指向 evals/")


def check_evals_json():
    path = os.path.join(EVALS_DIR, "evals.json")
    if not os.path.isfile(path):
        return check(False, "evals.json", "文件不存在")
    try:
        data = json.loads(read(path))
    except ValueError as exc:
        return check(False, "evals.json 可解析", str(exc))
    check(data.get("skill_name") == SKILL_NAME, "evals.json skill_name",
          "应为 %s" % SKILL_NAME)
    evals = data.get("evals") or []
    check(len(evals) >= 3, "evals.json 条目数", "至少要 3 条，当前 %d" % len(evals))
    bad = []
    for item in evals:
        for key in ("id", "name", "prompt", "expected_output", "expectations"):
            if not item.get(key):
                bad.append("%s 缺 %s" % (item.get("name", "?"), key))
        if not isinstance(item.get("expectations"), list):
            bad.append("%s 的 expectations 必须是数组" % item.get("name", "?"))
    check(not bad, "evals.json 字段完整性", "; ".join(bad))


def check_trigger_evals():
    path = os.path.join(EVALS_DIR, "trigger-evals.json")
    if not os.path.isfile(path):
        return check(False, "trigger-evals.json", "文件不存在")
    try:
        entries = json.loads(read(path))
    except ValueError as exc:
        return check(False, "trigger-evals.json 可解析", str(exc))
    bad = [str(idx) for idx, item in enumerate(entries)
           if not item.get("query") or "should_trigger" not in item or not item.get("notes")]
    check(not bad, "trigger-evals.json 字段完整性",
          "条目 %s 缺 query/should_trigger/notes" % ", ".join(bad) if bad else "")
    yes = [item for item in entries if item.get("should_trigger") is True]
    no = [item for item in entries if item.get("should_trigger") is False]
    check(len(yes) >= 3 and len(no) >= 3, "trigger-evals 正负样本",
          "需至少各 3 条，当前 正 %d / 负 %d" % (len(yes), len(no)))
def check_case(case_id):
    case_dir = os.path.join(EVALS_DIR, case_id)
    input_dir = os.path.join(case_dir, "input")
    answer_dir = os.path.join(case_dir, "answer")
    case_yaml = os.path.join(answer_dir, "case.yaml")
    oracle_yaml = os.path.join(answer_dir, "oracle.yaml")

    if not os.path.isdir(input_dir) or not os.listdir(input_dir):
        return check(False, "%s input/" % case_id, "input/ 缺失或为空")
    if not os.path.isfile(case_yaml) or not os.path.isfile(oracle_yaml):
        return check(False, "%s answer/" % case_id, "缺 case.yaml 或 oracle.yaml")

    case_text = read(case_yaml)
    lines = case_text.splitlines()
    missing = [key for key in CASE_REQUIRED_KEYS
               if not re.search(r"^%s:" % re.escape(key), case_text, re.M)]
    if not check(not missing, "%s case.yaml 必填键" % case_id,
                 "缺 %s" % ", ".join(missing) if missing else ""):
        return

    visible = parse_list_block(lines, "analyzer_visible")
    evaluator = parse_list_block(lines, "evaluator_only")
    actual = set()
    for dirpath, _dirnames, filenames in os.walk(input_dir):
        for name in filenames:
            actual.add("input/" + os.path.relpath(os.path.join(dirpath, name), input_dir))

    check(os.path.isfile(os.path.join(input_dir, "prompt.md")),
          "%s 客户输入" % case_id, "input/ 必须含 prompt.md")
    check(set(visible) == actual, "%s 隔离声明与 input/ 一致" % case_id,
          "声明 %s / 实际 %s" % (sorted(visible), sorted(actual)))
    check(all(path.startswith("input/") for path in visible),
          "%s analyzer_visible 前缀" % case_id, "只能列 input/ 下的文件")
    check(all(os.path.isfile(os.path.join(case_dir, path)) for path in visible),
          "%s analyzer_visible 文件存在" % case_id)
    for need in ("answer/case.yaml", "answer/oracle.yaml"):
        check(need in evaluator, "%s evaluator_only 含 %s" % (case_id, need))
    check(all(path.startswith("answer/") for path in evaluator),
          "%s evaluator_only 前缀" % case_id, "只能列 answer/ 下的文件")
    check(not set(visible) & set(evaluator), "%s 两个区不重叠" % case_id,
          "同一文件不能既可见又是答案")

    oracle_text = read(oracle_yaml)
    oracle_lines = oracle_text.splitlines()
    missing = [key for key in ORACLE_REQUIRED_KEYS
               if not re.search(r"^%s:" % re.escape(key), oracle_text, re.M)]
    check(not missing, "%s oracle.yaml 必填键" % case_id,
          "缺 %s" % ", ".join(missing) if missing else "")
    id_match = re.search(r"^id:\s*(\S+)\s*$", case_text, re.M)
    check(id_match is not None and id_match.group(1) == case_id,
          "%s case.yaml id" % case_id, "case.yaml 的 id 必须等于目录名")
    case_pl = re.search(r"^platform:\s*(\S+)\s*$", case_text, re.M)
    oracle_pl = re.search(r"^platform:\s*(\S+)\s*$", oracle_text, re.M)
    check(case_pl is not None and oracle_pl is not None
          and case_pl.group(1) == oracle_pl.group(1),
          "%s 平台一致性" % case_id,
          "case.yaml 与 oracle.yaml 的 platform 必须一致")
    for key in ("required_concepts", "required_actions", "forbidden_conclusions",
                "forbidden_actions"):
        check(len(parse_text_list(oracle_lines, key)) > 0,
              "%s oracle.%s" % (case_id, key), "不能为空")
    for key in ("recommended_concepts", "recommended_actions"):
        if re.search(r"^%s:" % key, oracle_text, re.M):
            check(len(parse_text_list(oracle_lines, key)) > 0,
                  "%s oracle.%s" % (case_id, key), "声明了该可选字段就必须有条目")
        else:
            check(True, "%s oracle.%s" % (case_id, key), "未使用（可选字段）")
    evidence = parse_evidence_files(oracle_lines)
    check(evidence and all(path in visible for path in evidence),
          "%s 证据可溯源" % case_id,
          "evidence_signatures 必须全部落在 analyzer_visible 内：%s" % evidence)

    fields = []
    root = re.search(r"^root_cause:\s*(.+)$", oracle_text, re.M)
    if root:
        fields.append(root.group(1))
    for key in ANSWER_TEXT_FIELDS:
        fields.extend(parse_text_list(oracle_lines, key))
    answer_text = "\n".join(fields)
    if re.search(r"allow_cross_platform:\s*true", case_text):
        check(True, "%s 跨平台串味检查" % case_id, "该 Case 显式豁免（平台纠偏场景）")
    elif re.search(r"^platform:\s*linux\s*$", case_text, re.M):
        lint_cross_platform(case_id, answer_text, LINUX_ANSWER_FORBIDDEN, padded_faq=True)
    elif re.search(r"^platform:\s*qnx\s*$", case_text, re.M):
        lint_cross_platform(case_id, answer_text, QNX_ANSWER_FORBIDDEN)
    else:
        check(True, "%s 跨平台串味检查" % case_id, "平台未定（platform 非 linux/qnx），跳过")


def precheck(case_id, cases):
    """盲测预检：只输出可读输入清单，不打印 answer/ 下任何路径或内容。"""
    if case_id not in cases:
        print("[ERROR] 未知 Case：%s（可用：%s）" % (case_id, ", ".join(cases) or "无"))
        return 2
    case_dir = os.path.join(EVALS_DIR, case_id)
    input_dir = os.path.join(case_dir, "input")
    case_yaml = os.path.join(case_dir, "answer", "case.yaml")
    if not os.path.isfile(case_yaml):
        print("[ERROR] %s：缺少 answer/case.yaml，Case 结构无效" % case_id)
        return 2
    visible = []
    for dirpath, _dirnames, filenames in os.walk(input_dir):
        for name in filenames:
            visible.append("input/" + os.path.relpath(os.path.join(dirpath, name), input_dir))
    declared = parse_list_block(read(case_yaml).splitlines(), "analyzer_visible")
    if sorted(visible) != sorted(declared):
        print("[ERROR] %s：input/ 实际文件与 analyzer_visible 声明不一致" % case_id)
        print("  实际：%s" % sorted(visible))
        print("  声明：%s" % sorted(declared))
        return 2
    print("Case: %s" % case_id)
    print("analyzer_visible（分析阶段唯一可读）：")
    for path in sorted(visible):
        print("  - %s" % path)
    print("评分阶段的答案文件：1 个（读取前必须先冻结 analyzer_result）")
    return 0


def main():
    parser = argparse.ArgumentParser(description="sdk-bsp-fusa 验收用例校验器")
    parser.add_argument("--list", dest="list_case", metavar="CASE",
                        help="预检单个 Case，只输出可读文件清单")
    parser.add_argument("--case", dest="only_case", metavar="CASE",
                        help="只校验指定 Case")
    args = parser.parse_args()

    cases = case_dirs()
    if args.list_case:
        return precheck(args.list_case, cases)

    if not cases:
        check(False, "Case 集合", "evals/ 下没有任何 FUSA-0NN 目录")
    check_skill_package()
    check_evals_json()
    check_trigger_evals()
    for case_id in cases:
        if args.only_case and case_id != args.only_case:
            continue
        check_case(case_id)
    if args.only_case and args.only_case not in cases:
        check(False, "Case 集合", "未知 Case：%s" % args.only_case)

    passed = sum(1 for ok, _label, _detail in results if ok)
    total = len(results)
    for ok, label, detail in results:
        if ok:
            print("[PASS] %s" % label)
        else:
            print("[FAIL] %s -> %s" % (label, detail))
    print("\nResult: %d/%d passed (Pass Rate: %.1f%%)"
          % (passed, total, passed * 100.0 / total if total else 0.0))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

