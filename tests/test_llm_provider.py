"""LLM provider 适配层合约:Anthropic / OpenAI 兼容适配器的 chat 映射(含 tool-calling)+ Registry。

离线:注入 fake client 验证「messages 构造 + 响应映射 + tool_calls」,绝不真连网络;真实 SDK 路径
只是延迟 import。规范 tools 形状 = OpenAI function-tool;Anthropic 适配器负责转换。
"""

import importlib.util
from types import SimpleNamespace

import pytest
from corespine.llm.provider import ChatResult, LLMProvider, Message, MockProvider, ToolCall

from agentspine.agent.agent import LlmAgent
from agentspine.llm.provider import (
    AnthropicProvider,
    OpenAICompatProvider,
    llm_providers,
    load_anthropic_sdk,
    load_openai_sdk,
)

_OPENAI_TOOL = {
    "type": "function",
    "function": {"name": "calc", "description": "算术", "parameters": {"type": "object"}},
}


# ---- fake 官方 SDK client(只实现适配器用到的最小面)-------------------------------------


class _FakeAnthropic:
    """伪 anthropic 客户端:messages.create 回 content blocks(给 tools 则回 tool_use)+ usage。"""

    def __init__(self) -> None:
        self.messages = self

    def create(self, *, model, max_tokens, system, messages, tools=None, **extra):
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        self.last = SimpleNamespace(model=model, system=system, messages=messages, tools=tools)
        if tools:
            content = [SimpleNamespace(type="tool_use", id="tu1", name="calc", input={"expr": user})]
        else:
            content = [
                # 非文本块带【非空】正文:适配器若不按 type 过滤就会把它拼进输出、被测试抓住。
                SimpleNamespace(type="thinking", text="THINK_LEAK"),
                SimpleNamespace(type="text", text=f"A[{system}]{user}"),
            ]
        return SimpleNamespace(
            content=content, usage=SimpleNamespace(input_tokens=len(user), output_tokens=7)
        )


class _FakeOpenAI:
    """伪 openai 客户端:chat.completions.create 回 message.content(给 tools 则回 tool_calls)+ usage。"""

    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=self)

    def create(self, *, model, messages, max_tokens, tools=None, **extra):
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next(m["content"] for m in messages if m["role"] == "user")
        self.last = SimpleNamespace(model=model, messages=messages, tools=tools)
        if tools:
            tc = SimpleNamespace(
                id="tc1", function=SimpleNamespace(name="calc", arguments='{"expr": "1+1"}')
            )
            message = SimpleNamespace(content=None, tool_calls=[tc])
        else:
            message = SimpleNamespace(content=f"O[{system}]{user}", tool_calls=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=SimpleNamespace(prompt_tokens=len(user), completion_tokens=9),
        )


def _msgs(system: str, user: str) -> list[Message]:
    out = []
    if system:
        out.append(Message("system", system))
    out.append(Message("user", user))
    return out


# ---- Anthropic 适配器 ------------------------------------------------------------------


def test_anthropic_chat_maps_text_blocks_and_usage():
    result = AnthropicProvider(client=_FakeAnthropic()).chat(_msgs("你是助手", "你好"))
    assert isinstance(result, ChatResult)
    assert result.text == "A[你是助手]你好"  # 只取 text block,thinking 非空块被跳过
    assert result.usage == {"input_tokens": 2, "output_tokens": 7}
    assert result.tool_calls == ()


def test_anthropic_separates_system_from_conversation():
    fake = _FakeAnthropic()
    AnthropicProvider(client=fake).chat([Message("system", "sys"), Message("user", "q")])
    assert fake.last.system == "sys"  # system 单独传(Anthropic 原生形状)
    assert fake.last.messages == [{"role": "user", "content": "q"}]


def test_anthropic_maps_tool_use_to_tool_calls_and_converts_tool_schema():
    fake = _FakeAnthropic()
    result = AnthropicProvider(client=fake).chat(_msgs("", "算 1+1"), tools=[_OPENAI_TOOL])
    assert result.tool_calls == (ToolCall(id="tu1", name="calc", arguments={"expr": "算 1+1"}),)
    # OpenAI function-tool → Anthropic input_schema 形状
    assert fake.last.tools == [{"name": "calc", "description": "算术", "input_schema": {"type": "object"}}]


