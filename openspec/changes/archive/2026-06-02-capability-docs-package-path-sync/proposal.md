## Why

近期已经完成多轮 package migration：

- admin CLI -> `fleetent.platform.admin_cli`
- governance -> `fleetent.governance`
- integrations -> `fleetent.integrations`
- memory -> `fleetent.intelligence.memory`

后续 legacy shim cleanup 也已经删除了对应顶层兼容入口，例如 `memory_layer.py`、`mcp_client.py`、
`sandbox_client.py`、`permission_gate.py`、`agent_policy.py` 和 `admin.py`。

代码和 OpenSpec specs 已经形成新的 canonical package 边界，但部分 capability docs 和总架构文档仍使用旧的
legacy 平铺模块名，例如 `memory_layer`、`mcp_client`、`sandbox_client`、`permission_gate`。

这些旧名字现在容易造成两个问题：

- 读者误以为 legacy path 仍是主要实现位置。
- 文档继续引用已经删除的 import path 或文件名。

本 change 只同步文档命名和模块路径，不修改代码。

## What Changes

- 更新 `docs/architecture.md` 的架构图、模块清单和数据流说明，使用 canonical package 名称。
- 更新 capability docs 中的 package / dependency / public API 表述：
  - `docs/capabilities/memory.md`
  - `docs/capabilities/long-term-ctx.md`
  - `docs/capabilities/reflection.md`
  - `docs/capabilities/vector-store.md`
  - `docs/capabilities/mcp.md`
  - `docs/capabilities/sandbox.md`
  - `docs/capabilities/governance.md`
  - `docs/capabilities/tools.md`
  - `docs/capabilities/connectors.md`（如仍提到 MCP client legacy path）
  - `docs/capabilities/im-gateway.md`（如仍提到 permission gate legacy path）
  - `docs/capabilities/platform.md`（如仍提到 admin CLI legacy entrypoint）
- 保留 `docs/archive/**` 历史记录不改。
- 保留 OpenSpec archive 历史记录不改。
- 当前 docs 不再把已删除 legacy path 描述为主要实现位置。

## Out of Scope

- 不修改 Python 代码。
- 不删除 shim。
- 不新增或修改数据库 schema。
- 不修改 capability 功能范围。
- 不修改 OpenSpec archive 历史记录。
- 不重写 capability docs 的完整产品规划。
- 不改 owner 分工和状态定义，除非路径同步暴露明显错误。
- 不恢复任何 legacy shim。

## Module Boundary Impact

- **Owning package**：none，文档同步 change。
- **Public API surface**：不改变代码 public API；文档改为引用 canonical public API。
- **Owned tables**：无。
- **Config namespace**：无。
- **Cross-module dependencies**：只更新文档中的依赖名称，不改变实际 import。
- **Migration / shim plan**：文档应把 canonical package 作为当前实现位置；已删除 legacy shim 不得再被描述为当前 public API。
