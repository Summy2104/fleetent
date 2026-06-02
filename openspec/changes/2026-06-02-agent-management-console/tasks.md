## 0. 前置（开放决策）

- [ ] 0.1 `agents` 表加 `status` / `provenance` / `drift` 列的 **Alembic 迁移**：确认与 `2026-05-29-multi-agent-management` 的 `active_version_id` / `deleted_at` 迁移先后顺序与 revision 链；回填规则（`status=enabled`，已 `deleted_at` 非空回填 `archived`；`provenance=adhoc`；`drift=0`）。
- [ ] 0.2 确认 `status` 与已有 `deleted_at` 的归一口径：archive 同时置两者、restore 同时清两者，避免双真相。
- [ ] 0.3 确认 `status` 与 `agent_versions` / `active_version_id` 正交（启停/归档不动 active version）。
- [ ] 0.4 确认模板库存放形态：内置只读模块级常量（`agent_templates.py`），**不落库**、不可经 API 编辑。
- [ ] 0.5 确认权限从 `is_admin` 迁到 `auth.require_role`：`/admin/agents/*` 守卫统一走 role；沿用 user-management 的兼容映射与高危二次确认守卫。
- [ ] 0.6 确认 observability 是否已暴露"按 agent_id 聚合"查询入口；若无则记为跨域 follow-up，本 change 单测以 mock 聚合源验证。

## 1. agent_store — status / provenance / drift 列 + Alembic

- [ ] 1.1 Write failing tests: 迁移后 `agents` 含 `status` / `provenance` / `drift` 列，默认 `enabled` / `adhoc` / `0`；存量行回填正确（`deleted_at` 非空 → `status=archived`）
- [ ] 1.2 写 Alembic 迁移加列 + 回填（named params，经 agent_store 边界）→ 测试转绿

## 2. agent_store — 启停状态转换

- [ ] 2.1 Write failing tests: `set_status(name, "disabled")` / `"enabled"` 切换；非法转换被拒；启停不动 `active_version_id` 与绑定
- [ ] 2.2 实现 `enable` / `disable`（状态机校验）→ 转绿

## 3. agent_store — 归档/恢复 + 绑定保护引用视图

- [ ] 3.1 Write failing tests: `references(agent_id)` 聚合 user_agents / channel_agents / 默认占用；非空时 `archive` 抛保护错误并带占用方；为空 + 确认 → `status=archived` 且 `deleted_at` 同事务置位
- [ ] 3.2 实现 `references` + `archive`（绑定保护 + 与 `soft_delete` 衔接）→ 转绿
- [ ] 3.3 Write failing tests: `restore` 清 `deleted_at` 置 `enabled`；archived 不在可路由列表；历史 trace 仍可查
- [ ] 3.4 实现 `restore` → 转绿

## 4. agent_store — 克隆

- [ ] 4.1 Write failing tests: `clone(src_name, new_name)` 复制 active version 定义、不带 user/channel 绑定、不为默认、`status=enabled` / `provenance=adhoc`；重名拒
- [ ] 4.2 实现 `clone` → 转绿

## 5. agent_templates — 内置只读模板库

- [ ] 5.1 Write failing tests: `list_templates()` 含 `readonly-qa` / `ops` / `support`，各带 display_name / allowed_tools / system_prompt；模板只读不可改
- [ ] 5.2 新建 `agent_templates.py`（模块级常量，无 IO）→ 转绿

## 6. agent_observability — 按 agent 聚合视图

- [ ] 6.1 Write failing tests: `aggregate(agent_id, window)` 返回调用次数 / token / 成本 / 错误率 / 平均时延 / permission_gate 触发与通过率 / 最近会话列表（mock observability 聚合源）；下钻单会话链路
- [ ] 6.2 新建 `agent_observability.py`（只读消费 observability traces，不新增采集）→ 转绿

## 7. agent_admin_api — 启停/归档/恢复/克隆/模板/观测路由 + require_role + 审计

- [ ] 7.1 Write failing tests（TestClient）: viewer 写 403、读 200；admin 可启停/归档/恢复/克隆
- [ ] 7.2 守卫从 `is_admin` 改 `auth.require_role`；接 `POST .../enable` / `.../disable`，写 `audit_log` → 转绿
- [ ] 7.3 Write failing tests: `POST .../archive` 绑定保护 409 + 占用方清单 + 需二次确认；`POST .../restore`；高危审计
- [ ] 7.4 实现 archive/restore 路由（绑定保护 + 二次确认 + 审计）→ 转绿
- [ ] 7.5 Write failing tests: `POST .../clone` 不带绑定 201 + 审计；`GET /admin/agent-templates`；从模板创建预填
- [ ] 7.6 实现 clone / templates 路由 → 转绿
- [ ] 7.7 Write failing tests: `GET .../observability` 返回聚合视图（mock 聚合源），viewer 可读
- [ ] 7.8 实现 observability 路由 → 转绿

## 8. server — /chat 对 disabled/archived 拒绝路由

- [ ] 8.1 Write failing tests: 路由到 `disabled` Agent 返回"该 Agent 已停用"、不进 agent_loop；`archived` 视为不可路由；`enabled` 正常
- [ ] 8.2 在 `/chat` 路由解析处加 status 检查 → 转绿

## 9. agent_store — 受管/临管来源 + drift 标志

- [ ] 9.1 Write failing tests: console 创建/克隆/模板创建默认 `provenance=adhoc`；provenance 翻转保持 `agent_id` / active version / 绑定不变；对 `managed` 的 UI 改动置 `drift=1`，对 `adhoc` 不置
- [ ] 9.2 实现 provenance / drift 标志位维护（不实现回流，回流交 askit）→ 转绿

## 10. 收尾

- [ ] 10.1 分层运行：`uv run pytest tests/unit -x -q` 与 `uv run pytest tests/integration -x -q` 绿
- [ ] 10.2 全量 `uv run pytest -x -q` 绿
- [ ] 10.3 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过
