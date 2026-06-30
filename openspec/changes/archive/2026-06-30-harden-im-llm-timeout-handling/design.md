## Context

IM 路径上 LLM 超时/异常会导致「无回复 + Slack loading 永不清除」。已逐环核实控制流（确定性，无需实测）：

- `runtime/error_classifier._categorize`：仅识别 `TimeoutError`（asyncio 工具超时）与 `APIStatusError`（带状态码）；`httpx.ReadTimeout` / `openai.APITimeoutError` 落 `unknown`（`should_retry=False, should_switch_model=False`）。
- `runtime/loop._stream_policy_chat`：`if not classify(exc).should_switch_model: raise` → 超时直接抛、不重试不切换。
- `runtime/loop._run_inner`（~2178）：`except Exception: _log_run_error(...); raise` → 仅记 trace 后重抛，无兜底回帖。
- `im_gateway/normalizer.route`（~761）：`response = await agent_loop.run(...)` 无 try/except → 异常冒泡到 IM 适配器（slack_bolt 仅打印 "Failed to run listener function"）。
- `im_gateway/slack._make_status_funcs`：loading 状态仅在 `reply_func` 内清除（`setStatus(status="")`）；异常路径 reply_func 不触发 → 状态不清。
- standalone 与 managed 共用 `normalizer.route`（managed 经 node `im_edge._forward_inbound` → agent `/im/route` → 同一 `normalizer.route`）。

约束：`im_gateway/`、`runtime/` 均为 agent 运行时模块，MUST NOT import `fleetent.platform.*`；不得引入不可注入的全局可变状态；catch 后必须 log 或 re-raise。

## Goals / Non-Goals

**Goals:**
- IM 路径任何 agent 运行失败都给用户可见反馈，并清除 loading 状态（P0）。
- LLM 瞬时超时被自动重试/模型切换，降低失败发生率（P1）。
- 聊天 LLM client 有确定的超时边界与有界重试（P2）。
- 一处修复同时覆盖 standalone 与 managed。

**Non-Goals:**
- 不改长程任务/重启恢复语义（重启补发/状态清除留作后续 change，见 Open Questions）。
- 不新增 env / agent.yaml 配置字段（超时阈值先用模块内可注入常量）。
- 不改正常成功路径行为；不动 platform 侧任何代码。
- 不替换 LLM 模型/网关（模型选型是另一议题）。

## Decisions

**D1（P0 兜底位置）= 在 `normalizer.route` 包 `agent_loop.run`，而非 `run()` 内部。**
- 理由：`normalizer.route` 是 IM 边界、`msg.reply_func` 在此可用且天然清 loading；standalone/managed 共用此函数，一处覆盖两模式。`run()` 还服务 TUI/CLI（无 IM reply 语义），不宜在通用层注入 IM 兜底。
- 备选：在 `_run_inner` 内兜底——否决，run() 非 IM 专属，且需把 reply_func 语义下沉，污染通用循环。

**D2（P0 catch 后 log 且不再 raise）。**
- 理由：已向用户兜底回帖即"已处理"，再 raise 会触发 IM 适配器的未处理 listener 失败（无意义噪声）。以 error 日志满足「不吞异常」。
- 同时 `await session_mgr.save(...)`，避免失败轮丢失用户输入（与成功路径一致）。

**D3（P1 新增 `llm_timeout` 分类码，而非复用 `rate_limit`/`unknown`）。**
- 理由：语义清晰、可独立挂标志位（`should_retry=True, should_switch_model=True, should_compress=False`），并复用既有 `model-transient-retry`（退避重试）与 `model-fallback`（模型切换），改分类即生效，无需改主循环逻辑。
- 备选：直接在 `_stream_policy_chat` 里 `isinstance` 判超时——否决，违反「主循环只读标志位、不重复解析异常」既有要求（见 agent-error-classification spec）。

**D4（P2 显式 `httpx.Timeout` + `max_retries`，阈值为模块内可注入常量）。**
- 理由：给流式调用 chunk 间停顿设有限 read 超时（90s）并启用 SDK 层重试（2 次），与 P1 互补（P1 在应用层、P2 在 SDK 层）。常量便于测试 monkeypatch。

**修复后链路**：LLM 超时 → `llm_timeout`（P1）→ SDK 重试（P2）+ 应用层退避/切换（P1）→ 仍失败 → `_run_inner` 抛出 → `normalizer.route` 兜底（P0）回帖 + 清 loading + 存会话 + log。

## Risks / Trade-offs

- [P0 兜底可能掩盖真实 bug] → 仍写 error 日志 + 保留 trace 的 `_log_run_error`，可观测；兜底只面向用户，不丢失诊断。
- [P1 把超时设为可切换，单模型路由时切换无目标] → 既有 `_policy_candidates`/fallback 在无备用时回到原 target 重试，行为安全；retry 上限由 `_MAX_TRANSIENT_RETRIES` 控制，不会无限。
- [P1 重试放大慢请求耗时] → 重试有上限（2）+ P2 的 read 超时（90s）封顶单次，最坏总时延有界。
- [P2 read=90s 仍可能短于超大上下文的合理生成时间] → 取值保守可调（常量），后续可按 agent 上下文规模（实测 ~30k tokens）调优；本 change 先消除"无界/默认不一致"。
- [reply_func 自身抛错（如 Slack API 失败）] → 兜底回帖用 `contextlib.suppress` 包裹，二次失败不再抛、不影响 log 与 return。

## Migration Plan

无 schema/数据迁移、无 shim。纯行为增强：
- 部署：随 agent 运行时发布即生效（standalone 与 node 拉起的 agent 均用同一 `runtime`/`im_gateway`）。
- 回滚：还原三处代码改动即可；无状态/数据残留。
- 验证基线：改动后 agent 仍能在无 platform、platform 表不存在环境下完成 `fleetent agent run` 对话。

## Open Questions

- 长程任务/重启恢复时主动补发与清 loading（P3）是否纳入：本 change 不含，建议另起 change（涉及 `session-restart-recovery` 与 IM 地址 replier 的重投递语义）。
- P2 超时阈值是否提升为 agent.yaml 可配置字段：暂不，先常量；若运维需要再做 `model-parameter-config` 扩展。
