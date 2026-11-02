#!/usr/bin/env python3
"""AX615 VO 知识库检索（可选 MCP 知识库工具）。

用法：
  kb_query.py --query "VO 黑屏 无输出" [--kb <id,id>] [--top-k 8] [--json]
  kb_query.py --list-kbs

Token 从 ~/.agents/xiaozhi.env 或环境变量 XIAOZHI_MCP_AUTH_TOKEN 读取，绝不回显。
MCP endpoint 从 XIAOZHI_MCP_URL 读取，不在脚本内置服务地址。
知识库 ID 由 --kb 或环境变量 XIAOZHI_KB_IDS（逗号分隔）提供，不在脚本内置。
退出码：0 检索成功且命中；1 检索执行成功但无结果（未命中）；
2 参数或 Token 等本地错误；3 网络/协议层失败（未执行成功）。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

MCP_URL_ENV = "XIAOZHI_MCP_URL"
KB_IDS_ENV = "XIAOZHI_KB_IDS"
TIMEOUT = 120
TOP_K_RANGE = (1, 50)


def load_mcp_url():
    """从环境变量读取 MCP endpoint，避免把部署地址写入发布包。"""
    url = os.environ.get(MCP_URL_ENV, "").strip()
    if not url:
        print(f"错误：未设置 {MCP_URL_ENV}（例如 https://<mcp-host>/mcp/）", file=sys.stderr)
        sys.exit(2)
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        print(f"错误：{MCP_URL_ENV} 不是有效 URL", file=sys.stderr)
        sys.exit(2)
    if (parsed.scheme != "https" or not parsed.netloc
            or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        print(f"错误：{MCP_URL_ENV} 必须是不含凭据、查询参数和片段的 HTTPS URL", file=sys.stderr)
        sys.exit(2)
    return url, f"{parsed.scheme}://{parsed.netloc}"


def load_token():
    """优先读 ~/.agents/xiaozhi.env（个人配置，权威），环境变量仅作兜底。

    shell 初始化环境可能残留占位符（如 replace-me），故文件优先。
    """
    env_file = os.path.expanduser("~/.agents/xiaozhi.env")
    try:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export "):]
                if line.startswith("XIAOZHI_MCP_AUTH_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if token and "replace" not in token.lower():
                        return token
        print(f"错误：{env_file} 中未找到有效的 XIAOZHI_MCP_AUTH_TOKEN"
              "（请按部署文档配置 Token）", file=sys.stderr)
    except OSError:
        pass  # 文件不可读时退回环境变量

    token = os.environ.get("XIAOZHI_MCP_AUTH_TOKEN", "")
    if token and "replace" not in token.lower():
        return token
    print("错误：无法获取 XIAOZHI_MCP_AUTH_TOKEN（文件与环境变量均无效）", file=sys.stderr)
    sys.exit(2)


def parse_kb_ids(raw):
    """逗号分隔的知识库 ID 列表：去空白、丢空项，非空校验；未传 --kb 时读取 XIAOZHI_KB_IDS。"""
    if raw is None:
        raw = os.environ.get(KB_IDS_ENV, "")
        if not raw.strip():
            raise ValueError(f"未指定知识库：请传 --kb 或设置 {KB_IDS_ENV}")
    ids = [item.strip() for item in raw.split(",")]
    ids = [item for item in ids if item]
    if not ids:
        raise ValueError("--kb 不能为空")
    return ids


class _SameOriginOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """只跟随同源重定向：Authorization 头重放会把 Bearer token 带给新 host。"""

    def __init__(self, origin):
        super().__init__()
        self._origin = origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(urllib.parse.urljoin(req.full_url, newurl))
        if f"{target.scheme}://{target.netloc}" != self._origin:
            raise urllib.error.HTTPError(
                req.full_url, code,
                f"拒绝跨源重定向（{self._origin} -> {target.scheme}://{target.netloc}）",
                headers, fp,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_request(token, mcp_url, method, params, req_id):
    body = json.dumps({
        "jsonrpc": "2.0", "id": req_id, "method": method, "params": params,
    }).encode("utf-8")
    return urllib.request.Request(
        mcp_url, data=body, method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )


def _decode_messages(raw):
    """兼容普通 JSON 与 SSE（text/event-stream）两种响应体。"""
    body = (raw or "").strip()
    if not body:
        return []
    if not body.startswith(("{", "[")):
        # SSE：取所有 data: 行的载荷（event:/id:/retry: 行忽略）
        body = "\n".join(
            line.strip()[5:].strip() for line in body.splitlines()
            if line.strip().startswith("data:")
        ).strip()
    if not body:
        return []
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else [payload]


def _extract_text(msg, req_id):
    if not isinstance(msg, dict):
        return None
    if msg.get("id") != req_id:
        return None
    if "error" in msg:
        print(f"错误：MCP 返回错误: {json.dumps(msg['error'], ensure_ascii=False)}",
              file=sys.stderr)
        sys.exit(3)
    result = msg.get("result")
    if not isinstance(result, dict):
        return None
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return None
    first = content[0]
    if not isinstance(first, dict):
        return None
    text = first.get("text")
    if not isinstance(text, str):
        return None
    is_error = result.get("isError") or first.get("type") == "error"
    return text, bool(is_error)


def mcp_call(token, mcp_url, mcp_origin, method, params, req_id=1):
    """调用 MCP 工具并返回文本结果；网络/协议层失败直接以退出码 3 结束。"""
    req = _build_request(token, mcp_url, method, params, req_id)
    opener = urllib.request.build_opener(_SameOriginOnlyRedirect(mcp_origin))
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"错误：HTTP {e.code} {e.reason}", file=sys.stderr)
        sys.exit(3)
    except urllib.error.URLError as e:
        print(f"错误：无法连接 MCP endpoint: {e.reason}", file=sys.stderr)
        sys.exit(3)
    except (TimeoutError, OSError) as e:
        print(f"错误：MCP 请求失败（超时或读取错误）: {e}", file=sys.stderr)
        sys.exit(3)

    for msg in _decode_messages(raw):
        extracted = _extract_text(msg, req_id)
        if extracted is None:
            continue
        text, is_error = extracted
        if is_error:
            print(f"错误：MCP 工具执行失败: {text}", file=sys.stderr)
            sys.exit(3)
        return text
    print("错误：响应中未找到有效结果", file=sys.stderr)
    sys.exit(3)


def has_hits(text):
    """判断检索结果文本是否含实际命中（用于退出码 0/1 与未命中提示）。"""
    value = (text or "").strip()
    if not value:
        return False
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return True  # 非 JSON 文本按有内容处理
    if isinstance(data, list):
        return bool(data)
    if isinstance(data, dict):
        for key in ("results", "items", "documents", "hits", "data"):
            if isinstance(data.get(key), list):
                return bool(data[key])
        if data.get("count") == 0:
            return False
        return bool(data)
    return bool(data)


def cmd_query(token, mcp_url, mcp_origin, args):
    result = mcp_call(token, mcp_url, mcp_origin, "tools/call", {
        "name": "rag-query_knowledge",
        "arguments": {
            "query": args.query,
            "knowledge_ids": args.kb,
            "top_k": args.top_k,
        },
    })
    if args.json:
        print(json.dumps({"query": args.query, "knowledge_ids": args.kb,
                          "top_k": args.top_k, "hits": has_hits(result),
                          "result": result}, ensure_ascii=False, indent=2))
    else:
        print(result)
    return 0 if has_hits(result) else 1


def cmd_list_kbs(token, mcp_url, mcp_origin):
    result = mcp_call(token, mcp_url, mcp_origin, "tools/call", {
        "name": "rag-list_knowledge_bases",
        "arguments": {},
    })
    print(result)
    return 0 if result.strip() else 1


def main():
    parser = argparse.ArgumentParser(description="AX615 VO 知识库检索（可选 MCP 知识库工具）")
    parser.add_argument("--query", help="检索问题/关键词（要具体：现象+模块+疑似 API）")
    parser.add_argument("--kb", help="知识库 ID，逗号分隔；未指定时读取环境变量 XIAOZHI_KB_IDS")
    parser.add_argument("--top-k", type=int, metavar="N",
                        help=f"返回片段数，范围 {TOP_K_RANGE[0]}-{TOP_K_RANGE[1]}，默认 8")
    parser.add_argument("--list-kbs", action="store_true", help="列出可见知识库")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（含 hits 字段）")
    args = parser.parse_args()

    if not args.list_kbs and not args.query:
        parser.error("需要 --query 或 --list-kbs")

    if args.top_k is None:
        args.top_k = 8
    if not TOP_K_RANGE[0] <= args.top_k <= TOP_K_RANGE[1]:
        parser.error(f"--top-k 必须在 {TOP_K_RANGE[0]}-{TOP_K_RANGE[1]} 之间")
    if args.list_kbs:
        args.kb = []
    else:
        try:
            args.kb = parse_kb_ids(args.kb)
        except ValueError as error:
            parser.error(str(error))

    token = load_token()
    mcp_url, mcp_origin = load_mcp_url()
    if args.list_kbs:
        return cmd_list_kbs(token, mcp_url, mcp_origin)
    return cmd_query(token, mcp_url, mcp_origin, args)


if __name__ == "__main__":
    sys.exit(main())
