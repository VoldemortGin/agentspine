"""tool 合约:echo / calc 派发 + 结果带 provenance + 算术求值安全。"""

import pytest

from agentspine.tools.tool import CalcTool, EchoTool, Tool, ToolResult


def test_echo_tool_returns_input_with_provenance():
    tool = EchoTool()
    result = tool.run("hello")
    assert isinstance(result, ToolResult)
    assert result.output == "hello"
    assert result.tool == "echo"  # provenance
    assert isinstance(tool, Tool)


@pytest.mark.parametrize(
    ("expr", "expected"),
    [("1+1", "2"), ("2*(3+4)", "14"), ("10/4", "2.5"), ("-3 + 5", "2"), ("2**5", "32")],
)
def test_calc_tool_evaluates_arithmetic(expr, expected):
    result = CalcTool().run(expr)
    assert result.output == expected
    assert result.tool == "calc"  # provenance


def test_calc_tool_rejects_non_arithmetic_code():
    # 只认白名单算术节点;函数调用 / 名字 一律拒绝(绝不触碰任意代码执行)。
    with pytest.raises(ValueError):
        CalcTool().run("__import__('os').system('echo hi')")
