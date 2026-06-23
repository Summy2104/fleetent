## 1. 路径与管理库主干（必须最先落）

- [x] 1.1 Write failing tests：`paths.py` 暴露 `management_db_path()`、`tenant_dir()`、`tenant_agent_home_dir()`、`tenant_agent_data_dir()`，默认 `agent_home_dir()`/`agent_data_dir()` 作为 `default` tenant shim；默认 DB URL 指向 `<FLEETENT_HOME>/management.db` 而非 `data/management.db`
- [x] 1.2 Implement：更新 `paths.py`、`config.Settings.database_url`、`user_store.DB_PATH` 及直接断言默认管理库路径的测试/配置路径，不迁移旧 `data/management.db`
- [x] 1.3 Verify green：运行 1.1 的最窄相关测试，必须由红转绿

## 2. Tenant router 与 agent DB 拍平

- [x] 2.1 Write failing tests：`SQLiteTenantBackend` 映射 `tenant_scope(T)` 到 `tenants/T/kb.db`，映射 `agent_scope(T,A)` 到 `tenants/T/agents/A/data/{agent_state,agent_vectors,agent_memory,agent_memory_vectors}`，且不创建 `data/T/A/`
- [x] 2.2 Implement：更新 `tenant_router.py` 的 SQLite backend 路径语义与 docstring；调整 `_init_agent_db_schema()` 参数语义/调用点，使 agent home data 目录拍平
- [x] 2.3 Verify green：运行 tenant router、agent DB schema init、multi-tenant fanout、agent_memory DB init 的最窄相关测试，必须由红转绿

## 3. Runtime CLI 与 standalone tenant-first home

- [x] 3.1 Write failing tests：`fleetent agent init/run` 默认解析 `tenants/default/agents/<name>/`，显式 `--home` 最高优先级，runtime data redirects under `<home>/data`
- [x] 3.2 Implement：更新 `runtime.agent_app.resolve_home`、agent init 脚手架、CLI 参数传递和受影响的 path tests
- [x] 3.3 Verify green：运行 agent runtime CLI、agent init、data redirect 相关最窄测试，必须由红转绿

## 4. Node tenant-aware home ownership

- [x] 4.1 Write failing tests：node desired-state agent entry 携带 `tenant_id`；node backend/reconcile/forwarder/im-edge 使用 `tenants/<tenant>/agents/<name>`；停止不再期望 agent 时擦除 tenant-aware `.env`
- [x] 4.2 Implement：更新 node provider/reconcile/backend/forwarder/im_edge 的 home 解析，hash/cache/status 仍以 agent identity 稳定关联；node spawn 显式传 tenant-aware `--home`
- [x] 4.3 Verify green：运行 node supervisor、forwarder、managed stack home materialize 相关最窄测试，必须由红转绿

## 5. Platform lifecycle 改为 desired-state payload builder

- [x] 5.1 Write failing tests：platform create/update/apply/clone managed agent 不写 tenant-aware agent home；desired-state 仍包含完整 agent config、env/secret 输入和 skill manifest 所需字段
- [x] 5.2 Implement：拆分/收窄 `platform.agent_lifecycle.materialize`，保留 `agent_file_from_store()` / desired-state builder；managed 路径禁用 `write_home()`，legacy/local helper 明确非 managed
- [x] 5.3 Verify green：运行 platform agent lifecycle、node desired-state API、secret injection 相关最窄测试，必须由红转绿

## 6. Skill bundle distribution

- [x] 6.1 Write failing tests：platform bundle API 对 `skill_name + base_version` 懒生成 immutable tar.gz cache；排除 `.git`；拒绝绝对路径、`..`、symlink/hardlink 逃逸；manifest 含 `bundle_url` 与 `bundle_sha256`
- [x] 6.2 Implement：新增 platform skill bundle cache/service/API，复用公共 skill 池与 pool git metadata；desired-state skill manifest 只传 metadata，不内联文件内容
- [x] 6.3 Verify green：运行 skill bundle distribution 与 desired-state manifest 的最窄测试，必须由红转绿

## 7. Node skill bundle 部署

- [x] 7.1 Write failing tests：node 发现本地缺少 desired skill 版本时下载 bundle、校验 sha256、安全解压到临时目录、原子替换 `skills/<skill>/`；本地版本匹配时跳过；drift 时不覆盖
- [x] 7.2 Implement：新增 node skill deployer，接入 reconcile；记录本地 `base_version/base_commit/home_hash` metadata；错误隔离，单 skill 失败不破坏 agent.yaml/.env 写入
- [x] 7.3 Verify green：运行 node skill deployer/reconcile 相关最窄测试，必须由红转绿

## 8. Node skill drift observation 与 backflow bundle 拉取

- [x] 8.1 Write failing tests：node 扫描真实 home skill 副本，内容 hash 或 runtime provenance 变化时 status 上报 drift；platform 接收并更新 `agent_skills` 观测态；managed backflow nomination 从 owning node 拉 bundle，不读 platform-local home
- [x] 8.2 Implement：扩展 node status payload、platform status ingestion、`agent_skills` 必要字段/迁移、node skill bundle read endpoint、backflow_store managed nomination 路径
- [x] 8.3 Verify green：运行 skill drift observation、backflow nomination、skill admin store 相关最窄测试，必须由红转绿

## 9. Platform read projection 与长尾路径收口

- [x] 9.1 Write failing tests：platform read projection 经 tenant-first router 只读 `tenants/<tenant>/agents/<agent>/data/*.db`；不读取 `data/<tenant>/<agent>`；diagnostics/backup/redaction 识别新 agent `.env` 与 DB 路径
- [x] 9.2 Implement：更新 `platform/read_projection.py`、KB worker/admin router 构造、diagnostics/export/backup/runbook 直接相关路径；保留必要 default shim 但 managed 路径不得依赖旧布局
- [x] 9.3 Verify green：运行 platform read projection、KB worker/admin、diagnostics/redaction 路径相关最窄测试，必须由红转绿

## 10. 边界护栏与文档同步

- [x] 10.1 Write failing tests：新增/更新护栏，禁止 managed platform lifecycle 写 agent home；禁止 agent/runtime/independent packages import platform；禁止新增旧 `data/<tenant>/<agent>` 断言；确认 node 不读取 Git repo
- [x] 10.2 Implement：更新护栏测试、`docs/architecture/agent-home-layout.md`、`docs/architecture/data-model.md`、直接冲突的 capability docs/spec references
- [x] 10.3 Verify green：运行 module dependency guardrails、path residual grep/guardrail、OpenSpec validate 最窄命令，必须由红转绿

## 11. 收尾验证

- [x] 11.1 运行 `openspec validate tenant-first-layout --strict`
- [x] 11.2 运行 `make test-pr`
- [x] 11.3 运行 `make test-unit-ci`
- [x] 11.4 本 change 跨路径/DB/router/node/platform/skill 边界，运行全量 integration：`uv run pytest tests/integration -q`，判据为对照 main 无新增失败
- [x] 11.5 手工 grep 确认关键旧 canonical 路径不再出现在 managed/runtime 契约中：`data/<tenant>/<agent>`、`FLEETENT_HOME/agents/<name>`、`data/management.db`；仅允许 legacy compatibility、历史 archive 和明确旧布局文档段落
- [x] 11.6 所有 checkbox 完成后再执行 `opsx:archive`，并同步 specs；archive 前不得跳过任何 TDD 红绿步骤
