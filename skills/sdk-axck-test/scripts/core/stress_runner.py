#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/stress_runner.py
L3: 压力、极限与浸泡测试引擎 (Stress & Soak Engine)
支持多并发、高吞吐突发 (Burst)、时延分布剖析 (Min/Max/Avg/P50/P90/P95/P99) 及错误率分析。
"""

import time
import statistics
from typing import Callable, List, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from .http_client import AxckResponse
from .domain_apis import AxckClient

@dataclass
class StressConfig:
    name: str = "stress_test"
    total_requests: int = 100
    concurrency: int = 5
    interval: float = 0.0          # 每个工作线程内部请求间隔 (秒)
    timeout_per_req: float = 5.0

@dataclass
class StressReport:
    name: str
    total_requests: int
    success_count: int
    failed_count: int
    duration_seconds: float
    qps: float
    min_latency_ms: float
    max_latency_ms: float
    avg_latency_ms: float
    p50_latency_ms: float
    p90_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    error_summary: List[str] = field(default_factory=list)

class StressRunner:
    """
    轻量级并发压力与浸泡测试运行器
    """
    def __init__(self, client: AxckClient):
        self.client = client

    def run(
        self,
        action: Callable[[AxckClient], AxckResponse],
        config: StressConfig
    ) -> StressReport:
        latencies: List[float] = []
        errors: List[str] = []
        success_count = 0
        failed_count = 0

        t_start = time.time()

        # 分配任务到线程池
        def _worker_task() -> Optional[AxckResponse]:
            if config.interval > 0:
                time.sleep(config.interval)
            try:
                return action(self.client)
            except Exception as e:
                return AxckResponse(
                    success=False,
                    status_code=0,
                    code=-1,
                    msg=str(e),
                    data=None,
                    latency_ms=0.0,
                    error=str(e)
                )

        with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
            futures = [executor.submit(_worker_task) for _ in range(config.total_requests)]
            for fut in as_completed(futures):
                resp = fut.result()
                if resp is not None:
                    latencies.append(resp.latency_ms)
                    if resp.success:
                        success_count += 1
                    else:
                        failed_count += 1
                        if resp.msg and resp.msg not in errors:
                            errors.append(resp.msg)
                else:
                    failed_count += 1
                    errors.append("None response from worker")

        duration = time.time() - t_start
        qps = (len(latencies) / duration) if duration > 0 else 0.0

        latencies.sort()
        if latencies:
            min_l = latencies[0]
            max_l = latencies[-1]
            avg_l = sum(latencies) / len(latencies)
            p50_l = statistics.median(latencies)
            
            def percentile(p: float) -> float:
                idx = int(len(latencies) * p)
                if idx >= len(latencies):
                    idx = len(latencies) - 1
                return latencies[idx]

            p90_l = percentile(0.90)
            p95_l = percentile(0.95)
            p99_l = percentile(0.99)
        else:
            min_l = max_l = avg_l = p50_l = p90_l = p95_l = p99_l = 0.0

        return StressReport(
            name=config.name,
            total_requests=len(latencies),
            success_count=success_count,
            failed_count=failed_count,
            duration_seconds=duration,
            qps=qps,
            min_latency_ms=round(min_l, 2),
            max_latency_ms=round(max_l, 2),
            avg_latency_ms=round(avg_l, 2),
            p50_latency_ms=round(p50_l, 2),
            p90_latency_ms=round(p90_l, 2),
            p95_latency_ms=round(p95_l, 2),
            p99_latency_ms=round(p99_l, 2),
            error_summary=errors
        )
