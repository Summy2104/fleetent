# Design — Agent Management Console（增量）

> 本 change 叠加在 `2026-05-29-multi-agent-management` 之上。该 change 已定义 `agents` / `agent_versions` / `user_agents` / `channel_agents` schema、`active_version_id`、`deleted_at`、CRUD / 版本 / 绑定 API。本设计只描述**新增的运营层**，不重述已有结构。

## 状态机与已有字段的关系

新增 `agents.status ∈ {enabled, disabled, archived}`，与已有 `deleted_at` / `active_version_id` 协调如下：

```
[*] --create--> enabled
enabled --disable--> disabled        # 保留定义+全部绑定，仅拒新会话
disabled --enable--> enabled         # 立即恢复服务
enabled --archive--> archived        # 先过绑定保护 + 二次确认
disabled --archive--> archived
archived --restore--> enabled        # 保留期内恢复
archived --(超保留期硬清理)--> [*]    # 运维，CLI 不开放
```

- **`status` 是运营开关，`active_version_id` 是内容指针**——两者正交。禁用/归档不动 `active_version_id`，恢复后仍指向归档前的 active version。
- **`status=archived` ⟺ `deleted_at IS NOT NULL`**：归档即已有 `soft_delete` 语义的归一。`archive` 操作在置 `status=archived` 的同一事务里写 `deleted_at`；`restore` 清空 `deleted_at` 并置 `status=enabled`。`get_by_name` 现有"软删除返回 None"的行为不变（archived 即不可见于可路由列表）。
- **路由解析**：`status ∈ {disabled, archived}` 的 Agent 不接受新会话。`disabled` 与 `archived` 的拒绝文案不同：disabled → "该 Agent 已停用"（可恢复语义），archived → 等同不存在（404 / 不在可路由列表）。
- **存量回填**：现有行（无 `status` 列）迁移时回填 `status=enabled`；已 `deleted_at` 非空的行回填 `status=archived`，保证状态与软删除一致。

## 绑定保护引用视图（与删除共用）

归档前必须确认 Agent 未被占用。引用视图聚合三处占用方，**与已有删除/绑定逻辑共用同一查询**：

```
references(agent_id) = {
  users:    SELECT user_id  FROM user_agents    WHERE agent_id = :agent_id
  channels: SELECT platform, channel_id FROM channel_agents WHERE agent_id = :agent_id
  default:  (agent.name == default_agent_name)   # 全局默认值占用
}
```

- 视图非空 → `archive` 被阻止，API 返回 409 + 占用方清单（user_id 列表 / (platform, channel_id) 列表 / 是否为默认），提示先解绑或迁移。
- 视图为空且通过二次确认 → 执行归档。
- 该引用视图同时供详情页"被哪些 user/channel 引用"展示（与 `2026-05-29` 的绑定管理 UI 复用），单一查询、单一真相。
- SQL 全部 named params（`:agent_id`），经 `agent_store` 边界，schema 归 Alembic。

## 克隆与模板库形态

**克隆**：读源 Agent 的 active version 快照（system_prompt / allowed_tools / model_overrides / skills_dir / mcp_server_ids / memory_namespace），以新名称（全局唯一，重名拒绝）插入新 `agents` 行 + version 1，`status=enabled`、`provenance=adhoc`、`active_version_id` 指向新 version。**不复制** user_agents / channel_agents / 默认标志。克隆是一次普通 create，只是字段来源是另一个 Agent。

**模板库**：内置只读常量，**不落库**——放在 `agent_templates.py` 模块级数据（`TEMPLATES: dict[str, AgentTemplate]`），每个模板含 `id`、`display_name`、推荐 `allowed_tools`、`system_prompt`。

| template id | 用途 | 预填 allowed_tools（示意） |
|---|---|---|
| `readonly-qa` | 只读问答 | `["read_*", "search_*"]` |
| `ops` | 运维 | `["read_*", "shell", "github__*"]` |
| `support` | 客服 | `["read_*", "memory_*"]` |

- `GET /admin/agent-templates` 返回模板清单（id / display_name / allowed_tools / system_prompt 预览）。
- 从模板创建 = 用模板字段预填创建表单，admin 微调名称后走普通 create 路径；模板本身不可编辑（只读），改模板需改代码（受管来源由 askit 管，见下）。

