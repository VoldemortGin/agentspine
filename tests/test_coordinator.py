"""编排合约:顺序 / 并行跑 2 个 mock agent、保序收集、编排级 trace 隐私安全。"""

from corespine.observability.trace import InProcessPrivacyTraceSink

from agentspine.agent.agent import FunctionAgent
from agentspine.orchestration.coordinator import Coordinator


def _two_mock_agents():
    return [
        FunctionAgent("a", lambda t: f"a:{t}"),
        FunctionAgent("b", lambda t: f"b:{t}"),
    ]


def test_run_sequential_collects_all_in_order():
    coord = Coordinator(_two_mock_agents())
    results = coord.run_sequential("go")
    assert [r.agent for r in results] == ["a", "b"]
    assert [r.output for r in results] == ["a:go", "b:go"]


def test_run_parallel_collects_all_preserving_order():
    coord = Coordinator(_two_mock_agents())
    results = coord.run_parallel("go")
    # 并发跑,但结果仍按 agent 输入顺序返回(确定性、可断言)。
    assert [r.agent for r in results] == ["a", "b"]
    assert [r.output for r in results] == ["a:go", "b:go"]


def test_coordinator_emits_only_privacy_safe_summary_trace():
    sink = InProcessPrivacyTraceSink()
    coord = Coordinator(_two_mock_agents(), trace=sink)
    coord.run_sequential("go")
    coord.run_parallel("go")
    assert sink.codes() == ["coordinate", "coordinate"]
    assert [e.fields["mode"] for e in sink.events] == ["sequential", "parallel"]
    assert all(e.fields["agent_count"] == 2 for e in sink.events)
    # 编排级 trace 只含模式 / 计数 / 耗时,没有任务或输出正文。
    for event in sink.events:
        assert set(event.fields) == {"mode", "agent_count", "took_ms"}
