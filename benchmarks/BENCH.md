# spineagent 编排开销基线(BENCH)

`benchmarks/bench_orchestration.py` 给 agent 编排几条核心路径的【机制开销】钉一个可复现基线。
**全程零网络 / 零 key / 零真实 LLM API**:provider 全是脚本化 fake / corespine `MockProvider`,
工具是离线确定性 `CalcTool` / `FunctionTool(echo)`。这不是"真实模型性能"测试(那取决于远端模型、
不可复现),而是衡量 spineagent 自身在工具循环与多 agent 编排上的【纯编排开销】——基线让"某次
改动悄悄把编排变贵"无所遁形。

## 跑(始终从包根)

```bash
make bench
# 或:
.venv/bin/python benchmarks/bench_orchestration.py
```

末行打印 `bench orchestration OK`。

## 量了什么

| # | 路径 | 真实 API | 量的是 |
|---|---|---|---|
| 1 | `ToolUsingAgent.step` | `SyntaxToolPolicy` + `CalcTool`,`$prev` 链式喂回 | 离线确定性工具循环每步开销(1 / 4 / 16 步) |
| 2 | `FunctionCallingAgent.step` | 脚本化 provider 吐 `tool_calls`(OpenAI 形状)+ `FunctionTool` | 真 function-calling 循环每轮开销(1 / 4 / 16 轮) |
| 3 | `Coordinator.run_sequential` vs `run_parallel`(纯 CPU) | `FunctionAgent` 零延迟 | 线程池【纯编排开销】本身(2 / 8 agent) |
| 4 | `Coordinator.run_sequential` vs `run_parallel`(带延迟) | `FunctionAgent` + 固定 `time.sleep(2ms)` | 并行【加速比】(2 / 8 agent) |

路径 3 / 4 是同一对比的两面:CPU-only 暴露"并行不是免费的"(线程池 submit/join 有固定开销),
带延迟暴露"agent 各自等待(IO / 模型)时并行才真正赢"。延迟用 `time.sleep` 制造而非真实 IO——
`sleep` 期间释放 GIL,故线程池真并发,且零网络、确定性、跨平台。

## 基线数字

> 机器:Apple Silicon(arm64),macOS;CPython **3.13.2**。`timeit` 多轮取 min(单次操作)。
> 绝对值随机器/解释器浮动,**关注量级与并行 vs 串行的比值**(下方比值在本机两次跑间 < 10% 抖动)。

### [1] 工具循环 `ToolUsingAgent`(离线确定性)

| 链长 | 单次 step | 摊到每步 |
|---|---|---|
| 1 步 | ~13.7 µs | ~13.7 µs |
| 4 步 | ~47 µs | ~12 µs |
| 16 步 | ~275 µs | ~17 µs |

近似线性:每多一步工具调用 ≈ +15 µs(policy 决策 + `$prev` 替换 + `CalcTool` 求值 + 隐私 trace)。

### [2] function-calling 循环 `FunctionCallingAgent`(脚本化 provider)

| 轮数 | 单次 step | 摊到每轮 |
|---|---|---|
| 1 轮 | ~7.1 µs | ~7.1 µs |
| 4 轮 | ~16.5 µs | ~4 µs |
| 16 轮 | ~53 µs | ~3.3 µs |

每多一轮 `tool_calls` ≈ +3 µs(schema 复用 + OpenAI 形状消息拼装 + 工具 `parse_arguments`/`invoke`
+ 喂回)。比工具循环更便宜:这里 fake provider 是常量返回,真实开销集中在消息编排与工具边界校验。

### [3] Coordinator 串行 vs 并行 —— 纯 CPU

| agent 数 | `run_sequential` | `run_parallel` | 并行/串行 |
|---|---|---|---|
| 2 | ~4.5 µs | ~67 µs | **~15×(并行更慢)** |
| 8 | ~15 µs | ~230 µs | **~15×(并行更慢)** |

纯 CPU、零等待下,`ThreadPoolExecutor` 的建池 / submit / join 固定开销远大于"顺序调几个零成本
agent"。**结论:agent 本身是纯 CPU 快活时,别用并行——串行更省。**

### [4] Coordinator 串行 vs 并行 —— 带人造延迟(每 agent sleep 2 ms)

| agent 数 | `run_sequential` | `run_parallel` | 串行/并行(加速比) | 理想 |
|---|---|---|---|---|
| 2 | ~5.7 ms | ~3.0 ms | **~1.9×** | 2 |
| 8 | ~23 ms | ~3.3 ms | **~7.0×** | 8 |

每个 agent 各自等待(`sleep` 释放 GIL,模拟 IO / 远端模型往返)时,并行接近理想线性加速:
串行总耗时 ≈ n × delay,并行 ≈ delay + 编排开销。**结论:agent 各自阻塞在 IO / 模型调用上时,
并行是大赢——agent 越多、单 agent 等待越久,赢得越多。**

## 一句话拿走

- 工具循环 / function-calling 循环的每步编排开销在 **µs 量级**,相对真实模型一次往返(几十~几千 ms)
  可忽略——编排不是瓶颈,模型才是。
- **并行 vs 串行取决于 agent 在干嘛**:纯 CPU 快活 → 串行(并行约慢 15×);各自阻塞等待 → 并行
  (接近线性加速,本机 8 agent 实测 ~7×)。`Coordinator` 把两种模式都摆上桌,按 agent 的工作形态选。

## 复现说明

- 依赖:仅 `spineagent` 自身 + 兄弟薄核 `corespine` + 标准库 `timeit`/`time`,**无任何 benchmark
  专用依赖**(未动运行时 `dependencies`)。
- 确定性:fake provider 按脚本可重入重放,`CalcTool` 纯函数,`time.sleep` 固定;`timeit` 多轮取 min。
- 量级随机器浮动属正常;关注的是路径 3 / 4 的**比值**与各路径的**量级**,而非绝对纳秒。
