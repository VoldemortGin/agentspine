"""agentspine 自己的不变量(机制借 corespine.conformance,保证由本包绑定,ADR 0001 D6)。

corespine 的 ConformanceSuite 只提供「实现 × 不变量」笛卡尔积的【机制】;具体保证在此绑定。
本包绑两组:

  agent_step —— ①步必产出非空文本;②结果可溯源到产出它的 agent(provenance);
                ③步级 trace 只记元数据,绝不泄露任务/输出正文(隐私安全,由 corespine 的
                  InProcessPrivacyTraceSink「构造即保证」兜底)。
  tool_call  —— ①工具结果可溯源到产出它的工具(provenance);②调用必产出非空文本。

任何号称 Agent / Tool 的实现都必须跑过这两组——没过 conformance 的实现直接红,而非埋雷。
"""

from __future__ import annotations

from corespine.conformance.harness import InvariantPack
from corespine.observability.trace import FORBIDDEN_KEYS, InProcessPrivacyTraceSink

from agentspine.agent.agent import Agent, AgentResult
from agentspine.tools.tool import Tool

# 一段含敏感正文的任务:agent 若把它写进 trace 即泄露——隐私不变量要挡住的正是这个。
_SENSITIVE_TASK = "机密档案:绝密数字 42 与真实姓名,严禁原样写入 trace。"


def _step_returns_output(agent: Agent) -> None:
    result = agent.step("ping")
    assert isinstance(result, AgentResult)
    assert result.output, "agent 步必须产出非空文本"


def _result_carries_agent_provenance(agent: Agent) -> None:
    result = agent.step("ping")
    assert result.agent == agent.name, "结果必须可溯源到产出它的 agent"


def _step_traces_are_privacy_safe(agent: Agent) -> None:
    sink = InProcessPrivacyTraceSink()
    # 隐私 by construction:agent 若试图把任务/输出正文写进 trace,emit 立刻抛 TraceError。
    agent.step(_SENSITIVE_TASK, trace=sink)
    assert sink.codes(), "agent 步至少应发一条元数据 trace"
    for event in sink.events:
        leaked = {k for k in event.fields if k.strip().lower() in FORBIDDEN_KEYS}
        assert not leaked, f"步级 trace 泄露了受限字段:{sorted(leaked)}"


AGENT_INVARIANTS: InvariantPack[Agent] = (
    InvariantPack("agent_step")
    .add("step_returns_output", _step_returns_output)
    .add("result_carries_agent_provenance", _result_carries_agent_provenance)
    .add("step_traces_are_privacy_safe", _step_traces_are_privacy_safe)
)


def _tool_result_carries_provenance(tool: Tool) -> None:
    result = tool.run("1+1")
    assert result.tool == tool.name, "工具结果必须可溯源到产出它的工具"


def _tool_run_returns_output(tool: Tool) -> None:
    result = tool.run("1+1")
    assert result.output, "工具调用必须产出非空文本"


TOOL_INVARIANTS: InvariantPack[Tool] = (
    InvariantPack("tool_call")
    .add("result_carries_tool_provenance", _tool_result_carries_provenance)
    .add("run_returns_output", _tool_run_returns_output)
)
