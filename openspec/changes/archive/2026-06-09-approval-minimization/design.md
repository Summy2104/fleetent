## Context

`permission_gate.request_approval`（已合并）对每次 medium/high 调用都联系审批人、等决定。`resolve(approval_id, decision, approver)` 由 server / im_gateway/normalizer / tui 三处调用。`approval_store` 是 ensure_schema-only 的 agent-side 表（不经 alembic）。drift guard 只比对固定 store 列表（traces/memory/reflection/kb/session），且跳过「只在 ensure_schema、无 alembic 对应」的表——故新增纯 agent-side 表无需 migration。

## Goals / Non-Goals

**Goals:**
- 审批人可对一个 (请求者, 工具, 参数) 指纹授予持久「永久允许」，后续相同指纹自动放行。
- 指纹基于服务端规范化参数（反逃逸沿用：参数来自已记录的 tool_args，不同参数不复用）。
- 默认行为不变；不破坏 server/tui 既有 resolve 调用。

**Non-Goals:**
- 不做 allow-always 的管理 UI / 撤销 API（platform 控制面后续薄暴露；本 change 只存 + 查 + 授予 + 列出）。
- 不改 action-gate 路由、不改 run_stream。
- 不做指纹的模糊匹配（精确指纹；参数任一不同即重新审批——安全侧）。

## Decisions

**D1：allow-list 为纯 agent-side ensure_schema 表，不经 alembic。**
`governance/approval_allowlist_store.py`，`CREATE TABLE IF NOT EXISTS approval_allowlist(fingerprint TEXT PRIMARY KEY, scope_key TEXT, tool_name TEXT, created_at TEXT, created_by TEXT)`。与 `approval_store` 同模式（named params、SQLiteDatabase、db_path 可注入）。drift guard 不覆盖（不在其 store 列表；即便覆盖，ensure_schema-only 表被跳过）。规避 migration → 也规避 alembic 多头风险。

**D2：指纹 = sha256(scope_key | tool_name | canonical_json(args))。**
`fingerprint(scope_key, tool_name, tool_args) -> str`，纯函数。canonical = `json.dumps(args, sort_keys=True, separators=(",",":"))`，对键序无关、对值敏感。scope_key = 请求者 user_id（持久跨 session 的「这个用户已确认这条操作」）。不同用户/工具/参数 → 不同指纹，互不复用。

**D3：request_approval 前置查指纹，命中即自动放行。**
计算 fp（scope=requester_user_id）。`allowlist_store.is_allowed(fp)` 命中 → `insert_approval` 后立即 `update_approval(status="auto_approved")` 留审计、log、**return "approved"**，不调 `_notify_approvers`（零打扰）。未命中 → 存 `self._pending[approval_id] = fp` 后照常审批。

**D4：resolve 增 `always: bool=False`，授予持久指纹。**
`resolve(approval_id, decision, approver_user_id, always=False)`。当 `always and decision=="approved"` → `allowlist_store.add_grant(fp, scope_key, tool_name, created_at, created_by=approver)`（fp 从 `self._pending` 取）。默认 False → server/tui 现有调用零变化。

**D5：IM `approve always <id>` 授予。**
`normalizer._APPROVAL_RE` 扩展为 `^(approve|reject)(\s+always)?\s+<id>$`；`approve always <id>` → `resolve(decision="approved", always=True)`。`approve <id>` / `reject <id>` 不变。server/tui 暂不加 always（IM 为主审批通道；后续可加）。

## Risks / Trade-offs

- **scope=user 的过度放行**：一旦用户对某工具+参数授予永久允许，该用户后续相同调用都不再审批。缓解：指纹含**精确参数**（参数变即重新审批）；授予需审批人**显式** `approve always`（默认只批一次）；留审计行（auto_approved）。可接受：这正是「审批最小化」的预期权衡。
- **指纹 scope 选择**：选 user 而非 session（跨 session 持久，最小化更彻底）或 agent（过宽）。user 粒度兼顾最小化与可控。
- **无撤销 API**：本 change 不提供撤销；误授予需手动清表。记为 Non-Goal，platform 后续薄暴露管理面。

## Migration Plan

增量：新表 IF NOT EXISTS；permission_gate 前置查 + resolve 增默认参数，默认路径行为不变。无数据迁移、无 alembic 改动。Rollback：移除前置查与 always 分支、丢弃新表。
