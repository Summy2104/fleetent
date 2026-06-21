# Design — thread-scope-key-through-approval-resume

## 问题精确化

| 事实 | 位置/证据 |
|---|---|
| `ToolContext.scope_key` 默认 `None` | `tools/registry.py`:`scope_key: str \| None = None` |
| 正常回合 tool_context 带 scope_key | `runtime/loop.py:1746` / `2283`:`scope_key=_resolve_scope_key(session_id, agent_name)` |
| resume 的 tool_context **漏** scope_key | `im_gateway/normalizer.py:391`(`_resume_pending_in_session`)无 `scope_key=` |
| resume 把该 tool_context 透传执行 | `normalizer.py:439` → `resume_pending_approval(tool_context=...)` → `approval_resume.py:48` `dispatch(..., tool_context=tool_context)` |
| MCP dispatch 读 `tool_context.scope_key` | `tools/registry.py:333` / MCP `call()` wrapper |
| #280 翻译条件依赖 scope_key | `mcp/client.py`:`if scope_key and server.transport == "stdio"` |

链路:email 恒 medium 审批 → resume 执行 → `scope_key=None` → 翻译跳过 → server 收到裸 `/workspace/...` → 失败。

## 决策

### D1. 修复点：resume 的 tool_context 补 scope_key（最小、对症）
在 `_resume_pending_in_session`(`normalizer.py:391`)的 ToolContext 增加:
```python
scope_key=agent_loop.resolve_scope_key(session_id, agent.name if agent else None),
```
- `agent_loop` 已在该函数内 import(`from fleetent.runtime import loop as agent_loop`,且 402 行已用 `agent_loop.run`)。
- `agent.name if agent else None` 与该 tool_context 的 `agent_name` 取值一致。
- 解析逻辑与正常回合**完全同源**(同一函数),不复制、不发散。

### D2. 把 `_resolve_scope_key` 提升为公开 `resolve_scope_key`
现状私有(`runtime/loop.py:286`),仅 loop.py 内部 2 处用,无测试 patch、无外部引用 → 直接改名为公开 `resolve_scope_key`,更新 2 处调用。理由:
- 跨模块调用必须走 public API（仓库风格:不得 import 他模块私有实现）。im_gateway 调 `agent_loop.resolve_scope_key` 是合规的公开调用。
- 单一来源:resume 与正常回合共用同一解析,语义保证一致(session 域→session_id；agent 域→agent_name；manager 不可用→回退 session_id)。
- 无需 shim:无外部依赖旧名。

### D3. 不改 dispatch / 翻译 / 登记本身
#280 的翻译、`/exchange` 登记都已正确,只是因 scope_key=None 而空转。补上 scope_key 后它们自然生效——本 change 不碰它们的实现,blast radius 最小。

## 测试策略（unit，复用 test_normalizer_approval_resume.py 的 _resume_env）

现有 `_resume_env` fixture 已 mock `session_mgr` / `approval_router` / `resume_pending_approval`(AsyncMock,捕获调用)/ agent_config,并以 `normalizer.route(msg)` 驱动到 `_resume_pending_in_session`。

1. **`test_resolve_scope_key_is_public`**:`from fleetent.runtime import loop`;断言 `hasattr(loop, "resolve_scope_key")` 且对 session 域返回 session_id 类值。RED（改名前无此属性）→ GREEN。
2. **`test_resumed_tool_context_carries_scope_key`**:`monkeypatch.setattr(agent_loop, "resolve_scope_key", lambda sid, an: f"SK::{sid}")`（隔离值、不依赖 manager 实际 scope），`route(msg)` 后断言 `resume.await_args.kwargs["tool_context"].scope_key == "SK::<session_id>"`。RED（现状 scope_key=None）→ GREEN（normalizer 接线后）。
   - 该测试需 `resolve_scope_key` 先存在才能 monkeypatch → task 顺序：先改名(task 2)再接线(task 3)。

## 可观测信号

修复后:审批批准 `email__send_email`(带 `/workspace/...` 附件)→ `_call_via_session_inner` 收到非空 scope_key → 翻译为 `<host_workspace_dir>/...` → email server 读到文件 → 发送成功,不再 4 次「Attachment file not found」、不再被迫 base64 兜底。google-drive 上传同理。
