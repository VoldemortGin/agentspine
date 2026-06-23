"""LLM provider 调用的统一边界异常(vendor 网络/超时/API 异常归一到此)。

各真实适配器(Anthropic / OpenAI / Cohere / Gemini / Bedrock)的 SDK 调用点用 try/except 把
【vendor 抛出的网络/超时/API 异常】归一成 `ProviderError`,给上层一个稳定、可 grep 的边界异常,
而非五花八门的 SDK 私有异常类型。

【只归一 vendor 运行时故障,绝不兜底程序错】:KeyError / TypeError / AttributeError 这类
逻辑 bug 照常向上抛出——不退化成 except Exception 兜底,以免韧性外衣掩盖真正的代码缺陷。

rule-of-three 已触发:ragspine 与 spineagent 两个消费者重复同一块稳定面(同继承
corespine.CorespineError、同 code="provider.error"),据此把 ProviderError 提上了
corespine 0.1.1。本模块改为【从 corespine 再导出】,保留 `spineagent.llm.errors.ProviderError`
这一历史导入路径向后兼容;不再在本地定义。
"""

from __future__ import annotations

from corespine import ProviderError

__all__ = ["ProviderError"]
