## 1. 路径契约与静态护栏

- [ ] 1.1 Write failing tests：新增/更新 path tests，断言 `paths.logs_dir()` 为 `<home>/logs`、`paths.diagnostics_dir()` 为 `<home>/diagnostics`，并断言默认管理库仍为 `<home>/management.db`
- [ ] 1.2 Write failing tests：新增 residual path guard，扫描非 archive 的 `src/fleetent` 与关键 e2e helper，禁止新增 canonical `FLEETENT_HOME/data/` 默认写入、`home/agents/<name>`、`data/default/<agent>/agent_state.db`
- [ ] 1.3 Implement：更新 `paths.py` 与相关配置默认值；保留 `paths.data_dir()` 但标注 legacy/compat，不作为 platform 或 agent 默认产物根
- [ ] 1.4 Verify green：运行 1.1/1.2 的最窄测试，必须由红转绿

## 2. Platform logs 与 diagnostics 根级化

- [ ] 2.1 Write failing tests：structured logging 默认目录为 `<home>/logs`，`Settings().diagnostics.export_dir` 默认 `<home>/diagnostics`
- [ ] 2.2 Implement：更新 `structured_logging._LoggingConfig`、`configure_structured_logging()` fallback、`config.DiagnosticsSettings.export_dir` 与相关文档/测试
- [ ] 2.3 Verify green：运行 observability logging、config paths、diagnostics export/retention 相关最窄测试，必须由红转绿

## 3. Agent runtime 全量 data sink 重定向

- [ ] 3.1 Write failing tests：`_redirect_agent_data_paths(home)` 会重绑定 `session_mgr.SESSIONS_DIR`、`access.APPROVALS_PATH`、`diagnostics._default_data_dir`、`eval_logger.TRACE_PATH`、sandbox workspace root、tool spillover、sandbox output 到 `<home>/data/*`
- [ ] 3.2 Write failing tests：最小 agent boot 后不会创建 `<fleetent_home>/data/traces.jsonl`、`data/workspaces`、`data/tool_spillover`、`data/sandbox_output`
- [ ] 3.3 Implement：扩展 `runtime.agent_app._redirect_agent_data_paths()` 或拆出 focused helper，确保在 `_start_infra()` 与任何 sandbox/tool/trace 写入前执行
- [ ] 3.4 Verify green：运行 agent app data redirect、agent runtime CLI、eval_logger、sandbox output spill、tool truncation 相关最窄测试，必须由红转绿

## 4. Sandbox workspace / spillover 归属收口

- [ ] 4.1 Write failing tests：agent runtime 下 `host_workspace_dir(scope_key)` 使用 `<agent-home>/data/workspaces/<scope>`，不使用 `<fleetent_home>/data/workspaces`
- [ ] 4.2 Write failing tests：tool result spillover 与 sandbox output spill fallback 在 agent runtime 下写 `<agent-home>/data/tool_spillover` 与 `<agent-home>/data/sandbox_output`
- [ ] 4.3 Implement：为 sandbox manager / tool truncation / output spill 提供可注入根目录或 setter，并由 agent runtime boot 注入；保持测试 monkeypatch 能力
- [ ] 4.4 Verify green：运行 sandbox workspace、sandbox large output spill、tool result truncation、file tools workspace 相关最窄测试，必须由红转绿

## 5. E2E helper 与文档 inventory 修正

- [ ] 5.1 Write failing tests：更新或新增 helper-level 测试，断言 managed stack agent state DB helper 返回 `home/tenants/<tenant>/agents/<name>/data/agent_state.db`
- [ ] 5.2 Implement：修正 `tests/e2e/*` helper 中旧路径；更新 `docs/architecture/agent-home-layout.md` 与 `docs/architecture/data-model.md`，列清 home / tenant / agent 文件 inventory 与 owner
- [ ] 5.3 Verify green：运行受影响 e2e helper smoke、agent-home-layout residual path guard、OpenSpec 最窄 validate，必须由红转绿

## 6. Fresh dev home 动态验收

- [ ] 6.1 Write failing test/script：用临时 `FLEETENT_HOME` 执行 dev bootstrap + agent runtime 初始化等价路径，产出 inventory 并断言 `FLEETENT_HOME/data/` 未承载任何 agent runtime 文件
- [ ] 6.2 Implement：补齐缺失重定向与 Makefile/install/dev docs，使 `make dev-bootstrap` 和 managed node 启动后符合 inventory
- [ ] 6.3 Verify green：运行动态 inventory 测试；手工或脚本化执行 fresh home smoke，确认 `logs/`、`diagnostics/`、`node/`、`tenants/` 分层正确

## 7. 收尾验证

- [ ] 7.1 运行 `openspec validate cleanup-runtime-path-ownership --strict`
- [ ] 7.2 运行 `make test-pr`
- [ ] 7.3 运行相关 integration：`uv run pytest tests/integration/test_agent_db_schema_init.py tests/integration/test_tenant_router.py tests/integration/test_agent_memory_db_init.py tests/integration/test_diagnostics_export_recursive.py -q`
- [ ] 7.4 手工 grep 非 archive 路径，确认旧 canonical 命中仅存在于明确负例/legacy tests：`FLEETENT_HOME/data/`、`home/agents/`、`data/default/`
- [ ] 7.5 所有 checkbox 完成后再执行 `opsx:archive`，并同步 specs；archive 前不得跳过任何 TDD 红绿步骤
