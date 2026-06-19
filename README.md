# agentspine

Spine 家族的**通用多 agent 协作框架**(见 [ADR 0001](../docs/adr/0001-spine-family-boundaries-and-dependency-direction.md))。
agent / tool / 编排 + **MCP / A2A** 等 agent 协议缝。依赖薄核 `corespine`,复用其缝元模式与
observability / config 形状;**默认路径离线可跑、import-clean、零网络 SDK**。

> 通用 ≠ 地基。真正的核是更薄的 `corespine`,agentspine 是它的兄弟消费者,**不**含任何 RAG 概念。
> 详见 [`CLAUDE.md`](CLAUDE.md) 宪章。

## 缝的元模式(家族统一)

每条缝都长一个样,核心 import 零 SDK、离线可跑:

**Protocol + 离线确定性默认 + `Registry` 工厂 + 参数化 conformance**

## 里面有什么

| 模块 | 原语 |
|---|---|
| `agent/agent.py` | `Agent` 协议 + `LlmAgent`(走 corespine `LLMProvider`,离线用 `MockProvider`)/ `FunctionAgent`(纯函数节点);步级 trace 只记元数据 |
| `tools/tool.py` | `Tool` 协议 + `EchoTool` / `CalcTool`(安全算术求值);结果带 provenance。**运行时可把 ragspine RAG 插为一个 Tool**(见下) |
| `orchestration/coordinator.py` | `Coordinator`:把多个 agent **顺序或并行**跑同一任务、保序收集 `AgentResult` |
| `protocol/mcp/seam.py` | `McpClient` / `McpServer` 协议 + `OfflineMcpStub`(进程内回环)+ 真实 SDK 经 `[mcp]` extra 延迟 import |
| `protocol/a2a/seam.py` | `A2AAgent` 协议 + `OfflineA2AStub`(进程内回环)+ 真实 `a2a-sdk` 经 `[a2a]` extra 延迟 import |
| `conformance.py` | 本包绑定的不变量:`AGENT_INVARIANTS`(步产出 / provenance / 隐私 trace)、`TOOL_INVARIANTS`(结果 provenance) |

## 运行时组合 ragspine(ADR 0001 D4b)

agentspine **不**在包层面依赖 ragspine。但可在**运行时**把 ragspine 的 RAG 检索包成一个实现了
`Tool`(或 MCP server)协议的适配器,插给某个 agent 调用——松耦合、可选,方向只能 agentspine→ragspine。
本包 `dependencies` 永远不含 ragspine,也绝不在默认路径 import 它。

## 本地开发(始终从包根)

```bash
uv venv .venv
VIRTUAL_ENV="$(pwd)/.venv" uv pip install -e ../corespine
VIRTUAL_ENV="$(pwd)/.venv" uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/python -c "import agentspine"
```

## 30 秒上手

```python
from corespine import MockProvider, InProcessPrivacyTraceSink
from agentspine import LlmAgent, FunctionAgent, Coordinator, EchoTool, OfflineMcpStub
from agentspine.protocol.mcp.seam import McpTool

# 一个离线 agent:走 corespine 的确定性 MockProvider,跑单步
agent = LlmAgent("planner", MockProvider())
print(agent.step("列个计划").output)            # 确定性、可复现

# 多 agent 编排:顺序 / 并行跑同一任务,保序收集
coord = Coordinator([FunctionAgent("a", lambda t: f"a:{t}"),
                     FunctionAgent("b", lambda t: f"b:{t}")])
print([r.output for r in coord.run_parallel("go")])   # ['a:go', 'b:go']

# 工具:带 provenance 的结果
print(EchoTool().run("hi").tool)                # 'echo'

# MCP 离线回环:注册 + 调用,零网络
stub = OfflineMcpStub()
stub.register_tool(McpTool("upper"), lambda a: {"result": a["s"].upper()})
print(stub.call_tool("upper", {"s": "hi"}))     # {'result': 'HI'}

# 隐私 trace:步级只记元数据;塞正文会被 corespine 的 sink 直接拒绝
sink = InProcessPrivacyTraceSink()
agent.step("敏感任务", trace=sink)               # 只记 agent 名 / 长度 / token 数
```
