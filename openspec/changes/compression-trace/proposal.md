## Why

`context_mgr._compress`（`context_mgr.py`）每次压缩都会就地改写消息序列：切分头/中/尾三层（AR13）、把中段与 `prev_summary` 合并为新累积摘要（AR14）、或在摘要失败时静态降级（AR14 D3）、或在中段为空时退化为不插摘要（AR13 D4）。但**整个过程不留任何痕迹**：一旦压缩发生，运维与排查者无法回答「这次压缩是什么触发的？压缩前后 token / 消息数差多少？哪些消息被保留、哪些进了摘要被丢弃？产出的摘要是哪一条？走的是正常摘要还是降级？」——上下文「被压缩成什么样」对事后排查完全是黑盒。

`docs/capabilities/agent-runtime.md`「上下文压缩增强」明确列出 AR16「**压缩过程可追溯**：每次压缩写入运行日志，记录：触发原因、压缩前后消息数 / token 数、压缩耗时、使用的摘要模型」。

平台已有现成的 trace 出口 `eval_logger`（append-only JSONL，统一 `kind` taxonomy：`agent_run` / `im_message` / `sandbox_exec`），且其既有克制原则是**只记元数据、不落原始大对象**（`log_sandbox_exec` 只记 sizes/timing/exit_code，绝不落 stdout/code 源；`_serialize` 把 base64 图片替换为占位符）。AR16 应复用该出口，新增一类 `kind: "compression"` 的 trace 记录，沿用「只记元数据 / 摘要标识，不落原始消息内容」的克制约束。

## What Changes

- 在 `eval_logger` 新增一个压缩 trace writer（`kind: "compression"`），记录每次压缩的元数据：触发原因、压缩前后 token 数与消息数、保留/丢弃的消息范围（计数）、产出摘要的标识（指纹 + 长度），以及压缩结果类型（正常摘要 / 静态降级 / 无中段退化）、压缩耗时、使用的摘要模型。
- `context_mgr._compress`（及错误触发入口 `compress_for_context_overflow` 的路径）在每次压缩完成（含降级 / 退化分支）后，调用该 writer 写入一条压缩 trace；触发原因（`tmax` 自动 / `manual` 即 `/compact` 的 `force` / `context_overflow` 错误入口）随调用透传。
- agent_loop 调用压缩入口（`maybe_compress` / `compress_for_context_overflow`）时传入 `session_id`（及可选 `user_id` / `agent_name`，有则传、无则 None；CLI 无 session 即 None），随 trigger 一并经调用链透传到 `_compress`，再由 `_compress` 交给 `log_compression` 作为可选归因键写入——令一次 run 内多次压缩的 trace 可按 `session_id` 聚合归因。
- trace **只记元数据与摘要标识**：摘要文本不整段落盘，仅记其指纹（如截断哈希）与长度；保留 / 丢弃以「消息条数 + token 数」表达，不落原始消息对象——与 `eval_logger` 既有克制原则一致。
- 压缩 trace 写入**绝不影响压缩主流程**：trace 写失败只记日志、不向主循环抛异常（压缩本身已是降级安全路径，可追溯能力不得反过来成为新的失败点）。
- 不改压缩算法本身（AR13 分层、AR14 增量摘要 / 降级 / 退化语义全部不动），只在其出口加可观测性。

## Capabilities

### New Capabilities
- `compression-trace`: 上下文压缩过程可追溯（AR16）——每次压缩把元数据（触发原因、压缩前后 token / 消息数、保留与丢弃范围计数、摘要标识与长度、结果类型、耗时、摘要模型）经 `eval_logger` 写入一条 `kind: "compression"` 的 append-only JSONL trace，只记元数据 / 摘要标识不落原始大对象，trace 写入失败不影响压缩主流程。

### Modified Capabilities
<!--
不修改 AR13 `compression-layered-retention` 与 AR14 `compression-incremental-summary` 的既有 spec：
本 change 不改压缩算法语义，仅在压缩出口叠加可观测性，全部以本 change 自有 capability 内的 ADDED 需求承载。
归档顺序建议在 AR13 / AR14 之后（压缩三层 / 增量摘要语义先就位，本 change 仅观测其结果）。
-->
- （无）

## Impact

- **代码**：
  - 扩展 `src/fleetent/eval_logger.py`：新增 `log_compression(...)` writer（`kind: "compression"`），沿用既有 `TRACE_PATH` 单一可注入常量与「只记元数据」原则；不新增持久化结构、不引入新依赖。
  - 修改 `src/fleetent/context_mgr.py`：`_compress` 在每个返回分支（正常摘要 / 静态降级 / 无中段退化）前采集压缩元数据并调用 `log_compression`；触发原因与 `session_id`（及可选 `user_id` / `agent_name`）经 `maybe_compress` / `compress_for_context_overflow` 透传到 `_compress`（触发原因为新增内部参数、归因键为新增可选 kwarg 默认 None，均不改这两个公开入口的 `list → list` 返回语义）；`summary_model` 由 `_compress` 复用 `get_client_and_config("memory_extraction").model` 解析，不改 `_summarize` 签名。
  - 修改 `src/fleetent/agent_loop.py`：调用 `maybe_compress` / `compress_for_context_overflow` 时传入 `session_id`（及可选 `user_id` / `agent_name`），有则传、无则 None。
- **配置**：无新增必填 Settings 字段。
- **测试**：扩展 `tests/test_eval_logger.py`（断言 `log_compression` 写出 `kind: "compression"` 及各元数据字段、不含原始消息 / 摘要正文、写失败不抛）；扩展 `tests/test_context_mgr.py`（断言三类返回分支各写一条压缩 trace 且触发原因 / 前后计数正确）。`TRACE_PATH` `monkeypatch` 到 `tmp_path`；LLM 摘要调用按规范 mock（`patch get_client_and_config`）。
- **不影响**：AR13 分层切分与 `_keep_tail` identity check、AR14 增量摘要 / 降级 / 退化语义、`Tmax`/`Tretained` 触发与目标线、`session_mgr` 持久化、agent_loop 主循环、model fallback；不引入新依赖（无 AI 框架、无 ORM、无云服务）。

## Dependencies

- **`src/fleetent/context_mgr.py`（已实现，AR13/AR14）**：被观测对象。本 change 在其 `_compress` 出口采集元数据，需读取压缩前后的 token / 消息数、头/中/尾切分结果、摘要消息与结果分支。
- **`src/fleetent/eval_logger.py`（已实现）**：trace 出口。本 change 复用其 `TRACE_PATH`、append-only JSONL 写法与统一 `kind` taxonomy，新增 `kind: "compression"`。
- **`src/fleetent/agent_loop.py`（已实现）**：压缩入口的调用方，持有 `session_id`（及 `user_id` / `agent_name`）。本 change 在其调用 `maybe_compress` / `compress_for_context_overflow` 处传入这些归因键，使压缩 trace 可归因到具体 session。
- **AR13 `compression-layered-retention` / AR14 `compression-incremental-summary`**：提供本 change 要追溯的压缩日志结构契约（三层切分、`_SUMMARY_PREFIX` 摘要消息标识、降级 notice、无中段退化）。本 change build on 其语义，不重定义。
