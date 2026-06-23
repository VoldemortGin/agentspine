"""编排开销基线:量 spineagent 几条核心路径的【每次操作开销】(纯标准库 timeit)。

跑法:`python benchmarks/bench_orchestration.py`(或 `make bench`)。全程零网络 / 零 key /
零真实 LLM API——provider 全是脚本化 fake / corespine MockProvider,确定性可复现。这不是
"真实模型性能"测试(那取决于远端模型,不可复现),而是给 agent 编排的【机制开销】钉一个基线:
工具循环每步的分派 / 喂回成本、Coordinator 并行 vs 串行的编排开销。基线让"某次改动悄悄把
编排变贵"无所遁形。

量四类路径(都走真实导出的公开 API,与消费者用法一致):
  1. 工具循环(ToolUsingAgent)    —— 离线确定性 SyntaxToolPolicy 跑 N 步 calc 链($prev 喂回);
  2. function-calling 循环         —— 脚本化 provider 吐 N 轮 tool_calls 再收尾(真 function-calling 形状);
  3. Coordinator 串行 vs 并行(纯 CPU)—— 零人造延迟,显露线程池【纯编排开销】本身;
  4. Coordinator 串行 vs 并行(带延迟)—— 每个 fake agent 带可控人造 sleep,显露并行【加速比】。

路径 3/4 是同一对比的两面:CPU-only 那对暴露"并行不是免费的"(线程池本身有开销),
带延迟那对暴露"agent 各自等待(IO/模型)时并行才真正赢"。末行打印 "bench orchestration OK"。
基线数字见同目录 BENCH.md。
"""

from __future__ import annotations

import time
import timeit
from collections.abc import Callable
from functools import partial

from corespine.llm.provider import (
    ChatCompletion,
    Choice,
    FunctionCall,
    ResponseMessage,
    ToolCall,
    Usage,
)

from spineagent.agent.agent import FunctionAgent
from spineagent.agent.function_calling import FunctionCallingAgent
from spineagent.agent.policy import SyntaxToolPolicy
from spineagent.agent.tool_using import ToolUsingAgent
from spineagent.orchestration.coordinator import Coordinator
from spineagent.tools.function_tool import FunctionTool
from spineagent.tools.tool import CalcTool


def _fmt(seconds_per_op: float) -> str:
    """把"每次操作秒数"格式化成人类可读(ns / µs / ms)。"""
    ns = seconds_per_op * 1e9
    if ns < 1_000:
        return f"{ns:9.1f} ns"
    if ns < 1_000_000:
        return f"{ns / 1_000:9.2f} µs"
    return f"{ns / 1_000_000:9.3f} ms"


def _measure(label: str, fn: Callable[[], object], *, number: int, repeat: int = 5) -> float:
    """对 fn 跑 repeat 轮、每轮 number 次,取【最优轮】的单次开销并打印(timeit 惯例:取 min)。"""
    # timeit 的标准用法是取多轮 min:它最接近"无外部噪声干扰下的真实开销"。
    best = min(timeit.repeat(fn, number=number, repeat=repeat)) / number
    print(f"  {label:<48} {_fmt(best)}   (n={number:,}×{repeat})")
    return best


# ── 路径 1:工具循环(ToolUsingAgent,离线确定性)─────────────────────────────────
def _calc_chain_task(steps: int) -> str:
    """构造一条 N 步 calc 链:首步 1+1,其后每步 `$prev * 1`(把上一步观测喂回)。"""
    lines = ["calc: 1+1"]
    lines += ["calc: $prev * 1"] * (steps - 1)
    return "\n".join(lines)


def _bench_tool_loop() -> None:
    # max_steps 给足,使每条链都正常跑满 N 步工具调用(不触顶兜底)。
    agent = ToolUsingAgent("bench", SyntaxToolPolicy(), [CalcTool()], max_steps=64)
    for steps in (1, 4, 16):
        task = _calc_chain_task(steps)
        _measure(
            f"ToolUsingAgent.step({steps:>2} 步 calc 链)",
            partial(agent.step, task),
            number=20_000,
        )


# ── 路径 2:function-calling 循环(脚本化 provider,零真实 API)───────────────────
class _ScriptedProvider:
    """按脚本依次返回 ChatCompletion 的 fake provider;每次 chat 从头复用同一脚本(可重入)。

    与真实模型同形(ChatCompletion + tool_calls + OpenAI message dicts),但纯本地确定性:
    bench 反复调 step() 时每次从 turn 0 开始重放,故可被 timeit 任意次重复而结果稳定。
    """

    def __init__(self, *responses: ChatCompletion) -> None:
        self._responses = responses
        self._i = 0

    def chat(self, messages: object, *, tools: object = None) -> ChatCompletion:  # noqa: ARG002
        resp = self._responses[self._i]
        self._i = (self._i + 1) % len(self._responses)
        return resp


