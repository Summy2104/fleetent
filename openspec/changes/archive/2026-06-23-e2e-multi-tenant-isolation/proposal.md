## Why

多主体部署的核心承诺是**数据不串**：每个 tenant 的 KB、共享记忆、agent 运行库、向量底座按 `<data_dir>/<tenant>/...` 物理隔离（`tenant_router.SQLiteTenantBackend`）。这条隔离至今**只有单进程 unit/integration 覆盖**——没有一条 e2e 在真实多进程 managed 栈下证明"起两个 tenant、各自写数据、互相查不到"。隔离是 P1 安全契约，回归代价极高，必须有端到端守门。地基 harness（`e2e-managed-stack-coverage`）已落地，正好解锁这条覆盖。

## What Changes

- 新增 e2e：在多进程 managed 栈下起 **两个 tenant**（各一个 placed agent），分别写入各自的 KB / agent-state，断言：
  - **文件级物理隔离**：`<home>/<tenant-a>/...` 与 `<home>/<tenant-b>/...` 是独立 SQLite 文件，互不覆盖。
  - **跨租户查询无串数据**：在 tenant-a 写入的 KB 条目，经 tenant-b 的检索路径查不到（反之亦然）。
  - **agent 运行库隔离**：tenant-a 的 agent-state（会话/记忆）不可见于 tenant-b。
- 新增 harness fixture `managed_stack_two_tenants`（放 e2e 专属 helper，**不重构核心 `managed_stack`**），复用已落地的多进程起栈 + 确定性 LLM stub。
- 进 slow/nightly lane（`make test-e2e`），**不**进 per-merge `make test-pr`。

## Capabilities

### New Capabilities
- `e2e-multi-tenant-isolation`: 多进程 managed 栈下的多租户数据隔离端到端覆盖——两 tenant 起栈、各写数据、断言文件级隔离与跨租户查询零串数据。

### Modified Capabilities
（无；不改任何现有 capability 的 requirement，纯新增 e2e 覆盖。）

## Impact

纯测试侧改动，零 src 产品代码改动。

- **owning package**：`tests/e2e`（新增 test 文件 + tenant helper fixture）；复用 `tests/integration/_migration_template`、`tests/e2e/conftest.py::managed_stack` 既有基建
- **public API surface**：无（纯测试侧；不新增/改 src public API）
- **owned tables**：无（测试用隔离临时库；只读验证 `tenant_router` 落盘的隔离结构）
- **config namespace**：无
- **cross-module dependencies**：测试编排既有 platform/node/agent 三进程 + `tenant_router` 落盘路径；不引入 src 跨模块依赖
- **migration / shim**：无（复用 `apply_migrations`）
- **受影响代码**：仅 `tests/e2e/`；核心 `managed_stack` fixture **冻结不动**（新增 `managed_stack_two_tenants` 于独占 helper，避免与并行波 D2/D3 撞 `conftest.py`）
- **CI**：进 `make test-e2e` slow/nightly lane，不进 per-merge 门禁
