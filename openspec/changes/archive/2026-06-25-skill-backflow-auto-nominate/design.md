## Context

托管链路现状（已工作部分，本 change 复用、不改）：

- node `reconcile._post_status` 经 `skill_deployer.observe()` 算 home content hash，逐 skill 组 `{skill_name, base_version, base_commit, drift}` 上报 `POST /nodes/{id}/status`。
- platform `node_desired_state_api.post_node_status`（`node_desired_state_api.py:149`，由 `server.py:270` 挂载）逐 agent 调 `_project_skill_status`（同文件 `:242`）：对每个上报 skill `set_base_version/set_base_commit/set_drift`，并按 `any_drift` `agent_admin_store.mark_drift/clear_drift`。该行为由 `tests/integration/test_node_desired_state_api.py::test_post_status_projects_skill_drift_to_agent_skills` 覆盖。
- `backflow_store.nominate(*, agent_id, skill_name, proposed_content=None, pool_dir)`：校验 `get_drift().drift` 为真（否则 `ValueError`）→ `_capture_proposed_bundle`（managed 先经 `_capture_bundle_from_owning_node` 走 `/forward/agents/{name}/skills/{skill}/bundle` 拉 node 真实 home bundle；不可达则回落读本机 `paths.tenant_agent_home_dir(...)/skills/<skill>`）→ `_detect_conflict(pool_dir, ...)` → INSERT `backflow_proposals` status='pending'。
- `backflow_api`（`router = APIRouter(prefix="/admin/skills/backflow")`）已有 accept/reject/fork（均 `_require_admin`，`Authorization: Session <token>`），有 `_pool_dir()`/`engine_skills_dir()`/`_get_proposal_or_404`。
- `_skill_pool_dir()`（`node_desired_state_api.py:287`）= `Path(skill_registry._resolve_skills_dir(None))`，与 `backflow_api.engine_skills_dir()` 同源——自动提名复用前者，**不引入对 backflow_api 的依赖**。

约束：改动全在 `platform/` 内部 + `frontend/`；不改 node 代码（node→platform 仅 HTTP，不变）；不加 schema/迁移；不动 `materialize._copy_skills` 旧 drift 路径。

## Goals / Non-Goals

**Goals:**
- drift 落库（managed 上报）后**自动**产生 1 条 pending backflow 提案；去重；drift=false 不产生；提名失败不阻断 status 上报。
- 待审列表与 diff 经 admin 鉴权端点可读；accept/reject/fork/list/diff 全部经 `server.app` 可达。
- 管理员在 React SPA 看待审 → 看 diff → accept/reject/fork；冲突项二次确认。

**Non-Goals:**
- 不改 node 上报、不改既有 drift 消费、不改 `nominate/get_proposal_diff/accept/reject/fork` 既有逻辑（只新增调用方与端点）。
- 不动 platform 旧 `materialize._copy_skills` drift 检测（重复问题留后续 cleanup）。
- 不加 schema/迁移；不引入 reflection ↔ backflow 端点/UI 混用。
- 不做提名的异步化/队列化（本 change 在 status 请求内同步、best-effort 触发）。

## Decisions

### 决策 1：自动提名挂在既有 drift 消费点 `_project_skill_status`，经 `nominate_if_absent` 去重

`backflow_store` 新增 public 助手：

```python
def nominate_if_absent(*, agent_id: int, skill_name: str, pool_dir: Path) -> int | None:
    existing = list_proposals(agent_id=agent_id, skill_name=skill_name, status="pending")
    if existing:
        return None
    return nominate(agent_id=agent_id, skill_name=skill_name, pool_dir=pool_dir)
```

`_project_skill_status` 在 `set_drift(..., drifted=skill.drift)` 之后，对 `skill.drift` 为真者调用：

```python
if skill.drift:
    try:
        backflow_store.nominate_if_absent(
            agent_id=report.agent_id, skill_name=skill.skill_name, pool_dir=_skill_pool_dir()
        )
    except Exception:  # bulkhead：提名失败不得阻断 node status 上报
        _logger.warning("auto-nominate backflow failed", extra=..., exc_info=True)
```

**Why**：①去重先查 pending 并短路，避免对「已有提案」的 skill 反复 `nominate`（也避免反复对 owning node 发 bundle 拉取 HTTP）；②挂在既有消费点而非新建 sweep，最小改动、与 drift 落库同事务时序自洽（先落 drift，nominate 内 `get_drift` 必为真）；③`pool_dir` 复用同模块 `_skill_pool_dir()`，不依赖 `backflow_api`。

### 决策 2：提名 best-effort 舱壁化

`nominate` 在 managed 下会**同步**回拉 owning node 的 bundle（`_capture_bundle_from_owning_node`，10s 超时）。node 暂不可达、无 placement、无可捕获 bundle 等会抛异常。此处必须舱壁化：`try/except` 记 warning、吞掉、继续 loop，使 `POST /nodes/{id}/status` 仍返回 200、drift 仍落库、其它 agent/ skill 不受牵连。符合「关停/收尾链舱壁化」与「不吞异常须 log」规则（此处 log 后有意不 re-raise，因为提名是 status 上报的旁路增强、非主职责）。

