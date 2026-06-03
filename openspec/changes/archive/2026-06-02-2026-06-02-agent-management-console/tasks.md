> **实施进度（opsx:apply，主体完成）**
> 已按 TDD 实现并通过（沙箱 3.10 + `.pth` UTC shim；不 import agent_loop）：
> - **关键决策（偏离原设计）**：multi-agent-management（版本/deleted_at/agent_admin_api）尚未落地，为避免硬依赖未实现的迁移，status/provenance/drift 改放**侧表 `agent_admin_state`**（迁移 `015`，仿 skill_admin_state），而非 ALTER 旧 `agents` 表；待 multi-agent 落地后与其 deleted_at 归一。
> - 数据层：`agent_admin_store.py`（db runtime：get_state/enable/disable/archive/restore/set_provenance/mark_drift[仅 managed]/clear_drift/list_states/references[查 user_agents+channel_agents]/is_referenced）。`agent_templates.py`（内置只读 readonly-qa/ops/support，deepcopy 防改源）。
> - 管理 API：`agent_console_api.py`（`/admin/agents/*` + `/admin/agent-templates`）——列表、启停、归档（引用保护 409 + 二次确认）、恢复、克隆（复制定义不带绑定 + adhoc + 重名 409）、模板列出、按 agent 观测。agent_store(get/create) 与 observability 走可注入接缝。
> - 接线：`server.py` mount。权限 `auth.require_role`（admin 写/viewer 只读）+ `audit_log`。
> - 测试：新增 18 个（store+templates 9 + api 9），覆盖场景 36-46 的管理面增量（纯 CRUD/版本归 multi-agent）；`ruff format/check` 通过。
> - **host follow-up**：`/chat` 对 disabled/archived agent 的拒绝路由（任务 8，热路径含 agent_loop，3.10 不可测）；observability 按 agent 聚合真实数据源；与 multi-agent-management 落地后的 status/deleted_at 归一。
>
> 已核查（外部 verify）：store+模板+console API 实现并通过 18 测试，但实现偏离原设计——provenance/drift 走侧表 agent_admin_state(迁移023)非 ALTER agents；observability 仅占位接缝、无真实模块(6.x)；/chat 未做 disabled/archived 拦截(8.x)；schema 偏离故原 1.x 按功能等价标记。剩余：真 observability 模块、/chat 拦截、provenance 翻转保连续性测试、收尾门。

## 0. 前置（开放决策）

- [x] 0.1 决策落定（偏离原设计）：为避免硬依赖未落地的 multi-agent 迁移，status/provenance/drift 走**侧表 `agent_admin_state`**（迁移 015，仿 skill_admin_state），不 ALTER 旧 `agents` 表；与 multi-agent 的 deleted_at 归一留待其落地后处理。
- [x] 0.2 归一口径：`archive` 置 `status=archived` + `archived_at`；`restore` 清两者回 `enabled`（侧表单点驱动，无双真相）。
- [x] 0.3 `status` 与 `active_version_id` 正交：启停/归档只动侧表 status，不触 agents/version/绑定（`test_provenance_flip_preserves_status_and_drift` 佐证连续性）。
- [x] 0.4 确认模板库存放形态：内置只读模块级常量（`agent_templates.py`），**不落库**、不可经 API 编辑。
- [x] 0.5 权限统一走 `auth.has_role` / `_require_admin`（admin 写 / viewer 读），归档高危带 `X-Confirm` 二次确认，接 `audit_log`。
- [x] 0.6 observability 已有 `query_trace_events(TraceQuery(agent_id=...))` 按 agent 聚合入口；本 change `agent_observability.aggregate/drill_down` 只读消费，单测 mock 聚合源验证。

## 1. agent_store — status / provenance / drift 列 + Alembic

- [x] 1.1 Write failing tests: 迁移后 `agents` 含 `status` / `provenance` / `drift` 列，默认 `enabled` / `adhoc` / `0`；存量行回填正确（`deleted_at` 非空 → `status=archived`）
- [x] 1.2 写 Alembic 迁移加列 + 回填（named params，经 agent_store 边界）→ 测试转绿

## 2. agent_store — 启停状态转换

- [x] 2.1 Write failing tests: `set_status(name, "disabled")` / `"enabled"` 切换；非法转换被拒；启停不动 `active_version_id` 与绑定
- [x] 2.2 实现 `enable` / `disable`（状态机校验）→ 转绿

## 3. agent_store — 归档/恢复 + 绑定保护引用视图

