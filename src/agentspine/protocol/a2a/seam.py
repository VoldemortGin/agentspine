"""A2A(Agent-to-Agent)缝:A2AAgent 协议 + 离线回环 stub 默认。

家族缝的元模式(同 MCP 缝):Protocol + 离线确定性默认 + Registry 工厂 + 真实后端经可选
extra 延迟 import。默认路径【零网络、零重依赖】:OfflineA2AStub 在进程内回环——给出 agent
card(能力描述)并应答一条任务,让跨 agent 协作在离线 / 测试下也能端到端跑。

真实 A2A SDK(`a2a-sdk`,import 名 `a2a`)仅在选用时,经 [a2a] extra 由 corespine
.lazy_extra_import 延迟 import;未装时给「pip install agentspine[a2a]」友好报错。本模块
顶层【绝不】import 真实 SDK——import agentspine 不该拉入任何网络 SDK。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from corespine.seam.registry import Registry, lazy_extra_import

# 真实 A2A SDK 的 import 名(装了 agentspine[a2a] 才有);默认离线路径绝不 import 它。
_A2A_SDK_MODULE = "a2a"


@dataclass(frozen=True)
class A2ATask:
    """一条跨 agent 任务:task_id + 文本(协议载荷本身,非 trace)。"""

    task_id: str
    text: str


@dataclass(frozen=True)
class A2AResult:
    """跨 agent 任务结果:task_id + 产出 + 来源 agent 名(provenance)。"""

    task_id: str
    output: str
    agent: str


@runtime_checkable
class A2AAgent(Protocol):
    """A2A 协议:有名字;能给出 agent card(能力描述);能接收并应答一条任务。"""

    name: str

    def card(self) -> dict[str, Any]: ...

    def send(self, task: A2ATask) -> A2AResult: ...


class OfflineA2AStub:
    """离线回环 A2A:把一个本地应答函数暴露为 A2AAgent,零网络(默认 / 测试用)。"""

    def __init__(
        self,
        *,
        name: str = "offline-a2a",
        responder: Callable[[str], str] | None = None,
    ) -> None:
        self._name = name
        self._responder = responder or (lambda text: f"echo:{text}")

    @property
    def name(self) -> str:
        return self._name

    def card(self) -> dict[str, Any]:
        return {"name": self._name, "transport": "offline-loopback", "skills": ["echo"]}

    def send(self, task: A2ATask) -> A2AResult:
        return A2AResult(
            task_id=task.task_id, output=self._responder(task.text), agent=self._name
        )


def load_a2a_sdk() -> Any:
    """延迟 import 真实 A2A SDK;未装 [a2a] extra 时给「pip install agentspine[a2a]」友好报错。"""
    return lazy_extra_import(_A2A_SDK_MODULE, pkg="agentspine", extra="a2a")


def _make_real_agent(**kwargs: Any) -> A2AAgent:
    # 缺 [a2a] extra -> 友好 ImportError(离线默认路径永远不会走到这)。
    sdk = load_a2a_sdk()
    raise NotImplementedError(
        f"真实 A2A 适配器留待装了 agentspine[a2a] 的使用者按 {sdk.__name__!r} 接入;"
        "本壳只提供缝 + 离线 stub。"
    )


# 缝注册表:一个 spec 选实现(默认 offline 离线 stub;real 走延迟 import 的真实 SDK)。
a2a_agents: Registry[A2AAgent] = Registry("a2a_agent")
a2a_agents.register("offline", lambda **kw: OfflineA2AStub(**kw))
a2a_agents.register("real", _make_real_agent)
