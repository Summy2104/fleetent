## Why

`2026-05-29-multi-agent-management` 已经把 Agent 的**后端基础**补齐：`agent-admin-api`（CRUD / 版本列表 / 激活回滚 / user·channel 绑定）、`agent-versioning`、`agent-resource-isolation`、`agent-invocation`，以及 `agent-definition` / `channel-agent-binding` 的扩展。但它把 Agent 当作"定义对象"，缺了 `platform.md`«Agent 管理»要求的**管理面运营特性**：

1. **没有启停开关**：只能软删除（archived）或活着，无法"暂时下线但保留定义与绑定"。被禁用 Agent 路由到 `/chat` 时没有"该 Agent 已停用"的明确拒绝语义（场景 39）。
2. **删除/归档语义不完整**：已有 `soft_delete` 把 `deleted_at` 置位，但没有**绑定保护**——仍被 user/channel 绑定或为默认 Agent 时应阻止并列出占用方（场景 40），归档后也没有保留期内"恢复"路径（场景 41）。
3. **没有克隆与模板库**：无法一键复制一个 Agent 的定义（不带绑定）起一个副本（场景 42），也没有内置模板（只读问答 / 运维 / 客服）预填 `allowed_tools` + prompt 降低从零配置门槛（场景 43）。
4. **没有按 Agent 的观测视图**：observability 有 traces，但管理面没有按 `agent_id` 聚合的详情页（调用次数 / token·成本 / 错误率 / 时延 / permission_gate 通过率 / 最近会话下钻，场景 45）。
5. **权限只有布尔 `is_admin`**：`agent-admin-api` 临时引入的 `users.is_admin` 不足以表达 admin（可管理）/ viewer（只读观测）分级（场景 46）；`2026-05-30-user-management` 已用 `role` 取代它并提供 `auth.require_role`，本 change 应对齐复用。
6. **没有来源归属**：受管（spec-owned，由 askit `deploy --target fleetent` 编译）与临管（DB-only，本页即时创建）无徽章区分，对受管对象的 UI 改动也无 drift 标记与覆盖回流对接。

这些是把"能定义 Agent"升级为"能在后台运营 Agent"的缺口。本 change 是**增量**，叠加在 `2026-05-29-multi-agent-management` 之上：纯 CRUD / 版本能力不重复，只交叉引用。

## What Changes

**ADDED**
- `agent-lifecycle-toggle`：启用 / 禁用启停开关（禁用保留定义与全部绑定，但路由到该 Agent 的 `/chat` 被拒并提示"该 Agent 已停用"，重启即恢复，启停写审计）；归档（软删除）前的**绑定保护**（仍被 user / channel 绑定或为默认 Agent 则阻止并列出占用方，与已有 `soft_delete` 衔接）；归档后保留期内"恢复"。状态机 `enabled ↔ disabled → archived`，归档为高危需二次确认。
- `agent-template-clone`：克隆现有 Agent（复制 active version 的 system_prompt / allowed_tools / model_overrides，**不复制任何绑定**，新名称全局唯一）；内置只读模板库（只读问答 / 运维 / 客服），从模板起一个新 Agent 时预填推荐 allowed_tools + prompt。
- `agent-observability-view`：按 `agent_id` 聚合的详情页观测（调用次数 / token·成本曲线 / 错误率 / 平均时延 / permission_gate 触发与通过率 / 最近会话列表，可下钻单会话 trace）。**数据源为 observability 的 traces，本面只做聚合，不重新定义采集**。
- `agent-provenance`：每个 Agent 标注「受管（managed）/ 临管（adhoc）」徽章；受管对象的 UI 改动标 drift；与 askit `deploy --target fleetent` 覆盖回流对接的来源标志位（identity 仍是稳定 `agent_id`，受管/临管只是同行标志位，切换不重建对象）。

