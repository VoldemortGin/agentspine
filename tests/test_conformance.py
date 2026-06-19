"""conformance 合约:用 corespine harness 把本包的不变量绑成参数化套件 + 检出泄露违反。

机制由 corespine.ConformanceSuite 提供(实现 × 不变量 笛卡尔积);保证由 agentspine 绑定
(ADR 0001 D6)。这里把两类实现各喂进自己的不变量包:
  - 2 个 agent 实现 × 3 条 agent 不变量;
  - 2 个 tool 实现 × 2 条 tool 不变量。
再用一个故意把任务正文写进 trace 的「泄露 agent」证明:隐私不变量格子会被 run() 标红。
"""

import pytest

from corespine.conformance.harness import ConformanceSuite
from corespine.llm.provider import MockProvider

from agentspine.agent.agent import AgentResult, FunctionAgent, LlmAgent
from agentspine.conformance import AGENT_INVARIANTS, TOOL_INVARIANTS
from agentspine.tools.tool import CalcTool, EchoTool

AGENT_SUITE = ConformanceSuite(
    {
        "llm": lambda: LlmAgent("llm", MockProvider()),
        "function": lambda: FunctionAgent("function", lambda task: f"done:{task}"),
    },
    AGENT_INVARIANTS,
)

TOOL_SUITE = ConformanceSuite({"echo": EchoTool, "calc": CalcTool}, TOOL_INVARIANTS)


@pytest.mark.parametrize(
    ("impl", "invariant"), AGENT_SUITE.cases(), ids=AGENT_SUITE.ids()
)
def test_agent_conformance(impl, invariant):
    """每个 agent 实现 × 每条 agent 不变量 各跑一格(2 × 3 = 6 格全绿)。"""
    AGENT_SUITE.check(impl, invariant)


@pytest.mark.parametrize(
    ("impl", "invariant"), TOOL_SUITE.cases(), ids=TOOL_SUITE.ids()
)
def test_tool_conformance(impl, invariant):
    """每个 tool 实现 × 每条 tool 不变量 各跑一格(2 × 2 = 4 格全绿)。"""
    TOOL_SUITE.check(impl, invariant)


def test_conformance_detects_a_trace_payload_leak():
    """故意把任务正文写进 trace 的 agent:隐私不变量格子应被 run() 如实标红。"""

    class LeakyAgent:
        name = "leaky"

        def step(self, task, *, trace=None):
            if trace is not None:
                # 违规:把任务正文塞进 trace。InProcessPrivacyTraceSink.emit 会抛 TraceError。
                trace.emit("agent_step", text=task)
            return AgentResult(agent=self.name, output="ok")

    suite = ConformanceSuite({"leaky": LeakyAgent}, AGENT_INVARIANTS)
    results = suite.run()
    assert not suite.passed()
    failed = {r.invariant for r in results if not r.passed}
    # provenance / 产出两条它没违反;只在隐私 trace 那条踩雷。
    assert failed == {"step_traces_are_privacy_safe"}
