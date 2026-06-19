"""agentspine —— 通用多 agent 协作框架(ADR 0001 D1),依赖薄核 corespine。

agent / tool / 编排 + MCP / A2A 协议缝。复用 corespine 的缝元模式(Protocol + 离线确定性
默认 + Registry 工厂 + 参数化 conformance)、隐私安全 observability 与 env 配置风格;核心
默认路径【零网络、零重依赖、离线可跑】,真实协议 SDK 仅经可选 extra 延迟 import。

运行时可把 ragspine 当作一个 Tool / MCP server 在【运行时】组合调用(ADR 0001 D4b),但本包
【不】在包层面依赖 ragspine。详见 CLAUDE.md 宪章与家族 ADR 0001。
"""

from agentspine.agent.agent import Agent, AgentResult, FunctionAgent, LlmAgent
from agentspine.conformance import AGENT_INVARIANTS, TOOL_INVARIANTS
from agentspine.orchestration.coordinator import Coordinator
from agentspine.protocol.a2a.seam import (
    A2AAgent,
    A2AResult,
    A2ATask,
    OfflineA2AStub,
    a2a_agents,
    load_a2a_sdk,
)
from agentspine.protocol.mcp.seam import (
    McpClient,
    McpServer,
    McpTool,
    OfflineMcpStub,
    load_mcp_sdk,
    mcp_clients,
)
from agentspine.tools.tool import CalcTool, EchoTool, Tool, ToolResult

__version__ = "0.0.1"

__all__ = [
    # agent
    "Agent",
    "AgentResult",
    "LlmAgent",
    "FunctionAgent",
    # tools
    "Tool",
    "ToolResult",
    "EchoTool",
    "CalcTool",
    # orchestration
    "Coordinator",
    # protocol: mcp
    "McpClient",
    "McpServer",
    "McpTool",
    "OfflineMcpStub",
    "mcp_clients",
    "load_mcp_sdk",
    # protocol: a2a
    "A2AAgent",
    "A2ATask",
    "A2AResult",
    "OfflineA2AStub",
    "a2a_agents",
    "load_a2a_sdk",
    # conformance (本包绑定的不变量)
    "AGENT_INVARIANTS",
    "TOOL_INVARIANTS",
    "__version__",
]
