#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/scenario.py
L2/L3: 步骤与带外协同断言层 & 场景链式编排引擎 (Scenario Pipeline)
提供流式 DSL 编排测试步骤，执行复合断言，采集每一步的耗时并在会话中实时打印结构化用例。
"""

import time
from typing import Callable, List, Dict, Any, Optional
from dataclasses import dataclass, field
from .http_client import AxckResponse
from .domain_apis import AxckClient

@dataclass
class StepResult:
    name: str
    success: bool
    latency_ms: float
    response: Optional[AxckResponse] = None
    error: Optional[str] = None
    description: str = ""

@dataclass
class ScenarioReport:
    scenario_name: str
    success: bool
    total_steps: int
    passed_count: int
    failed_count: int
    duration_seconds: float
    step_results: List[StepResult] = field(default_factory=list)

class Step:
    def __init__(
        self,
        name: str,
        action: Callable[[AxckClient], AxckResponse],
        assertion: Optional[Callable[[AxckResponse], bool]] = None,
        wait_after: float = 0.0,
        description: str = ""
    ):
        self.name = name
        self.action = action
        self.assertion = assertion
        self.wait_after = wait_after
        self.description = description or name

class ScenarioPipeline:
    def __init__(self, name: str, steps: List[Step]):
        self.name = name
        self.steps = steps

class ScenarioBuilder:
    """
    场景流式构建器 DSL
    """
    def __init__(self, name: str):
        self.name = name
        self.steps: List[Step] = []

    def step(
        self,
        name: str,
        action: Callable[[AxckClient], AxckResponse],
        assertion: Optional[Callable[[AxckResponse], bool]] = None,
        wait_after: float = 0.0,
        description: str = ""
    ) -> 'ScenarioBuilder':
        """添加单个执行步骤与可选断言"""
        self.steps.append(Step(name, action, assertion, wait_after, description))
        return self

    def repeat(
        self,
        name_prefix: str,
        times: int,
        interval: float,
        action: Callable[[AxckClient], AxckResponse],
        description_prefix: str = ""
    ) -> 'ScenarioBuilder':
        """批量循环添加重复动作步骤 (如突发连拍、高频切流)"""
        desc = description_prefix or name_prefix
        for i in range(times):
            self.steps.append(
                Step(
                    name=f"{name_prefix}_{i+1}",
                    action=action,
                    wait_after=interval,
                    description=f"{desc} [第{i+1}/{times}次循环]"
                )
            )
        return self

    def build(self) -> ScenarioPipeline:
        return ScenarioPipeline(self.name, self.steps)

class ScenarioRunner:
    """
    场景执行引擎，支持注入 CaseReporter 及 inspector 实时输出每项测试信息与内存监控
    """
    def __init__(self, client: AxckClient, reporter=None, inspector=None):
        self.client = client
        self.reporter = reporter
        self.inspector = inspector
        self._last_mem_snap = None
        if self.inspector:
            try:
                self._last_mem_snap = self.inspector.get_memory_snapshot()
            except Exception:
                pass

    def run(self, pipeline: ScenarioPipeline, stop_on_failure: bool = True) -> ScenarioReport:
        step_results: List[StepResult] = []
        t0 = time.time()
        overall_success = True

        for idx, step in enumerate(pipeline.steps, start=1):
            step_t0 = time.time()
            resp = None
            try:
                resp = step.action(self.client)
                step_latency = (time.time() - step_t0) * 1000.0

                success = resp.success
                error = None
                if not success:
                    error = resp.msg or resp.error or "HTTP/Biz error"

                # 执行自定义业务断言
                if success and step.assertion is not None:
                    try:
                        assert_res = step.assertion(resp)
                        if not assert_res:
                            success = False
                            error = "Custom assertion failed"
                    except Exception as e:
                        success = False
                        error = f"Assertion exception: {str(e)}"

                # 采样当前内存状态并计算增量
                mem_info = None
                cur_snap = None
                delta_cmm_kb = 0
                delta_rss_kb = 0
                if self.inspector:
                    try:
                        cur_snap = self.inspector.get_memory_snapshot()
                        if cur_snap and cur_snap.get("cmm_total_kb", 0) > 0:
                            if self._last_mem_snap:
                                delta_cmm_kb = cur_snap.get("cmm_used_kb", 0) - self._last_mem_snap.get("cmm_used_kb", 0)
                                delta_rss_kb = cur_snap.get("vm_rss_kb", 0) - self._last_mem_snap.get("vm_rss_kb", 0)
                            mem_info = dict(cur_snap)
                            mem_info["delta_cmm_kb"] = delta_cmm_kb
                            mem_info["delta_rss_kb"] = delta_rss_kb
                            self._last_mem_snap = cur_snap
                    except Exception:
                        pass

                step_results.append(
                    StepResult(
                        name=step.name,
                        success=success,
                        latency_ms=step_latency,
                        response=resp,
                        error=error,
                        description=step.description
                    )
                )

                # 实时向 CaseReporter 汇报本项测试
                if self.reporter:
                    gates = {
                        "HTTP_Status": {
                            "desc": "HTTP响应码",
                            "expected": 200,
                            "actual": resp.status_code if resp else "None",
                            "passed": resp.status_code == 200 if resp else False
                        },
                        "Biz_Code": {
                            "desc": "业务执行码",
                            "expected": 0,
                            "actual": resp.code if resp else -1,
                            "passed": resp.code == 0 if resp else False
                        }
                    }
                    if mem_info:
                        # 单步 CMM 内存泄露门限 < 1024KB
                        cmm_leak_ok = delta_cmm_kb < 1024
                        gates["CMM_Leak_Check"] = {
                            "desc": "单步物理CMM泄露门限 (<1MB)",
                            "expected": "<1024KB",
                            "actual": f"{delta_cmm_kb:+d}KB",
                            "passed": cmm_leak_ok
                        }
                    if step.assertion is not None:
                        gates["Custom_Assert"] = {
                            "desc": "自定义业务门限",
                            "expected": "True",
                            "actual": str(success),
                            "passed": success
                        }

                    inputs = {"pipeline": pipeline.name, "step_idx": idx, "step_name": step.name}
                    outputs = {
                        "status_code": resp.status_code if resp else 0,
                        "code": resp.code if resp else -1,
                        "latency_ms": round(step_latency, 2),
                        "data": resp.data if resp else None
                    }
                    self.reporter.report_case(
                        suite_name="scenario",
                        case_name=f"{idx}. {step.name}",
                        step_method=step.description,
                        inputs=inputs,
                        outputs=outputs,
                        gates=gates,
                        memory_info=mem_info,
                        status="PASS" if success else "FAIL",
                        duration=step_latency / 1000.0,
                        error_msg=error
                    )

                if not success:
                    overall_success = False
                    if stop_on_failure:
                        break

            except Exception as e:
                step_latency = (time.time() - step_t0) * 1000.0
                err_msg = str(e)
                step_results.append(
                    StepResult(
                        name=step.name,
                        success=False,
                        latency_ms=step_latency,
                        error=err_msg,
                        description=step.description
                    )
                )
                if self.reporter:
                    self.reporter.report_case(
                        suite_name="scenario",
                        case_name=f"{idx}. {step.name}",
                        step_method=step.description,
                        inputs={"pipeline": pipeline.name, "step_idx": idx},
                        outputs={"exception": err_msg},
                        gates={"Execution": {"desc": "执行无未捕获异常", "expected": "PASS", "actual": "EXCEPTION", "passed": False}},
                        status="FAIL",
                        duration=step_latency / 1000.0,
                        error_msg=err_msg
                    )

                overall_success = False
                if stop_on_failure:
                    break

            if step.wait_after > 0:
                time.sleep(step.wait_after)

        passed = sum(1 for r in step_results if r.success)
        failed = len(step_results) - passed
        duration = time.time() - t0

        return ScenarioReport(
            scenario_name=pipeline.name,
            success=overall_success,
            total_steps=len(step_results),
            passed_count=passed,
            failed_count=failed,
            duration_seconds=duration,
            step_results=step_results
        )
