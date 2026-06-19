"""最小多 agent 编排:把若干 Agent 顺序【或】并行跑同一个任务,收集结果。

Coordinator 是 agentspine 的「编排」缝最小实现:零外部依赖、离线可跑(用 mock agent 即可)。
  - run_sequential —— 逐个跑,保序收集 AgentResult;
  - run_parallel  —— 用线程池并发跑,结果仍按 agent 顺序返回(确定性 / 可断言)。

隐私:Coordinator 自己只记【编排级】元数据(模式 / agent 数 / 耗时),绝不记任务/输出正文;
并行分支不向各 agent 共享同一个 sink(避免跨线程写同一列表的竞态),per-agent 的 trace 是
agent 被直接调用时自己的事(见 agent/agent.py 的隐私约定)。
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from corespine.observability.trace import TraceSink

from agentspine.agent.agent import Agent, AgentResult


class Coordinator:
    """顺序 / 并行跑一组 agent,收集结果的最小协调器。"""

    def __init__(self, agents: Iterable[Agent], *, trace: TraceSink | None = None) -> None:
        self._agents = list(agents)
        self._trace = trace

    @property
    def agents(self) -> list[Agent]:
        return list(self._agents)

    def run_sequential(self, task: str) -> list[AgentResult]:
        """逐个跑每个 agent,按顺序收集结果。"""
        start = time.perf_counter()
        results = [agent.step(task) for agent in self._agents]
        self._emit("sequential", start)
        return results

    def run_parallel(self, task: str, *, max_workers: int | None = None) -> list[AgentResult]:
        """用线程池并发跑;结果仍按 agent 输入顺序返回(map 保序)。"""
        start = time.perf_counter()
        workers = max_workers or max(1, len(self._agents))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda agent: agent.step(task), self._agents))
        self._emit("parallel", start)
        return results

    def _emit(self, mode: str, start: float) -> None:
        """记一条隐私安全的编排级 trace:模式 + agent 数 + 耗时,绝不记正文。"""
        if self._trace is None:
            return
        self._trace.emit(
            "coordinate",
            mode=mode,
            agent_count=len(self._agents),
            took_ms=round((time.perf_counter() - start) * 1000, 3),
        )
