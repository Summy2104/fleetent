## Why

KB 组织审计（2026-07-01）后确认两处仍值得收拾，都不是可用性阻断、但都是真实的"接缝不合理"：

1. **`kb_ingest_jobs` 的 management.db 死回落**：队列在 `kb-retire-platform-ingest`（迁移 111）后已移出管理库、只活在独立 `kb_ingest_queue.db`（嵌入式迁移）。但 `kb_ingest_jobs.py` 仍：文件级 docstring 写"Management-DB backed"（早已不是）；`_database(None)` 回落 `Settings().database_url`（management.db）且**不跑迁移**——那张表已被 111 删掉，是条死/危险回落路径，且 `serve.py:210` 的 `config.queue_database_url or None` 在该 attr 为空时会真的触发它、读一张不存在的表。

2. **`/admin/kb/by-agent/{agent_id}` 冗余反查端点**：`kb-agent-binding` spec 只钦定 `/admin/kb/{kb_id}/agents` 与 `/admin/agents/{name}/kbs` 两个双向视图，`by-agent` 是**第三个非规范端点**、前端零消费、且用 int-id 键（与 platform 人面 URL 一律 name 的惯例不一致）。它唯一有别于 agent 侧视图的行为是"过滤已归档 KB"。

## What Changes

- **KB 队列去死回落**：`kb_ingest_jobs._database` 去掉 management.db 回落——`database_url` 缺失/空即报清晰错误（并始终对传入的 queue db 跑迁移）；修 `serve.py:210` 传真实 queue db url（不再 `or None`）；文件 docstring 改为"KB-local ingest job queue（queue db backed）"。
- **退役 `by-agent` 反查端点**：删 `kb_admin_api` 的 `GET /admin/kb/by-agent/{agent_id}`，把其"过滤已归档 KB"行为并入 spec 钦定的 `/admin/agents/{name}/kbs`（`list_agent_kbs`）；3 处反查集成测试迁到 agent 侧端点。

**不做**：`kb_ingest_jobs.py` 物理挪进 `knowledge_base/`（牵动 6+ importer + 需 shim，另议）；embedding 配置单源收敛（另议）；retrieval-playground 契约对齐（#3，挂 Tier-3 UI 一起做）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `kb-agent-binding`: 退役非规范的 `by-agent` 反查端点；明确 agent→KB 反查视图（`/admin/agents/{name}/kbs`）SHALL 排除已归档 KB 的绑定（承接原 by-agent 行为），双向视图收敛为 spec 钦定的两个。
- `kb-standalone-ingest`: 明确 KB ingest 队列的单一存储 = 本租户 `kb_ingest_queue.db`（经 `--config` 解析），队列访问 SHALL 显式提供 queue db url、SHALL NOT 隐式回落 management.db。

## Impact

- **代码**：`kb_ingest_jobs.py`（去回落 + docstring）、`knowledge_base/serve.py`（:210 传真实 url）、`platform/knowledge_base_management/kb_admin_api.py`（删 by-agent）、`platform/agent_management_console/agent_admin_api.py`（`list_agent_kbs` 加 archived 过滤）。
- **测试**：`kb_ingest_jobs` 的 None/空 url 报错单测；`serve` status 端点；`test_agent_kb_binding_routes.py` / `test_kb_admin_api.py` 的 by-agent 反查断言迁到 `/admin/agents/{name}/kbs`。
- **spec**：`kb-agent-binding` + `kb-standalone-ingest` 两处 delta。
- **无迁移、无 DB schema 变更**。
- ⚠️ **文件重叠 & 执行顺序**：本 change 改 `agent_admin_api.py`，与 `agent-identity-honest-naming`(A) 同文件不同函数——**apply SHALL 排在 A 合并之后**，避免并行 worktree 冲突。