def test_anthropic_satisfies_llm_provider_protocol():
    assert isinstance(AnthropicProvider(client=_FakeAnthropic()), LLMProvider)


# ---- OpenAI 兼容适配器 ------------------------------------------------------------------


def test_openai_chat_maps_content_and_usage():
    result = OpenAICompatProvider("gpt-x", client=_FakeOpenAI()).chat(_msgs("role", "hi"))
    assert result.text == "O[role]hi"
    assert result.usage == {"input_tokens": 2, "output_tokens": 9}
    assert result.tool_calls == ()


def test_openai_passes_messages_through_natively():
    fake = _FakeOpenAI()
    OpenAICompatProvider("gpt-x", client=fake).chat(_msgs("", "hi"))
    assert fake.last.messages == [{"role": "user", "content": "hi"}]  # 无 system 时不塞空 system


def test_openai_maps_tool_calls_parsing_json_arguments():
    result = OpenAICompatProvider("gpt-x", client=_FakeOpenAI()).chat(_msgs("", "x"), tools=[_OPENAI_TOOL])
    assert result.text == ""  # 工具调用时 content 为 None -> ""
    assert result.tool_calls == (ToolCall(id="tc1", name="calc", arguments={"expr": "1+1"}),)


def test_openai_satisfies_llm_provider_protocol():
    assert isinstance(OpenAICompatProvider("gpt-x", client=_FakeOpenAI()), LLMProvider)


# ---- 与 LlmAgent 集成(provider 即「统一 invoke = chat」)------------------------------


def test_providers_drive_llm_agent():
    agent = LlmAgent("worker", AnthropicProvider(client=_FakeAnthropic()), system="sys")
    result = agent.step("任务")
    assert result.agent == "worker"  # provenance
    assert result.output == "A[sys]任务"

    agent2 = LlmAgent("w2", OpenAICompatProvider("m", client=_FakeOpenAI()))
    assert agent2.step("任务2").output == "O[]任务2"


# ---- Registry(离线默认 mock + 真实后端 anthropic / openai)------------------------------


def test_registry_makes_mock_default():
    provider = llm_providers.make("mock")
    assert isinstance(provider, MockProvider)
    assert provider.chat(_msgs("", "x")).text  # 离线确定性,非空


def test_registry_makes_real_providers_with_injected_client():
    a = llm_providers.make("anthropic", client=_FakeAnthropic())
    o = llm_providers.make("openai", model="m", client=_FakeOpenAI())
    assert isinstance(a, AnthropicProvider)
    assert isinstance(o, OpenAICompatProvider)
    assert a.chat(_msgs("", "hi")).text == "A[]hi"
    assert o.chat(_msgs("", "hi")).text == "O[]hi"


def test_registry_lists_all_names():
    names = llm_providers.names()
    assert {"mock", "anthropic", "openai"} <= set(names)
    assert llm_providers.group == "corespine.llm"  # 第三方 provider 的 entry-point group


def test_registry_unknown_spec_lists_available():
    with pytest.raises(ValueError) as ei:
        llm_providers.make("nope")
    msg = str(ei.value)
    assert "mock" in msg and "anthropic" in msg and "openai" in msg


# ---- 缺 extra 时延迟 import 给友好报错(仅当 SDK 确实未安装时断言)----------------------


@pytest.mark.skipif(
    importlib.util.find_spec("anthropic") is not None, reason="anthropic 已安装,无法验证缺失报错"
)
def test_anthropic_missing_extra_gives_friendly_error():
    with pytest.raises(ImportError) as ei:
        load_anthropic_sdk()
    assert "pip install agentspine[anthropic]" in str(ei.value)


@pytest.mark.skipif(
    importlib.util.find_spec("openai") is not None, reason="openai 已安装,无法验证缺失报错"
)
def test_openai_missing_extra_gives_friendly_error():
    with pytest.raises(ImportError) as ei:
        load_openai_sdk()
    assert "pip install agentspine[openai]" in str(ei.value)
