## Why

Skill backflow（回流）= 把「agent 改过的 home skill 副本 → 审核 → 合回公共池」打通。其**存储层**（`backflow_store.nominate/list_proposals/get_proposal/get_proposal_diff`）、**治理决策**（`backflow_api` 的 accept/reject/fork）、**管理表**（`backflow_proposals`、`agent_skills`，Alembic 094/095）、**集成测试**（`test_backflow_*`）均已就绪，但整条链未接通。

复核现状（2026-06-25，对照实际代码）后，断点收敛为 **3 处**（原任务简报的「断点①：platform 收到 node 上报只记心跳、丢弃 skills」**已不成立**——`POST /nodes/{id}/status` 实际在 `node_desired_state_api.py::_project_skill_status` 已消费 skills、落 `set_base_version/set_base_commit/set_drift`，并由 `test_post_status_projects_skill_drift_to_agent_skills` 覆盖；该接收端落在 `node_desired_state_api.py` 而非简报所指的 `node_admin_api.py`）：

1. **自动提名缺失**：`backflow_store.nominate()` 在全 `src` 无任何调用 → drift 落库后**永不产生待审提案**。`_project_skill_status` 只写 drift，未触发提名。
2. **读端点缺失 + router 未挂**：`backflow_api.router` 不在 `server.py` 的 `include_router` 列表里（前端/admin 无法访问 accept/reject/fork）；且缺「列表」「看 diff」两个 GET 读端点。
3. **前端缺失**：`frontend/src/features/skills/` 无 backflow 审批界面（现有只读区对接的是 reflection `/admin/skills/proposals`，非 backflow，二者不可混用）。

## What Changes

打通 managed 部署端到端链路：agent 改 skill → node 检测 drift 随 status 上报 → platform 落 `agent_skills.drift=1`（**已有**）→ platform **自动生成** backflow 待审提案（去重：已有 pending 则跳过）→ 管理员在前端看列表/diff → 采纳/拒绝/另存（冲突需二次确认）→ 采纳写回公共池并 git 提交（**已有**）。

- **drift 自动提名（去重、best-effort）**：在既有 drift 消费点 `_project_skill_status` 中，对 `drift=true` 的 skill 调用新增的 `backflow_store.nominate_if_absent(...)`（先查 pending 短路去重，无则 `nominate(...)`，`pool_dir` 复用模块内 `_skill_pool_dir()`）。提名失败（如 owning node 暂不可达、无可捕获 bundle）**舱壁化**：记 warning、不传播，绝不令 node status 上报失败。
- **回流读端点**：`backflow_api` 新增 `GET /admin/skills/backflow`（列待审，剔除 `proposed_bundle` 全文、补 `agent_name`）与 `GET /admin/skills/backflow/{id}/diff`（薄包 `get_proposal_diff`，不存在→404），沿用既有 `_require_admin` 鉴权。
- **挂载治理 router**：`server.py` 加 `backflow_api` import 与 `include_router`，使 accept/reject/fork/list/diff 全部可达。
- **前端回流审批区**：`features/skills/api.ts` 加 backflow 的 query/diff/accept/reject/fork hooks；`page.tsx` 加审批区（仿现有只读 reflection 区，但带决策按钮；冲突项 accept 需二次确认 + `X-Confirm: true`）。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `skill-backflow`：新增 requirement——①drift 观测自动触发回流提名（去重、best-effort 不阻断上报）；②回流待审列表与 diff 经 admin 端点可访问；③回流治理 router 挂载到平台应用（accept/reject/fork 可达）。
- `skill-admin-ui`：新增 requirement——React SPA 渲染**回流审批区**（平台治理：列表 + diff + accept/reject/fork 决策；冲突项二次确认）。与既有「reflection proposals 只读」requirement **不冲突**（后者针对 agent-owned、DM 审批的 reflection 提案 `/admin/skills/proposals`；本区针对平台治理的 backflow 提案 `/admin/skills/backflow`）。

## Impact

- **owning package**：`platform/`（`skill_management/backflow_store.py`、`skill_management/backflow_api.py`、`node_management/node_desired_state_api.py`、`server.py`）+ `frontend/`（`features/skills/api.ts`、`features/skills/page.tsx`）。
- **public API surface**：
  - `backflow_store.nominate_if_absent(*, agent_id: int, skill_name: str, pool_dir: Path) -> int | None`（新增；返回新提案 id，或已有 pending 时返回 None）。
  - `backflow_api` 新增 `GET /admin/skills/backflow`、`GET /admin/skills/backflow/{proposal_id}/diff` 两个端点；`backflow_api.router` 挂载到 `server.app`。
- **owned tables**：无（复用既有管理表 `backflow_proposals`、`agent_skills`；**无新迁移**，Alembic 已到 101）。
- **config namespace**：无。
- **cross-module dependencies**：`platform/node_management/node_desired_state_api` → `platform/skill_management/backflow_store`（platform 内跨子包，沿用既有 `from fleetent.platform.skill_management import skill_admin_store` 同款用法，过 `check_module_boundaries`）。node SHALL NOT import `fleetent.platform.*`（不变——node 仅经 HTTP 上报，本 change 不改 node 代码）。frontend 仅经 HTTP 契约。
- **migration / shim plan**：无 schema/迁移；纯行为增量。无模块移动、无 shim。
- **范围外（明确不动）**：
  - 不动 platform 旧的 `materialize._copy_skills` drift 检测（服务 dev/单机，与 node 那套重复，cleanup 留后续）。
  - 不改数据库结构、不加迁移。
  - 不碰 agent→platform 解耦红线（改动全在 platform 内部 + 前端；node 不动）。
  - 不改 node 上报路径、不改既有 drift 消费（已工作）。