def _echo_tool() -> FunctionTool:
    return FunctionTool(
        name="echo",
        description="回显",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
        func=lambda text: text,
    )


def _tool_turn(call_id: str, arguments: str) -> ChatCompletion:
    msg = ResponseMessage(
        role="assistant",
        content=None,
        tool_calls=(ToolCall(id=call_id, function=FunctionCall(name="echo", arguments=arguments)),),
    )
    return ChatCompletion(
        choices=(Choice(index=0, message=msg, finish_reason="tool_calls"),),
        usage=Usage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
    )


def _text_turn(content: str) -> ChatCompletion:
    return ChatCompletion(
        choices=(Choice(index=0, message=ResponseMessage(role="assistant", content=content)),),
        usage=Usage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
    )


def _bench_function_calling_loop() -> None:
    # 脚本:N 轮 tool_calls(各执行一次 echo 工具、按 OpenAI 形状喂回)后,末轮出文本收尾。
    for rounds in (1, 4, 16):
        script = [_tool_turn(f"c{i}", '{"text": "x"}') for i in range(rounds)] + [
            _text_turn("done")
        ]
        agent = FunctionCallingAgent(
            "bench", _ScriptedProvider(*script), [_echo_tool()], max_steps=rounds + 1
        )
        _measure(
            f"FunctionCallingAgent.step({rounds:>2} 轮 tool_calls)",
            partial(agent.step, "go"),
            number=20_000,
        )


# ── 路径 3/4:Coordinator 串行 vs 并行 ────────────────────────────────────────
def _cpu_agents(n: int) -> list[FunctionAgent]:
    """n 个纯 CPU fake agent(无 IO / 无 sleep):量线程池本身的纯编排开销。"""
    return [FunctionAgent(f"a{i}", lambda t: f"a:{t}") for i in range(n)]


def _delay_agents(n: int, delay_s: float) -> list[FunctionAgent]:
    """n 个带固定人造延迟的 fake agent:模拟 agent 各自等待(IO/模型),让并行加速比显形。

    用 time.sleep 制造可控延迟而非真实 IO——零网络、确定性、跨平台。串行总耗时≈n×delay,
    并行(线程池在 sleep 期间释放 GIL)总耗时≈delay,加速比≈agent 数。
    """

    def _slow(task: str, *, d: float = delay_s) -> str:
        time.sleep(d)
        return f"a:{task}"

    return [FunctionAgent(f"a{i}", _slow) for i in range(n)]


def _bench_coordinator_cpu() -> None:
    # 纯 CPU、零延迟:串行就是顺序调 n 次;并行多了线程池 submit/join 的固定开销。
    for n in (2, 8):
        coord = Coordinator(_cpu_agents(n))
        seq = _measure(
            f"Coordinator.run_sequential(纯CPU,{n} agent)",
            partial(coord.run_sequential, "go"),
            number=20_000,
        )
        par = _measure(
            f"Coordinator.run_parallel  (纯CPU,{n} agent)",
            partial(coord.run_parallel, "go"),
            number=5_000,
        )
        print(
            f"     -> 纯CPU {n} agent:并行/串行 = {par / seq:5.2f}×(>1 说明线程池开销在纯CPU下不划算)"
        )


def _bench_coordinator_delay() -> None:
    # 每个 agent 固定 sleep:串行≈n×delay,并行≈delay(sleep 释放 GIL,线程真并发)。
    delay_ms = 2.0
    delay_s = delay_ms / 1_000
    for n in (2, 8):
        coord = Coordinator(_delay_agents(n, delay_s))
        # 延迟路径每次 op 本就是毫秒级,number 取小、repeat 取多即可拿到稳定中位。
        seq = _measure(
            f"Coordinator.run_sequential({n} agent×{delay_ms:g}ms)",
            partial(coord.run_sequential, "go"),
            number=20,
        )
        par = _measure(
            f"Coordinator.run_parallel  ({n} agent×{delay_ms:g}ms)",
            partial(coord.run_parallel, "go"),
            number=20,
        )
        print(
            f"     -> 带延迟 {n} agent:串行/并行 = {seq / par:5.2f}×(理想≈{n};并行赢在 agent 各自等待时)"
        )


def main() -> None:
    print("spineagent 编排开销基线(单次操作;路径 1/2/3 越小越好):")
    print("[1] 工具循环 ToolUsingAgent(离线确定性 SyntaxToolPolicy,$prev 喂回)")
    _bench_tool_loop()
    print("[2] function-calling 循环 FunctionCallingAgent(脚本化 provider,零真实 API)")
    _bench_function_calling_loop()
    print("[3] Coordinator 串行 vs 并行 —— 纯 CPU(显露线程池纯编排开销)")
    _bench_coordinator_cpu()
    print("[4] Coordinator 串行 vs 并行 —— 带人造延迟(显露并行加速比)")
    _bench_coordinator_delay()
    print("bench orchestration OK")


if __name__ == "__main__":
    main()
