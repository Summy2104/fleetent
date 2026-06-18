## Context

`slim-admin-cli` 删除前提审查（2026-06-18）确认 4 块 API 缺口。本 design 给出每块的补齐方案。两块（observability 端点形状、default-agent 控制面模型）是架构判断点，需在写 specs 前定稿。

现状关键事实（已核实代码）：
- `agent_statistics/stats_admin_api.py:32-54`：`fetch_traces`/`fetch_approvals`/`agent_allowed_tools`/`pricing_table` 全是 `return []`/`return None` 占位桩。
- `fleetent.observability` 公共 API 提供 `query_trace_events(TraceQuery)`、`get_usage_summary(UsageQuery)`、`get_performance_summary(...)`——CLI `observability` 三命令直接用它们，数据真实。
- `user_store.create_user(name)`（user_store.py:82）建用户即签发 `ma-` key，scope `["*"]`，明文一次性返回。`create_web_user`（:320）建 web 用户、需 email、不发 key。
- `user_store.rotate_key(user_id)`（:已核实）撤销该 user 全部 active key + 发新 key，明文一次性返回。无 HTTP 路由调用它。
- default-agent 解析：`agent_config.AgentConfigIndex.default` 在 scan agent.yaml 时由各文件的 `bindings.default` 标记求出（zero-DB 文件索引）。CLI `set-default-agent` 直编 agent.yaml 文件。
- `agent_admin_state` 是管理表（Alembic 权威），现有列 status/provenance/drift/archived_at/updated_at。
- materialize 路径（`agent_lifecycle/materialize.py`）从 agent_store + admin state 产出 agent.yaml 内容下发给 node。

## Goals / Non-Goals

**Goals:**
- 补齐 observability / service-principal / rotate-key / default-agent 四块 HTTP API，使对应 4 + 2 条 CLI 命令真正有等价 HTTP 路径。
- observability HTTP API 保留 CLI 的全部过滤维度（不能只给 dashboard 聚合）。
- default-agent 改为与目标架构一致的控制面属性。

**Non-Goals:**
- 删除任何 CLI 命令（由 `slim-admin-cli` 在本 change 落地后做）。
- 重构 observability 存储层或 trace schema。
- 给新端点做 UI（按需后续）。
- 改 node 侧 scan 逻辑（node 继续从 agent.yaml 的 `bindings.default` 读默认，不变）。

## Decisions

### D1（判断点）：observability 用专用查询端点，并顺带接通 stats 占位桩

**选定**：新增专用 `/admin/observability/{traces,usage,performance}` 三端点，直接包装 `fleetent.observability` 的三个查询函数，query 参数一一映射 CLI 的过滤维度。**同时**把 `stats_admin_api.py` 的 `fetch_traces`/`fetch_approvals`/`pricing_table` 接到真实数据源。

理由：
- CLI 三命令的价值在**多维原始 trace 查询**（run_id/user_id/session/event_type/时间窗），`/admin/stats/*` 是 dashboard 聚合（按 agent + 窗口），维度对不齐——只补 stats 桩**不能**替代 CLI。
- 专用端点是 CLI 的 1:1 映射，`slim-admin-cli` 删 CLI 时迁移路径清晰。
- stats 桩既然同源，顺手接通，消除"空壳 dashboard"这个独立技术债（边际成本低）。

**备选（否决）**：只接通 `/admin/stats/*` 桩——维度不足，删 CLI 后无法按 run_id/session 查 trace，是隐性回退。

### D2（判断点）：default-agent 改为控制面属性 + materialize 下发

**选定**：default-agent 从"CLI 直编 agent.yaml 文件"升为**控制面属性**：
- `agent_admin_state` 加一列 `is_default`（或建 per-tenant 单行 `default_agent` 设置表，design 二选一，倾向加列 + 代码层保证"每 tenant 至多一个 default"）。
- `PUT /admin/agents/{name}/default` 把该 agent 置默认（同 tenant 内其他 agent 的 default 清除）；`DELETE /admin/agents/default` 清除当前默认。
- materialize 产出 agent.yaml 时，对 `is_default` 的 agent 写 `bindings.default: true`。
- node 侧 scan 逻辑不变——它继续从下发的 agent.yaml `bindings.default` 求 index.default。

理由：目标架构里 agent.yaml 是控制面 materialize 的产物，node 不该被手工直编。default-agent 作为控制面属性、经 materialize 下发，是唯一与"控制面是配置真相源"一致的模型。

**迁移**：存量部署中 `bindings.default` 已写在 agent.yaml 文件里。本 change 落地时需把现有文件标记回填进 `is_default`（一次性脚本或迁移），之后文件标记由 materialize 重新生成。**这是本 change 风险最高的子项**。

**备选（否决）**：加 HTTP 端点但仍直写 agent.yaml 文件——违反控制面/node 边界，且平台不该假设能访问 node 上的 agent.yaml 文件。

### D3：service-principal 与 rotate-key 是薄包装

- `POST /admin/service-principals`：body `{name}`，调 `user_store.create_user(name)`，返回 `{user, api_key_plaintext_once}`。admin 鉴权 + 审计。
- `POST /admin/users/{user_id}/rotate-key`：调 `user_store.rotate_key(user_id)`，返回 `{user, api_key_plaintext_once}`；user 不存在 → 404。admin 鉴权 + 审计。

两者都是现成 store 函数的 HTTP 暴露，无新逻辑。命名用 `service-principals` 而非复用 `POST /admin/users`（后者是 web 用户语义，不发 key），避免把两种用户混进一个端点。

### D4：鉴权/审计沿用既有 admin router 模式

所有新端点用 `Authorization: Session <token>` + `_require_admin`，写操作调 `audit_log.write_audit`，与 `add-platform-admin-apis` 落地的端点一致。

## Risks / Trade-offs

- **[default-agent 迁移]** 存量 agent.yaml 的 `bindings.default` 与新 `is_default` 列双写期不一致 → 迁移时一次性回填 + 之后只认控制面列、materialize 重写文件标记；落地前在 integration 测试覆盖"回填后 materialize 产物的 bindings.default 与回填前一致"。
- **[observability 数据量]** trace 查询端点全量返回可能大 → 复用 CLI 已有的 `limit` 参数，默认上限与 CLI 一致。
- **[stats 桩接通的回归面]** `/admin/stats/*` 一旦接真实数据，原本"返回空集"的测试断言会变 → 接通时同步更新这些测试（预期内）。
- **[create_user vs create_web_user 概念漂移]** 两条建用户路径并存（服务账号 vs web 用户）→ 端点命名显式区分（`service-principals` vs `users`），文档说清各自语义。

## Migration Plan

1. observability 端点 + stats 桩接通（独立，先做）
2. service-principal + rotate-key 端点（独立，薄包装）
3. default-agent 控制面化（最后做，含 Alembic 加列 + 回填 + materialize 改动 + 迁移测试）
4. 每块 integration 测试覆盖 happy path + auth 拒绝 + 关键错误
5. 收尾：`make test-pr` + `make test-unit-ci` + integration 对照 main 基线
6. 落地后才解锁 `slim-admin-cli` 删全部 18 条

## Open Questions

- **OQ1**：default 标记存 `agent_admin_state.is_default` 列，还是单独 per-tenant `default_agent` 设置表？倾向加列（少一张表），但"每 tenant 至多一个 default"的约束加列时只能靠代码/部分索引保证。specs 阶段定。
- **OQ2**：`/admin/stats/*` 接通真实数据是否触及 viewer 可见性口径（per-user mask）？接通时核对 `MASK_PER_USER_FOR_VIEWER` 路径不被空桩掩盖过。
