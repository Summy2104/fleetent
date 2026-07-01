# Tasks: kb-cleanup-2

> 执行前置：本 change 改 `agent_admin_api.py`，与 `agent-identity-honest-naming`(A) 同文件——**须在 A 合并进 main 之后**再建 worktree（`git pull origin main` 拿到 A 的改动），避免冲突。
> TDD Hard Gate：测试任务在实现任务之前，最窄命令见红→见绿。

## 1. KB 队列去 management.db 死回落（#1）

- [ ] 1.1 [test-red] 加/改 `kb_ingest_jobs` 单测：`_database`（及经它的 public 函数如 `get_job`）在 `database_url` 为 `None`/空串时 SHALL `raise`（不回落 `Settings().database_url`）。跑 `uv run pytest tests/unit -k kb_ingest_jobs -x -q` → **见红**（现会回落 mgmt.db）。
- [ ] 1.2 [impl] `kb_ingest_jobs._database`：去掉 `or Settings().database_url`，`database_url` 缺失/空即 `raise ValueError`，并**始终** `migrate(database, _LOCAL_QUEUE_MIGRATIONS)`；public 函数签名 `database_url: str | None = None` → `database_url: str`（必填）。跑同命令 → **见绿**。
- [ ] 1.3 [impl] 文件级 docstring `"Management-DB backed KB ingest job queue."` → 纠正为 KB 本地队列（queue-db backed）表述。
- [ ] 1.4 [impl] `knowledge_base/serve.py:210`：`database_url=config.queue_database_url or None` → 传真实 `config.queue_database_url`；**核实**该 status 端点 config 确有 queue db url 来源（若原靠空 url 静默读 mgmt.db，补接线让其拿到本租户 queue db——这是修 bug）。跑 `uv run pytest tests/unit -k serve -q`（或相应集成）见绿。
- [ ] 1.5 grep 确认 `kb_ingest_jobs` 无 `Settings().database_url` 回落残留、无调用点漏传 `database_url`。

## 2. 退役 by-agent 反查端点、并入 archived 过滤（#2）

- [ ] 2.1 [test-red] 改 `tests/integration/test_agent_kb_binding_routes.py` + `test_kb_admin_api.py`：(a) 断言 `GET /admin/kb/by-agent/{id}` **不存在**（404 / 路由缺失守卫）；(b) 把原 by-agent 的反查断言迁到 `GET /admin/agents/{name}/kbs`，并新增断言其**排除已归档 KB**（用原 by-agent 测试里的 archived/stale 场景，shape 从 `{agent_id,kb_ids}` 换成 `{agent,kb_ids}`）。跑 `uv run pytest tests/integration/test_agent_kb_binding_routes.py tests/integration/test_kb_admin_api.py -x -q` → **见红**（by-agent 仍在、agent 侧尚不滤 archived）。
- [ ] 2.2 [impl] `platform/knowledge_base_management/kb_admin_api.py`：删除 `@router.get("/by-agent/{agent_id}")` 及其 `kbs_for_agent` 处理函数。
- [ ] 2.3 [impl] `platform/agent_management_console/agent_admin_api.py` 的 `list_agent_kbs`：并入 archived 过滤——取本租户已归档 KB 集合（复用原 by-agent 的 `kb_engine_list(tenant_id)` 路径），从 `list_kbs_for_agent` 结果中剔除已归档 kb_id。跑 §2.1 命令 → **见绿**。
- [ ] 2.4 grep 确认 `by-agent` 在 src/tests 无残留（仅剩测试"不存在"守卫与 spec 说明）；确认前端本就无消费（无需改前端）。

## 3. 收尾门禁（全绿才算完）

- [ ] 3.1 全库 grep：`grep -rn "by-agent" src` 为空；`grep -rn "Settings().database_url" src/fleetent/kb_ingest_jobs.py` 为空。
- [ ] 3.2 `openspec validate kb-cleanup-2 --strict`
- [ ] 3.3 `uv run mypy src`（队列函数签名收紧为必填后类型一致）
- [ ] 3.4 `make test-pr` + `make test-integration-ci`，判据"对照 main 基线无新增失败"（含 `test_agent_kb_binding_routes.py` / `test_kb_admin_api.py` / kb_ingest_jobs / serve 相关）。
- [ ] 3.5 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（`list_agent_kbs` 引 kb 引擎列表为 platform→platform，不越 agent/platform 边界；确认护栏绿）。
- [ ] 3.6 tasks.md 全 `[x]`；功能分支 `openspec archive kb-cleanup-2`（同步 `kb-agent-binding` + `kb-standalone-ingest` 两 spec）；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