**MODIFIED**
- `agent-admin-api`：在已有 `/admin/agents/*` 上扩展启停（`POST .../enable` / `.../disable`）、归档/恢复（带绑定保护 + 二次确认）、克隆（`POST .../clone`）、模板（`GET /admin/agent-templates`、从模板创建）、按 agent 观测（`GET .../observability`）路由；`/admin/*` 守卫从布尔 `is_admin` 改为 `auth.require_role`（admin 写 / viewer 只读），写操作落 `audit_log`。
- `agent-definition`：`agents` 表加 `status`（`enabled` / `disabled` / `archived`）与 `provenance`（`managed` / `adhoc`）列；`status=archived` 与已有 `deleted_at` 衔接（归档即软删除）；路由解析对 `disabled` / `archived` 拒绝新会话。

## Capabilities

### New Capabilities

- `agent-lifecycle-toggle`
- `agent-template-clone`
- `agent-observability-view`
- `agent-provenance`

### Modified Capabilities

- `agent-admin-api`
- `agent-definition`

## Impact

- **与 `2026-05-29-multi-agent-management` 的衔接**：
  - 本 change **不重复** agent CRUD / 版本列表 / 激活回滚 / user·channel 绑定（场景 36/37/38/44 的核心已由该 change 覆盖，本 change 只补"启停 / 来源 / 权限分级"的增量验收）。
  - 复用其 `agents.deleted_at`（归档=软删除）、`active_version_id`、`agent_versions`、`channel_agents.bound_version_id`；新增 `status` / `provenance` 两列叠加在其 schema 上。
  - 绑定保护与已有 user_agents / channel_agents / `default_agent_name` 共用同一"引用视图"。
- **跨域 follow-up**（本 change 只声明契约，不实现对端）：
  - **observability**：需提供"按 `agent_id` 聚合"的查询入口（调用次数 / token / 成本 / 错误率 / 时延 / permission_gate 通过率 / 最近会话）；本面只消费，聚合口径以 observability 为准。
  - **askit（覆盖回流）**：受管 Agent 的 drift 标记与覆盖回流由 askit `deploy --target fleetent` 处理；本 change 只维护 `provenance` 标志位与 drift 标记字段。
  - **governance / agent-runtime**：被 `disabled` / `archived` Agent 的路由拒绝在网关侧最终生效，本面只保证状态可被运行域读取；运行语义以 agent-runtime 为准。
- **代码**：
  - 修改：`agent_admin_api.py`（启停 / 归档+恢复 / 克隆 / 模板 / 观测路由 + `require_role` 守卫 + 审计接线）、`agent_store.py`（`status` / `provenance` 列 + 状态转换 + 绑定保护引用视图 + clone）、`server.py`（`/chat` 路由对 disabled/archived 拒绝）。
  - 新增：`agent_templates.py`（内置只读模板库，模块级常量，无 IO）、`agent_observability.py`（按 `agent_id` 聚合视图，消费 observability traces）。
- **依赖**：无新增依赖（FastAPI、aiosqlite、`auth` / `audit_log` 已在）。
- **数据**：`agents` 表加 `status`（默认 `enabled`）/ `provenance`（默认 `adhoc`）/ `drift`（默认 `0`）列，走 **Alembic 迁移**（存量行回填 `status=enabled` / `provenance=adhoc`）。不新增表。模板库为内置常量，不落库。
- **破坏性**：
  - `/admin/agents/*` 守卫从 `is_admin` 改 `require_role`（admin/viewer 分级）；兼容映射 `is_admin == role in {admin, built_in_admin}` 已由 user-management 提供。
  - 已有 `soft_delete` 调用点需经绑定保护检查（直接调用旁路应改走归档 API）。

## Commit 切分建议

每个 commit 自包含、内部 TDD（测试先红 → 实现 → 绿）：

1. `feat(agent_store): add status/provenance/drift columns + Alembic migration`（1.x）
2. `feat(agent_store): enable/disable/archive/restore state transitions + binding-protection reference view`（2.x、3.x）
3. `feat(agent_store): clone agent definition without bindings`（4.x）
4. `feat(agent_templates): built-in read-only template library`（5.x）
5. `feat(agent_observability): per-agent aggregation view over observability traces`（6.x）
6. `feat(agent_admin_api): enable/disable/archive/restore/clone/template/observability routes + require_role guard + audit`（7.x）
7. `feat(server): reject /chat routing to disabled/archived agents`（8.x）
8. `feat(agent_store): provenance badge + drift flag for managed agents`（9.x）