**Trade-off**：在 status 请求内同步回拉 bundle 增加该请求时延（每个新漂移 skill 一次 HTTP）。drift 罕见且去重短路使稳态下几乎不触发 `nominate`；异步化列为后续。

### 决策 3：读端点薄包 store，列表剔除 bundle 全文

`backflow_api` 新增：

- `GET /admin/skills/backflow`（可选 `?status=`，缺省 `pending`）：`_require_admin` → `list_proposals(status=...)` → 每条**剔除 `proposed_bundle`**（列表不传全量文件内容）、补 best-effort `agent_name`（`agent_store.get_by_id(agent_id)`，缺失置 None）。
- `GET /admin/skills/backflow/{proposal_id}/diff`：`_require_admin` → `get_proposal_diff(proposal_id, pool_dir=_pool_dir())`；store 抛 `ValueError("... not found")` → 映射 404。

**Why**：列表是高频只读，`proposed_bundle` 可能很大；diff 已由 `get_proposal_diff` 算好（vs base / vs head / conflict），端点只做鉴权 + 404 映射。鉴权完全沿用既有 `_require_admin`（与 accept/reject/fork 同口径）。

### 决策 4：挂载 router

`server.py` 加 `from fleetent.platform.skill_management import backflow_api` 与 `app.include_router(backflow_api.router)`（与既有 13 个 `include_router` 并列）。挂载后 `/admin/skills/backflow*` 全部可达。

### 决策 5：前端回流审批区独立于 reflection 只读区

`features/skills/api.ts` 加（沿用 `useAdminApi()` + React Query + `Session` 头）：
- `useBackflowProposalsQuery()` → `GET /admin/skills/backflow`
- `useBackflowDiffQuery(id)` → `GET /admin/skills/backflow/{id}/diff`
- `useBackflowAcceptMutation(id)` → `POST .../{id}/accept`（冲突时带 `{ 'X-Confirm': 'true' }`）
- `useBackflowRejectMutation(id)` → `POST .../{id}/reject`
- `useBackflowForkMutation(id)` → `POST .../{id}/fork`（body `{fork_name}`）

`page.tsx` 加「Skill backflow」审批区（仿现有 reflection 只读区版式：section + 卡片列表 + `<pre>` diff），但每条带 accept / reject / fork 按钮。**冲突项**（`conflict=1`）accept 前 `window.confirm(...)`，确认后带 `X-Confirm: true` 调用（fork_name 经 `window.prompt`/输入获取）。决策成功后 invalidate backflow 列表。

**Why**：现有 `skill-admin-ui` spec 规定 reflection proposals 区**只读**（agent-owned、DM 审批）；backflow 是**平台治理**（`skill-backflow` spec 明示 accept/reject/fork 经 admin 治理鉴权）。两区语义不同，必须分开，避免把 backflow 决策误并进只读 reflection 区。

## Risks / Trade-offs

- **[status 请求内同步回拉 bundle]** → 新漂移 skill 首次提名时该请求多一次（10s 超时上限的）HTTP。去重短路使稳态几乎不触发；异步化列后续。可接受（drift 罕见、内网 LAN）。
- **[提名失败被吞]** → 舱壁化只记 warning。这是有意的（提名是旁路增强）；运维经日志可见失败，不影响 drift 可见性与后续人工/重试。
- **[与旧 `materialize` drift 路径并存]** → 两套都会写 `agent_skills.drift`。managed agent 的权威 drift 来自 node 观测（`_project_skill_status`）；`materialize` 的 drift 写发生在 platform-local/standalone 物化路径。验证任务（tasks 4.5）只读确认 `materialize` 的 drift 重置不作用于 managed agent（有 placement 者），不会把 node 刚上报的 drift 清掉、令自动提名落空。本 change 不改两套行为，仅在 node 这套之上加提名。
- **[列表端点 agent_name 解析]** → 每条一次 `agent_store.get_by_id`，pending 提案数小（人审节流），N+1 可接受；缺失置 None 不报错。
- **[二次确认仅前端]** → 后端冲突 accept 已强制 `X-Confirm: true`（428）。前端 `window.confirm` 只是 UX 护栏；真正闸门在后端，双保险。

## Migration Plan

- 纯增量、无 schema/迁移。
- 回滚：移除 `_project_skill_status` 内 `nominate_if_absent` 调用、移除两个 GET 端点与 `server.py` 的 include、移除前端审批区即可；已生成的 pending 提案无害（可经 reject 关闭）。

## Open Questions

- 无阻塞项。提名异步化（出 status 请求路径、入队后台处理）与旧 `materialize._copy_skills` drift 路径的 cleanup（去重两套检测）确认为后续独立 change。