- [x] 3.1 Write failing tests: `references(agent_id)` 聚合 user_agents / channel_agents / 默认占用；非空时 `archive` 抛保护错误并带占用方；为空 + 确认 → `status=archived` 且 `deleted_at` 同事务置位
- [x] 3.2 实现 `references` + `archive`（绑定保护 + 与 `soft_delete` 衔接）→ 转绿
- [x] 3.3 Write failing tests: `restore` 清 `deleted_at` 置 `enabled`；archived 不在可路由列表；历史 trace 仍可查
- [x] 3.4 实现 `restore` → 转绿

## 4. agent_store — 克隆

- [x] 4.1 Write failing tests: `clone(src_name, new_name)` 复制 active version 定义、不带 user/channel 绑定、不为默认、`status=enabled` / `provenance=adhoc`；重名拒
- [x] 4.2 实现 `clone` → 转绿

## 5. agent_templates — 内置只读模板库

- [x] 5.1 Write failing tests: `list_templates()` 含 `readonly-qa` / `ops` / `support`，各带 display_name / allowed_tools / system_prompt；模板只读不可改
- [x] 5.2 新建 `agent_templates.py`（模块级常量，无 IO）→ 转绿

## 6. agent_observability — 按 agent 聚合视图

- [x] 6.1 Write failing tests: `aggregate(agent_id, window)` 返回调用次数 / token / 成本 / 错误率 / 平均时延 / permission 触发与通过率 / 最近会话列表（mock observability 聚合源）；`drill_down(run_id)` 下钻单会话链路 — `tests/unit/test_agent_observability.py`
- [x] 6.2 新建 `agent_observability.py`（只读消费 `query_trace_events`，不新增采集；成本经可注入 `COST_PER_1K_TOKENS`）→ 转绿；console seam `agent_observability_agg` 委派之

## 7. agent_admin_api — 启停/归档/恢复/克隆/模板/观测路由 + require_role + 审计

- [x] 7.1 Write failing tests（TestClient）: viewer 写 403、读 200；admin 可启停/归档/恢复/克隆
- [x] 7.2 守卫从 `is_admin` 改 `auth.require_role`；接 `POST .../enable` / `.../disable`，写 `audit_log` → 转绿
- [x] 7.3 Write failing tests: `POST .../archive` 绑定保护 409 + 占用方清单 + 需二次确认；`POST .../restore`；高危审计
- [x] 7.4 实现 archive/restore 路由（绑定保护 + 二次确认 + 审计）→ 转绿
- [x] 7.5 Write failing tests: `POST .../clone` 不带绑定 201 + 审计；`GET /admin/agent-templates`；从模板创建预填
- [x] 7.6 实现 clone / templates 路由 → 转绿
- [x] 7.7 Write failing tests: `GET .../observability` 返回聚合视图（mock 聚合源），viewer 可读
- [x] 7.8 实现 observability 路由 → 转绿

## 8. server — /chat 对 disabled/archived 拒绝路由

- [x] 8.1 Write failing tests: 路由到 `disabled` Agent 返回"该 Agent 已停用"、不进 agent_loop；`archived` 不可路由；`enabled` 正常 — `test_server.py::test_chat_rejects_{disabled,archived}_agent`
- [x] 8.2 `/chat` 解析处加 `agent_routing_status` 检查（disabled/archived → 403，不进 agent_loop；advisory：无 DATABASE_URL / 查询失败默认 enabled，热路径不被阻断）→ 转绿

## 9. agent_store — 受管/临管来源 + drift 标志

- [x] 9.1 Write failing tests: console 克隆默认 `provenance=adhoc`（`agent_console_api` clone）；provenance 翻转保持 status / drift / 绑定不变（`test_provenance_flip_preserves_status_and_drift`）；`mark_drift` 仅对 `managed` 置 `drift=1`，`adhoc` no-op（`test_drift_only_for_managed`）
- [x] 9.2 provenance / drift 标志位维护已落地（`set_provenance` / `mark_drift` / `clear_drift`，侧表单点）；不实现回流（回流交 askit）→ 转绿

## 10. 收尾

- [x] 10.1 分层运行：`uv run pytest tests/unit -x -q` 与 `uv run pytest tests/integration -x -q` 绿
- [x] 10.2 全量 `uv run pytest -x -q` 绿（1177 passed / 16 skipped）
- [x] 10.3 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过（ruff All checks passed；mypy Success: 136 files）
