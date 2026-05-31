## Why

`test-suite-organization` 已经建立了 `tests/unit/`、`tests/integration/`、`tests/e2e/`
和 `tests/evaluation/` 四层目录，以及对应的 Makefile / Bitbucket CI 入口。
但历史测试仍大量平铺在 `tests/` 根目录，导致两个问题：

- `tests/unit` 不能代表真实的快速单元测试集，PR unit gate 覆盖不足。
- 新增测试已经有规则，旧测试仍混在根目录，团队和 AI agent 很难判断应该参考哪种组织方式。

本 change 专门处理历史测试迁移，把现有平铺测试按成本和依赖范围移动到对应目录，并让 CI
真正基于迁移后的分层测试集工作。

## What Changes

- 盘点 `tests/` 根目录现有 `test_*.py` 文件，并按以下规则分类：
  - `tests/unit/`：单模块行为测试，外部依赖通过 mock / monkeypatch 隔离。
  - `tests/integration/`：跨模块协作、SQLite / Alembic / FastAPI / IM gateway / runtime 边界测试。
  - `tests/e2e/`：CLI、HTTP 服务或真实入口的完整链路测试。
  - `tests/evaluation/`：memory、long-term context、reflection、knowledge-base 等效果评估测试。
- 将历史平铺测试移动到对应目录，保持文件名可追踪。
- 修正被移动测试的 import、fixture 路径和 pytest collection 问题。
- 收紧 `pytest.ini`，不再把 `tests/` 根目录作为长期 test collection layer。
- 更新 Bitbucket CI，使 PR/main 的 unit + integration gate 覆盖迁移后的真实测试集。
- 更新 `AGENTS.md` / `CLAUDE.md`，明确历史迁移完成后不得再向 `tests/` 根目录新增测试。

## Initial Classification

具体执行时可以根据测试内容微调，但默认按下面方向迁移：

- `tests/unit/`：
  - `test_config.py`
  - `test_context_mgr.py`
  - `test_model_router.py`
  - `test_tool_registry.py`
  - `test_tools.py`
  - `test_normalizer_allowlist.py`
  - `test_permission_gate.py`
  - `test_blocklist.py`
  - `test_quota.py`
  - `test_module_boundaries.py`
- `tests/integration/`：
  - `test_2fa.py`
  - `test_admin.py`
  - `test_agent_loop.py`
  - `test_agent_store.py`
  - `test_api_key_auth.py`
  - `test_api_key_store.py`
  - `test_audit_log.py`
  - `test_auth.py`
  - `test_cron_scheduler.py`
  - `test_db.py`
  - `test_im_channel_allowlist.py`
  - `test_im_connector_config.py`
  - `test_im_connector_manager.py`
  - `test_im_connector_store.py`
  - `test_im_gateway.py`
  - `test_im_user_store.py`
  - `test_im_workbench.py`
  - `test_integration.py`
  - `test_long_term_ctx.py`
  - `test_mcp_client.py`
  - `test_memory_layer.py`
  - `test_reflection.py`
  - `test_sandbox_client.py`
  - `test_schedule_store.py`
  - `test_server.py`
  - `test_server_lifespan.py`
  - `test_session_mgr.py`
  - `test_skill_registry.py`
  - `test_sub_agent.py`
  - `test_tools_schedule.py`
  - `test_user_admin_api.py`
  - `test_user_store.py`
  - `test_user_store_roles.py`
  - `test_vector_store.py`
  - `test_web_user_mgmt.py`
  - `test_webhook_router.py`
  - `test_webhook_server.py`
- `tests/e2e/`：
  - 仅迁移真正启动服务、CLI 或完整用户入口的测试；如果现有根目录文件只是 FastAPI
    in-process client，则保留为 integration。
- `tests/evaluation/`：
  - 当前不迁移历史文件，除非执行时发现已有测试是效果评估而非行为验证。

## Module Boundary Impact

- **owning package**：无运行时代码 owning package；本 change 属于 test / CI ownership。
- **public API surface**：无新增或修改 public API。
- **owned tables**：无。
- **config namespace**：无。
- **cross-module dependencies**：只调整测试文件位置，不新增模块依赖。
- **migration / shim plan**：移动测试文件时保持文件名，必要时只修正测试 import / fixture 路径；
  不为旧测试路径提供兼容 shim。

## Impact

- **代码**：不修改运行时代码，除非测试移动暴露路径或 fixture bug。
- **测试**：大规模移动历史测试文件；目标是根目录不再保留 `test_*.py`。
- **CI**：PR/main 的 unit 和 integration gate 覆盖迁移后的真实测试集。
- **文档**：更新 agent 指南，移除根目录兼容期表述。
- **不包含**：
  - 不新增业务功能。
  - 不重写测试语义。
  - 不引入真实 LLM / embedding / 外部服务测试。
  - 不把 e2e / evaluation 加入默认 PR gate。
