## Context

P1–P3 已建立引擎、pre/post_tool_use、output_transform、on_user_input、pre_llm_call、on_assistant_reply。P4 补全压缩生命周期和 run/session 生命周期。

## Goals / Non-Goals

**Goals:** pre_compact（注入）+ post_compact（观测）+ on_run_complete（观测）+ session_start/session_end（IM 路径）。无新 agent.yaml 字段，复用 P1 引擎契约。

**Non-Goals:** `agent_app.py` 的 session 生命周期（CLI 单轮，无会话持久化语义）。

## Decisions

### D1：pre_compact / post_compact 落在 _gated_compress 周围

`run()` 主循环里 `_gated_compress` 是同步调用：

```python
_compressed, flap_state = _gated_compress(messages, flap_state, ...)
messages[:] = _compressed
```

在此两侧加 async dispatch：
- `pre_compact` before：payload `{message_count: len(messages)}`，`inject_context`→`messages.append({"role": "user", "content": inject_context})` 在压缩前（使注入内容进入压缩输入，运维方可用于标记"必保留"段）
- `post_compact` after：payload `{messages_before: len_before, messages_after: len(messages)}`，纯观测

`run_stream()` 同位置相同处理。

### D2：on_run_complete 在 _record_agent_run_completed 之后

`run()` 末尾已有 `_record_agent_run_completed(...)` + `extract_and_update(...)`。`on_run_complete` 在 `_apply_output_transform` 之后、`return reply` 之前 dispatch，payload `{reply, stop_reason_name: stop_reason.name if stop_reason else "normal"}`；纯观测。run_stream 路径不加（流式无单一 stop_reason 汇聚点，且 run_stream 无 extract_and_update 等对称结构）。

### D3：session_start / session_end 在 normalizer.route 的会话锁内

`session_start`：`history = await session_mgr.load(session_id)` 之后，`history.insert(0, system)` 之前。payload `{session_id, user_id, message_count: len(history)}`；`inject_context`→在 history 末尾（user 消息前）追加一条 `{"role": "user", ...}`（企业上下文、session 级策略）。

`session_end`：`agent_loop.run(...)` 返回之后、`session_mgr.save(...)` 之前。payload `{session_id, user_id, reply}`；纯观测（审计/通知）。

两者均 fail-open（`strict=False`），hook 异常不影响 session。
