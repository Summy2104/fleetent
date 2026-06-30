## Why

IM 路径上，当 LLM 调用超时（`httpx.ReadTimeout` / `openai.APITimeoutError`）或 agent 运行抛任何异常时，用户会**收不到任何回复，且 Slack 的 "思考中…" loading 状态永不清除**——表现为机器人"卡死在转圈、永远不回话"。这在工具类 turn（需 ≥2 次 LLM 调用）下尤其高发（实测某网关 ~31% 单次调用超时 → 工具 turn >50% 静默失败）。standalone 与 managed 两种 IM 宿主共用同一处理链，问题一致。

根因链（均为确定性控制流，已逐环核实）：
1. `runtime/error_classifier._categorize` 把 LLM 超时归为 `unknown`（`should_retry=False, should_switch_model=False`）→ 不重试、不模型切换，直接抛出。
2. `runtime/loop._run_inner` 捕获 LLM 调用异常仅用于记 trace 后 `raise`（无兜底回帖）；`im_gateway/normalizer.route` 主路径调 `agent_loop.run` 未包 try/except → 异常冒泡至 slack_bolt，仅打印 `Failed to run listener function`，不回任何消息。
3. `im_gateway/slack._make_status_funcs` 的 loading 状态仅在 `reply_func` 内清除；异常路径 `reply_func` 不触发 → 状态永不清。

## What Changes

- **P0（兜底回帖 + 清 loading）**：`im_gateway/normalizer.route` 主路径将 `agent_loop.run(...)` 包入 try/except；异常时经 `msg.reply_func` 回一条用户可见提示（如「⚠️ 处理时出错或超时了，请重试」），从而**同时清除 Slack assistant loading 状态并投递通知**；随后保存本轮会话、记 error 日志、**不再向上冒泡**（catch 后 log，不吞不裸抛）。standalone（agent 自托管 Slack）与 managed（node 托管 Slack，经 agent `/im/route`）共用 `normalizer.route`，**一处修复覆盖两模式**。
- **P1（超时归类为可重试/可切换）**：`runtime/error_classifier` 把 `httpx.ReadTimeout` / `httpx.TimeoutException` / `openai.APITimeoutError` / `openai.APIConnectionError` 归入新的可恢复类别（`should_retry=True, should_switch_model=True`），使瞬时超时被既有的退避重试（`model-transient-retry`）与模型失败转移（`model-fallback`）自动处理，从源头降低静默触发率。
- **P2（LLM client 显式超时 + 重试）**：`runtime/loop._build_async_client` 给 `AsyncOpenAI` 设显式 `timeout`（connect=5 / read=90 / write=10 / pool=5 秒）与 `max_retries=2`，为流式调用设定合理读超时边界并启用 SDK 层重试。

无 BREAKING：仅在既有失败路径上新增兜底与重试，正常成功路径行为不变。

## Capabilities

### New Capabilities
- `im-run-failure-fallback`: IM 路径上当 agent 运行失败（超时/异常）时，必须向用户投递一条可见的失败提示并清除 IM 进度/loading 状态，且失败被记录而非静默吞没；覆盖 standalone 与 managed 两种宿主。
- `llm-client-timeout`: 面向聊天 LLM 的 HTTP client 必须配置显式连接/读/写超时与有界重试，使流式调用的停顿有确定边界。

### Modified Capabilities
- `agent-error-classification`: 新增对 LLM 请求超时/连接错误（`httpx.ReadTimeout`/`TimeoutException`、`openai.APITimeoutError`/`APIConnectionError`）的归类——判定为「可重试且可切换模型」，不再落入 `unknown`。
- `im-progress-feedback`: 状态清除从「仅 agent run 完成路径」扩展为「完成与失败两条路径」——run 因异常失败并经 `reply_func` 投递兜底提示时，同样先清除 loading 状态（消除永久「思考中…」）。

## Impact

**受影响代码**：
- `src/fleetent/im_gateway/normalizer.py`（P0：`route` 主路径兜底）
- `src/fleetent/runtime/error_classifier.py`（P1：`_categorize` + 分类表）
- `src/fleetent/runtime/loop.py`（P2：`_build_async_client`）

**模块边界声明（AGENTS.md 要求）**：
- Owning packages：`im_gateway/`（P0）、`runtime/`（P1、P2）——均为 agent 运行时模块，**MUST NOT import `fleetent.platform.*`**（不新增反向依赖）。
- Public API surface：不新增公开 API；`normalizer.route`、`error_classifier.classify`、`loop` 内部函数签名不变（P0 仅在 route 内部加 try/except；P1 仅扩分类表；P2 仅改 client 构造）。
- Owned tables：无（不涉及任何表/迁移）。
- Config namespace：P2 超时阈值作为模块内可注入常量（便于 monkeypatch 测试），暂不引入新 env/agent.yaml 字段；如需可配置化留作后续。
- Cross-module dependencies：P0 复用 `msg.reply_func`（IM 边界既有注入，clears loading + posts）；P1 复用既有 `model-transient-retry`/`model-fallback` 机制（仅改变分类即生效），不新增跨包调用。
- Migration / shim plan：无 schema/数据迁移；无 shim。

**依赖**：`httpx`、`openai` 已是现有依赖，仅引用其异常类型与 `httpx.Timeout`。

**验证基线**：改动后 agent 仍须能在「无 platform、platform 的 DB 表不存在」环境下完成 `fleetent agent run` 对话（P0/P1/P2 均不触碰 platform）。
