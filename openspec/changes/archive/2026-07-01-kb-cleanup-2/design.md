## Context

KB 组织审计（2026-07-01）后的两处收尾。都无迁移、无 schema 变更、非可用性阻断。#1 是队列存储卫生（去 management.db 死回落），#2 是绑定反查端点收敛（退非规范的 by-agent、并入 archived 过滤）。本 change 改 `agent_admin_api.py`，与 `agent-identity-honest-naming`(A) 同文件不同函数，故须排在 A 之后执行。

## Goals / Non-Goals

**Goals**
- `kb_ingest_jobs` 队列访问显式传 queue db url、缺失即报错，不再隐式回落已删的 management.db 表；docstring 纠正。
- 退役 `/admin/kb/by-agent/{agent_id}`，agent→KB 反查唯一入口 = `/admin/agents/{name}/kbs`，并让它排除已归档 KB。

**Non-Goals**
- 不把 `kb_ingest_jobs.py` 物理挪进 `knowledge_base/`（牵动 6+ importer + shim，另议）。
- 不动 embedding 单源收敛、retrieval-playground 契约（#3 挂 Tier-3）。
- 不改 `/admin/kb/{kb_id}/agents`（正向视图）与绑定写行为。

## Decisions

**D1：`_database` 去回落 = 让 queue db url 必填。**
`kb_ingest_jobs._database(database_url)` 去掉 `or Settings().database_url` 回落，`database_url` 缺失/空即 `raise`，并始终对传入 url 跑 `_LOCAL_QUEUE_MIGRATIONS`（原来只在传了 url 时 migrate）。所有 public 函数签名 `database_url: str | None = None` → `database_url: str`（必填）。备选（保留 None 但指向专用 queue db 常量）被否决——queue db 是 per-tenant、经 `--config` 解析，无全局默认。

**D2：`serve.py:210` 传真实 queue url。**
`config.queue_database_url or None` → 直接传 `config.queue_database_url`（standalone status 端点的 config 应已解析出本租户 queue db；若为空，D1 会让它响亮失败而非静默读错库——正是想要的）。task 须核实该 config 确有 queue url 来源。

**D3：archived 过滤上移到 agent 侧反查。**
把 by-agent 的 `kb_engine_list(tenant_id)` 取 archived 集合、过滤绑定的逻辑，搬进 `agent_admin_api.list_agent_kbs`。两端反查行为从此一致（都排除 archived）。by-agent 端点整体删除。

**D4：spec 两处 delta。**
`kb-standalone-ingest`：队列访问显式 url、禁回落 mgmt.db（MODIFY 现有队列 requirement）。`kb-agent-binding`：收敛为两个视图、反查排除 archived、无第三端点（MODIFY binding matrix requirement）。

## Risks / Trade-offs

- **D2 可能暴露 serve 的 queue url 未接线** → 若 status 端点原来靠空 url 静默读 mgmt.db（本就错），改后会报错；task 须确认 serve 正确提供 queue url，必要时补接线（这是修 bug，不是引入回归）。
- **测试 shape 变更**：by-agent 返回 `{agent_id, kb_ids}`，agent 侧返回 `{agent, kb_ids}`——迁移的断言须换 shape，且 archived 过滤现在对 agent 侧生效（原 agent 侧不滤）。
- **agent_admin_api 引 kb 引擎列表**：`list_agent_kbs` 新增 import kb 引擎 archived 查询——platform→platform，不越 agent/platform 边界（kb_admin_api 已同样引用）；仍跑边界护栏确认。
- **与 A 同文件**：见 Context，apply 排在 A 之后。

## Migration Plan

无数据迁移。回滚 = revert。部署方：若有脚本调 `/admin/kb/by-agent/{id}`，改用 `/admin/agents/{name}/kbs`。

## Open Questions

无。
