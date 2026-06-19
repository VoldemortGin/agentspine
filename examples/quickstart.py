"""agentspine 一键离线 demo:多 agent 编排(顺序 / 并行)+ 工具派发 + 隐私安全 trace。

零网络、零重依赖、确定性可复现:
  - agent 走 corespine 的 `MockProvider`(离线确定性回声)与纯函数 `FunctionAgent`;
  - 编排用 `Coordinator` 把同一任务【顺序】与【并行】跑一遍,并行结果仍保序;
  - 工具派发一个 `CalcTool`(安全算术求值),结果带 provenance;
  - trace 用 corespine 的 `InProcessPrivacyTraceSink`:只记 code / 计数 / 耗时,塞正文会被
    「构造即保证」直接拒绝。

`make demo` 即跑本文件;成功时最后打印 "agentspine OK"。
"""

from __future__ import annotations

from corespine.llm.provider import MockProvider
from corespine.observability.trace import InProcessPrivacyTraceSink

from agentspine import Agent, CalcTool, Coordinator, FunctionAgent, LlmAgent

# 一段含敏感正文的任务:它绝不该出现在任何 trace 里(隐私不变量,文末自检)。
_TASK = "为发布写一个三步上线计划:机密代号 42"


def _build_agents() -> list[Agent]:
    """搭 3 个离线 mock agent:1 个走确定性 LLM(MockProvider),2 个纯函数节点。"""
    return [
        LlmAgent("planner", MockProvider(), system="你是计划助手"),
        FunctionAgent("reverse", lambda task: task[::-1]),
        FunctionAgent("tagger", lambda task: f"[done] {task}"),
    ]


def main() -> None:
    # 编排级 trace:只记 mode / agent 数 / 耗时(隐私安全)。
    orchestration_trace = InProcessPrivacyTraceSink()
    coord = Coordinator(_build_agents(), trace=orchestration_trace)

    print("== 顺序编排 ==")
    for r in coord.run_sequential(_TASK):
        print(f"  {r.agent}: {r.output}")

    print("== 并行编排(线程池并发,结果仍按 agent 顺序返回)==")
    for r in coord.run_parallel(_TASK):
        print(f"  {r.agent}: {r.output}")

    # 工具派发:带 provenance 的结果(result.tool 可溯源到产出它的工具)。
    print("== 工具派发 ==")
    res = CalcTool().run("2 * (3 + 4)")
    print(f"  tool={res.tool} output={res.output}")

    # 步级隐私 trace:把含敏感正文的任务跑进 sink —— 只会记元数据,绝不记正文。
    step_trace = InProcessPrivacyTraceSink()
    LlmAgent("planner", MockProvider()).step(_TASK, trace=step_trace)

    print("== 隐私安全 trace(只含 code / 计数 / 耗时,无任务/输出正文)==")
    for label, sink in (("编排", orchestration_trace), ("步级", step_trace)):
        for event in sink.events:
            print(f"  [{label}] code={event.code} fields={dict(event.fields)}")

    # 自检:trace 字段里绝不出现任务正文(隐私不变量,跑挂即视为回归)。
    leaked = [
        event
        for sink in (orchestration_trace, step_trace)
        for event in sink.events
        if any(_TASK in str(value) for value in event.fields.values())
    ]
    assert not leaked, "trace 泄露了任务正文,违反隐私不变量"

    print("agentspine OK")


if __name__ == "__main__":
    main()
