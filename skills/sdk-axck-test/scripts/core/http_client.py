#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/http_client.py
L0: 传输与通信核心层 (Transport & Client Core)
封装 HTTP 请求、连接池复用、超时重试 (指数退避)、毫秒级耗时监控及统一响应解析。
"""

import time
import json
import http.client
import urllib.parse
from typing import Any, Dict, Optional
from dataclasses import dataclass

@dataclass
class AxckResponse:
    success: bool
    status_code: int
    code: int                      # CGI 业务返回码 (0 表示成功)
    msg: str                       # 响应提示信息
    data: Any                      # 解析后的业务数据 payload
    latency_ms: float              # 毫秒级网络调用耗时
    raw_json: Optional[Dict[str, Any]] = None
    retries_attempted: int = 0
    error: Optional[str] = None

class AxckHttpClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 80,
        timeout: float = 5.0,
        max_retries: int = 0,
        retry_delay: float = 0.1,
        backoff_factor: float = 2.0,
        http10_bypass: bool = True
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.http10_bypass = http10_bypass
        self.base_url = f"http://{host}:{port}"

    def request(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> AxckResponse:
        """
        发起 HTTP 请求并自动计算时延、重试与统一响应建模。
        支持 HTTP/1.0 skip_host 安全穿透模式（避免公司路由 DPI 拦截 302）。
        """
        req_timeout = timeout if timeout is not None else self.timeout

        # 格式化 URL 路径与参数
        query_string = ""
        if params:
            query_string = "?" + urllib.parse.urlencode(params)
        full_path = f"{path}{query_string}"

        last_error = None
        current_delay = self.retry_delay

        for attempt in range(self.max_retries + 1):
            t0 = time.time()
            conn = None
            try:
                conn = http.client.HTTPConnection(self.host, self.port, timeout=req_timeout)
                if self.http10_bypass:
                    conn._http_vsn = 10
                    conn._http_vsn_str = "HTTP/1.0"
                    conn.putrequest(method, full_path, skip_host=True, skip_accept_encoding=True)
                else:
                    conn.putrequest(method, full_path)

                if headers:
                    for k, v in headers.items():
                        conn.putheader(k, v)
                conn.endheaders()

                resp = conn.getresponse()
                latency_ms = (time.time() - t0) * 1000.0
                body_bytes = resp.read()
                status_code = resp.status

                # 解析 JSON
                try:
                    parsed_json = json.loads(body_bytes.decode("utf-8"))
                    biz_code = parsed_json.get("code", 0)
                    biz_msg = parsed_json.get("msg", "ok")
                    biz_data = parsed_json.get("data", parsed_json)
                    success = (status_code == 200 and biz_code == 0)
                    
                    if not success and status_code >= 500 and attempt < self.max_retries:
                        time.sleep(current_delay)
                        current_delay *= self.backoff_factor
                        continue

                    return AxckResponse(
                        success=success,
                        status_code=status_code,
                        code=biz_code,
                        msg=biz_msg,
                        data=biz_data,
                        latency_ms=latency_ms,
                        raw_json=parsed_json,
                        retries_attempted=attempt
                    )
                except json.JSONDecodeError:
                    if status_code >= 500 and attempt < self.max_retries:
                        time.sleep(current_delay)
                        current_delay *= self.backoff_factor
                        continue

                    return AxckResponse(
                        success=False,
                        status_code=status_code,
                        code=-1,
                        msg="JSON Decode Error",
                        data=body_bytes.decode("utf-8", errors="ignore"),
                        latency_ms=latency_ms,
                        retries_attempted=attempt,
                        error="Invalid JSON response"
                    )

            except Exception as e:
                latency_ms = (time.time() - t0) * 1000.0
                last_error = str(e)
                status_code = 0

                if attempt < self.max_retries:
                    time.sleep(current_delay)
                    current_delay *= self.backoff_factor
                    continue

                return AxckResponse(
                    success=False,
                    status_code=status_code,
                    code=-1,
                    msg=f"Request failed: {last_error}",
                    data=None,
                    latency_ms=latency_ms,
                    retries_attempted=attempt,
                    error=last_error
                )
            finally:
                if conn:
                    conn.close()
