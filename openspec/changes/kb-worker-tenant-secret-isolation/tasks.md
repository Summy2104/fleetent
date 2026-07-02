# Tasks: kb-worker-tenant-secret-isolation (#2 修根)

> 修确认可复现的跨租户凭证泄漏：凭证解析从进程全局 os.environ 改为 per-tenant scoped env。
> standalone/单租户向后兼容（默认 os.environ）。与 kb-deploy-multitenant-fixup 文件零重叠，可并行。
> TDD Hard Gate：测试在实现前，最窄命令红→绿。

## 1. 回归测试先行（红）

- [ ] 1.1 [test-red] 集成测：造两租户 A/B，各 `tenants/<t>/kb/.env` 用**同名** env 变量（`FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN`）不同值；worker 先后处理 A、B 的 connector_sync（或直接测凭证解析路径）→ 断言 A 用 A 的、B 用 B 的凭证。当前实现下 **B 误用 A 的 → 见红**（复现 bug）。跑最窄命令 → 见红。

## 2. resolver scoped 化

- [ ] 2.1 [impl] `connectors/confluence.py` + `connectors/google_drive.py`：`CredentialRefResolver.resolve(credential_ref, env: Mapping[str,str] | None = None)`——`env:` 引用对 `env`（缺省 `os.environ`）解析，不写死 `os.getenv`。`file://` 不变。
- [ ] 2.2 [impl] `service_config.load_tenant_connectors`：不再 `load_dotenv(env_path, override=False)` 进全局；改用 `dotenv_values(env_path)` 返回**局部 env 映射**（连同 connectors 一起返回给调用方）。

## 3. worker 线程 per-tenant env

- [ ] 3.1 [impl] `worker.py` 处理 connector_sync 时：取该租户局部 env 映射（§2.2），经 `_connector_settings` / `run_connector_sync` 下传到 connector 客户端构造与 resolver（多租户路径显式传 env）。若 `run_connector_sync` 深层不便加参数，则在 connector 客户端构造边界注入 scoped 凭证（design D3/Open Questions，取最小侵入点）。跑 §1.1 → 见绿。
- [ ] 3.2 [verify] grep 确认多租户 job 路径无残留 `os.getenv`/`os.environ` 读 connector secret；standalone 路径仍默认 os.environ（未破坏）。

## 4. 收尾门禁（全绿才算完）

- [ ] 4.1 边界护栏：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`。
- [ ] 4.2 `openspec validate kb-worker-tenant-secret-isolation --strict`
- [ ] 4.3 `uv run mypy src`（resolver 签名变更后类型一致）。
- [ ] 4.4 `make test-pr` + `make test-integration-ci`，判据"对照 main 基线无新增失败"（含新增隔离回归测试；standalone 相关测试仍绿）。
- [ ] 4.5 tasks.md 全 `[x]`；功能分支 `openspec archive kb-worker-tenant-secret-isolation`（同步 kb-ingest-worker spec）；**不扫 openspec/changes/archive/ 历史产物**；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
