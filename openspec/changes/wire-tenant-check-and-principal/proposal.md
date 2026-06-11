## Why

#4 Identity 端口落地后，`agent_app` 定义了跨主体访问校验函数 `_check_tenant(principal, agent_tenant)`，但**全仓零调用**——`/chat`、`/ws` 拿到 `Principal` 后直接进入运行，从不校验请求者主体是否匹配 agent 归属主体。当前单主体（全 `default`）下它恒为 no-op，但**多主体一上线就是静默放行的跨主体访问漏洞**：物理数据隔离（按 agent 归属主体路由，见 `tenant-scoped-db-routing`）仍在，但"谁能对哪个 agent 说话"无人把关。趁上下文热乎堵住这个"忘了接线"的陷阱。

同时 `identity-port` 已要求「核只消费 Principal」「sub-agent / 回合内调用继承父/会话 Principal」，但代码有三处未达标：sub-agent 构造 `parent_principal` 把 `tenant_id` 写死 `"default"`（`loop.py:676`）、TUI `dispatch` 传裸 `user_id` 而非 Principal、`invoke_agent` 工具调子 agent 不透传 Principal。多主体下这些会让身份/主体信息断链。

## What Changes

- **新增 edge 跨主体访问校验**：`/chat`、`/ws`（及等价 agent 入口）在运行前 SHALL 调用跨主体校验——请求者 `Principal.tenant_id` 与目标 agent 归属主体（`agent_tenant`）不符则拒（default-closed）。单主体（双方均 `default`）放行，保持现状无感。
- **修复 sub-agent 主体继承**（达成 `identity-port` 既有「继承」要求）：sub-agent / 回合内内部调用 SHALL 继承父/会话 `Principal` 的 `tenant_id`，移除 `loop.py` 中写死的 `tenant_id="default"`。
- **edge 全程传 Principal**：TUI `Connection` / `dispatch` SHALL 携带并透传 `Principal`（而非裸 `user_id`）；`invoke_agent` 工具 SHALL 把当前 `Principal` 透传给被调 agent run。消除 principal-less 的 `user_id` fallback 在 edge 路径被命中。

## Capabilities

### New Capabilities
- `cross-tenant-access-guard`: edge 在运行 agent 前校验请求者 `Principal.tenant_id` 与目标 agent 归属主体一致，不符 default-closed 拒绝（物理隔离之上的访问准入层）。

### Modified Capabilities
- `identity-port`: 强化「继承 / 核只消费 Principal」的可验证场景——明确 sub-agent 继承父 Principal 的 `tenant_id`（不写死 `default`）、TUI 与 `invoke_agent` 等 edge / 内部调用全程传 Principal（不走 principal-less `user_id` 路径）。

## Impact

- **代码**：`runtime/agent_app.py`（`/chat`、`/ws` 接入 `_check_tenant`）、`runtime/loop.py`（sub-agent `parent_principal` 继承父 tenant，约 `:676`）、`tui/dispatch.py`（`Connection` 持 Principal、`run_stream` 传 Principal）、`tools/builtin_tools.py`（`invoke_agent` 透传 Principal）。
- **依赖**：`identity.Principal`；agent 归属主体取自 agent 配置（`agent_tenant`，与 `tenant-scoped-db-routing` 同源），不耦合 `long_term_ctx`。
- **owned tables**：无；**config namespace**：无；**migration / shim**：无（纯行为变更）。
- **当前影响面**：单主体 Pilot 下行为不变（校验恒 True、继承值即 `default`）；价值在多主体上线前消除静默漏洞与身份断链。
- **不在本切片**：多主体 fan-out 路由本身（已由 `tenant-scoped-db-routing` 覆盖）；OIDC/外部 IdP 适配器。
