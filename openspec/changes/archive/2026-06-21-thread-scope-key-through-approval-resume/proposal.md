## Why

审批门控的 MCP 工具(尤其 `email__send_email`,恒 medium 审批)在批准后**发附件仍失败**:`Attachment file not found: /workspace/generated/x.png`。这是 #280(stdio 入参 `/workspace`→宿主路径翻译)对**审批恢复路径失效**导致的。

根因:`email__send_email` 是 medium 审批工具,走「挂起 → 人工批准 → 在 resume run 里重新执行」。resume 的 tool_context 在 `im_gateway/normalizer.py:391`(`_resume_pending_in_session`)构建时**漏了 `scope_key`**:

```python
tool_context = ToolContext(
    agent_name=..., session_id=session_id, session_context=...,
    outbound_connectors=..., run_id=..., delivery_ledger=...,
)   # ← 无 scope_key；ToolContext.scope_key 默认 None
```

对比正常回合(`runtime/loop.py:1746/2283`)的 tool_context 都有 `scope_key=_resolve_scope_key(session_id, agent_name)`。于是批准后执行该工具时 `tool_context.scope_key = None` → MCP dispatch 把 `scope_key=None` 透到 `_call_via_session_inner` → #280 的翻译条件 `if scope_key and server.transport == "stdio"` 为假 → 跳过翻译 → email server 收到裸 `/workspace/...` → 找不到文件。

证据(2026-06-21 实测 session `1782036414`):附件连失败 4 次(`/workspace/generated/...`、`/tmp/...`、`/workspace/outbound/...` 全因 server 读不到),最终靠 base64 内嵌 HTML 兜底、6 次审批才发出。`approval-suspend-resume` spec 明示 resume「执行 pending 工具走正常 dispatch 路径(注入 tool_context/connectors)」——但注入的 tool_context 与正常回合不等价(漏 scope_key),违反该意图。

副作用:审批后 MCP 工具产物的 `/exchange` 归属登记(`rewrite_and_register` 同样依赖 scope_key)对这些调用也失效。

## What Changes

- **resume 路径补 scope_key**:`_resume_pending_in_session`(`normalizer.py:391`)构建的 tool_context 增加 `scope_key=<与正常回合同源的解析结果>`,使审批恢复执行的工具与正常回合等价。
- **公开 scope_key 解析函数**:把 `runtime/loop.py` 的私有 `_resolve_scope_key` 提升为公开 `resolve_scope_key`(改名 + 更新 2 处内部调用),作为单一来源供 resume 路径复用,避免跨模块复制逻辑或 import 私有符号。

不动:审批挂起/恢复的其它行为、地址重建、ledger 共享、翻译/登记本身的实现。只补「resume 的 tool_context 带上 scope_key」这一处。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `approval-suspend-resume`:在「Approval resolution resumes the run」要求上明确——批准后重建并注入的 tool_context SHALL 携带与正常回合等价的 **workspace scope key**,使依赖 scope_key 的下游(`/workspace` 入参翻译、`/exchange` 产物归属登记)对审批恢复执行的工具同样生效。

## Impact

**owning package**:agent runtime —— `src/fleetent/im_gateway/normalizer.py`(resume 的 tool_context)+ `src/fleetent/runtime/loop.py`(`resolve_scope_key` 改名公开)。全程 agent runtime 侧,不 import `fleetent.platform.*`。

**public API surface**:`runtime/loop.py` 把 `_resolve_scope_key` 改名为公开 `resolve_scope_key(session_id, agent_name) -> str | None`(im_gateway 已 import `runtime.loop`,跨包调用其公开 API 合规)。`ToolContext` 结构与 dispatch 签名不变。

**owned tables**:无(零 schema、零迁移)。

**config namespace**:无。

**cross-module dependencies**:`im_gateway/normalizer.py` 经已有的 `from fleetent.runtime import loop as agent_loop` 调用公开 `resolve_scope_key`(同 `_get_manager` 等既有跨包用法)。不触碰 agent↔platform 边界。

**migration / shim plan**:`_resolve_scope_key` 仅 loop.py 内部使用(无测试 patch、无外部引用),直接改名,无需保留 shim。

**受影响代码**:`runtime/loop.py`(改名 + 2 处调用)、`im_gateway/normalizer.py`(resume tool_context 加 scope_key);测试 `tests/unit/test_normalizer_approval_resume.py`(新增「resolve_scope_key 公开」「resume tool_context 带 scope_key」用例)。