## 受管 / 临管来源模型与 drift

新增 `agents.provenance ∈ {managed, adhoc}` 与 `agents.drift`（整型布尔，默认 0）：

- **identity 是稳定的 `agent_id`**——"受管/临管"只是同一行上的**标志位**，切换来源**不重建对象、不换 id、不丢绑定/版本历史**。这与 platform.md 与 askit change 的口径一致。
- 本页所有即时创建（含克隆、从模板创建）默认产出 `provenance=adhoc`。
- 受管对象由 askit `deploy --target fleetent` 从 spec 编译写入（置 `provenance=managed`）。
- 对 `provenance=managed` 的 Agent 做 UI 改动（编辑 / 启停 / 改模型）时置 `drift=1`，UI 标 drift 徽章；drift 的转正（接受 UI 改动回 spec）或还原（覆盖回流抹掉 UI 改动）由 askit 处理——本 change **只维护 `provenance` / `drift` 两个标志位**，不实现回流逻辑。
- adhoc → managed 的"转正"与 managed → adhoc 的"脱管"由 askit 侧写标志位完成；本面读标志位渲染徽章并在 managed 上拦截/提示 drift。

## 按 agent 观测：只聚合不重定义采集

- 数据源是 observability 的 `traces`（`2026-05-29` 已记录 agent_id 维度）。本面新增 `agent_observability.py` 提供 `aggregate(agent_id, window) -> AgentMetrics`，按 `agent_id` 聚合：调用次数、token、成本、错误率、平均时延、permission_gate 触发数与通过率、最近会话列表（session_id + 时间 + 概要）。
- **不新增采集点、不改 trace schema**——只读 observability 的查询入口聚合。若 observability 尚未暴露按 agent 聚合接口，本 change 依赖该 follow-up（proposal Impact 已声明），单测以 mock 聚合源验证本面渲染与下钻链路。
- 下钻单会话 trace 复用 observability 既有的单会话 trace 查询，本面只提供 agent → session 列表的入口。

## 权限分级（复用 user-management）

- `/admin/agents/*` 守卫统一走 `auth.require_role`（`2026-05-30-user-management` 已提供）：
  - 写操作（create / edit / clone / 启停 / 归档 / 恢复 / 改模型 / 绑定）要求 `role in {admin, built_in_admin}`。
  - 只读（列表 / 详情 / 观测）允许 `viewer` 及以上。
  - viewer 触发写 → 403，请求不落库（场景 46）。
- 取代 `2026-05-29` 临时的布尔 `is_admin`；兼容映射 `is_admin == role in {admin, built_in_admin}` 由 user-management 提供。
- 归档等高危动作要求二次确认（请求带确认标志或 2FA，复用 user-management 的高危守卫口径），并写 `audit_log`（actor / action / target=agent_id / detail）。

## 审计

所有写操作（create / edit / clone / enable / disable / archive / restore / 改模型 / 绑定）落一条 `audit_log`（复用 `2026-05-30-user-management` 的 `audit_log` 表与 `write_audit`）：`action`（如 `agent.disable`）、`target_type="agent"`、`target_id=agent_id`、`detail`（前后状态 / 占用方等）。归档与恢复因高危额外记录二次确认结果。

## 测试隔离（遵循 CLAUDE.md）

- 数据库：`monkeypatch` `agent_store.DB_PATH`（或统一 DB fixture）到 `tmp_path`，绝不碰 `data/`；新列经 Alembic 迁移，测试用迁移后的临时库。
- API：FastAPI `TestClient`，注入不同 `role` 的会话验证 admin 可写 / viewer 403。
- 观测：mock `agent_observability.aggregate`（或其底层 observability 聚合源），断言渲染与下钻链路，不依赖真实 trace 数据。
- 状态机 / 绑定保护：构造 user_agents / channel_agents / 默认绑定，断言归档被阻止并列占用方；解绑后归档成功、保留期内恢复。
- 来源/drift：构造 `provenance=managed` 行，断言 UI 改动置 `drift=1` 且 id / 绑定不变。
- SQL named params、路径可 monkeypatch、禁 ORM / AI 框架、mypy strict、ruff 100。
