## 1. git_platform 可插拔包（config / backend / factory）

- [x] 1.1 (test) unit `tests/unit/test_git_platform_factory.py`：`create_git_platform` 按 provider 选型（bitbucket 命中）、未知 provider 记 warn 并 raise（不 fallback）、capability 门控（基类未实现的 PR 方法抛 `NotImplementedError`，能力布尔正确） → 见红
- [x] 1.2 (impl) `src/fleetent/integrations/git_platform/backend.py`：`BaseGitPlatformBackend`（`name`/`capabilities` ClassVar、`available()`、`push_branch(...)`、capability-gated PR 方法）+ `@dataclass(frozen=True) GitPlatformCapabilities` + `PullRequestRef` + `GitPlatformUnavailableError`；`factory.py`：`create_git_platform`；`config.py`：`GitPlatformConfig`；`__init__.py` 导出 public surface → 见绿
- [x] 1.3 (test) unit `tests/unit/test_git_platform_bitbucket.py`：`bitbucket` backend——respx 断 Bitbucket DC PR REST（open/get/merge/close 路径与 body）、`push_branch` dulwich 往返（真实 file:// bare repo）、token-in-url 日志脱敏、`available()` 探活永不抛 → 见红
- [x] 1.4 (impl) `src/fleetent/integrations/git_platform/backends/bitbucket.py`（优先实现）+ `backends/{gitea,gitlab}.py`（stub + capability 声明，未实现方法抛） → 见绿

## 2. 数据层：迁移 116 + backflow_store PR 列

- [x] 2.1 (test) integration `tests/integration/test_migration_116_backflow_pr_link.py`：apply 到 116 后 `backflow_proposals` 含 `pr_id`/`pr_branch`/`pr_url`/`pr_state`/`pr_target_branch`/`pr_merge_commit`（nullable）、旧行默认 NULL、可写读 → 见红
- [x] 2.2 (impl) `migrations/versions/116_backflow_pr_link.py`：守卫式 `add_column`（照 101/103 的 `_has_column` 风格），`down_revision="115"`；可选 `idx_backflow_proposals_pr_state`；downgrade drop columns → 见绿
- [x] 2.3 (test) integration `tests/integration/test_backflow_store_pr.py`：`set_pr_link`（branch/pr_id/pr_url 幂等更新）/`set_pr_state`（事务 + named params）/`_row_to_proposal` 透传 PR 列 / 按 PR 状态查询（`backed_up`/`pr_open`/未备份）→ 见红
- [x] 2.4 (impl) `backflow_store.py`：`set_pr_link`/`set_pr_state`/`list_by_pr_state`；`_row_to_proposal`/SELECT 透传 PR 列（nominate INSERT 不含 pr_* 列，nullable 默认 NULL）→ 见绿

## 3. backflow_pr_sweep（platform 独立定时任务）

- [x] 3.1 (test) unit `tests/unit/test_backflow_pr_sweep.py`：① pending 未备份 → `push_branch` 推**备份分支**（断言分支名 `<branch_prefix>/<agent>/<skill>` 非 main、`set_pr_state("backed_up")`）；② 已备份 + `auto_open_pr` → `open_pull_request` → `set_pr_state("pr_open")`；③ git 不可达（`GitPlatformUnavailableError`）→ `set_pr_state("deferred")`、不抛、下轮重试；FakeGitPlatformBackend 注入 → 见红
- [x] 3.2 (impl) `src/fleetent/platform/skill_management/backflow_pr_sweep.py`：`sweep()` / `run_now()`（类比 `kb_connector_sweep`），经注入的 backend factory + secret resolver，舱壁化每步独立 try/except → 见绿
- [x] 3.3 (test) unit 同文件：**断言 node ingestion 路径零 git**——`backflow_store` / `node_desired_state_api` 源码不含 `git_platform`/`push_branch`/`open_pull_request`（提名只存 bundle） → 见绿

## 4. backflow_api 治理改造

- [x] 4.1 (test) unit `tests/unit/test_backflow_api_pr.py`：`accept` = `merge_pull_request` → 复用 `align_pool_to_remote` → `set_current_version`/`set_drift(False)`/`bump_resync_epoch`（FakeGitPlatformBackend + mock pool_sync）；冲突 + `X-Confirm` 门控保留；`reject` = `close_pull_request` 且 pool 不动 + 清 drift + bump epoch；`fork` = push fork 分支 + 开/合 PR + 对齐 + 改绑；git 不可达 → deferred + 503、**不碰 drift/epoch** → 见红
- [x] 4.2 (impl) `backflow_api.py`：GitOps 启用时 accept/reject/fork 走 PR（merge/close/fork-branch + `align_pool_to_remote`），未启用保留 legacy 直写；新增 `POST /{id}/open-pr`（手动开单提案 PR）+ `POST /sync-backflow`（手动触发整轮 sweep）；git 调用包 `GitPlatformUnavailableError` → 503 → 见绿

## 5. 触发：scheduler job + config

- [x] 5.1 (test) integration `tests/integration/test_backflow_pr_scheduler.py`：注入 `_scheduler` 断言 `__skill_backflow_pr_sweep__` job 已注册 + config 字段默认 120 → 见红
- [x] 5.2 (impl) `config.py` `SchedulingSettings` 加 `skill_backflow_pr_sweep_interval_seconds: int = 120`；`server.py` `_build_platform_maintenance_scheduler` 注册 `__skill_backflow_pr_sweep__` interval job + secret resolver 注入（plane boundary 解耦） → 见绿

## 6. 前端：回流区 PR 态 + 手动控件（单独批次）

- [x] 6.1 (test) 前端 `frontend/src/features/skills/page.test.tsx`：回流提案展示 PR 状态（备份分支/PR 链接/state）；admin「立即开 PR」调 `POST /admin/skills/backflow/{id}/open-pr`、「立即同步回流」调 `POST /admin/skills/backflow/sync-backflow` → 见红
- [x] 6.2 (impl) 前端 `api.ts`/`page.tsx`：回流卡片加 PR 态徽章/分支/链接 + `useOpenBackflowPrMutation`（gitops 启用且未开 PR 时显示「Open PR」）/`useSyncBackflowMutation`（dialog 内「Sync backflow」）→ 见绿

## 7. Spec 同步与质量门

- [x] 7.1 spec 手工同步（openspec CLI 本机不可用）：新增 `specs/skill-git-platform/spec.md`；MODIFY `skill-backflow`（accept/reject/fork 改 PR + 备份分支/开PR/降级 ADDED）
- [x] 7.2 模块边界：`check_module_boundaries.py`（exit 0）；plane boundary guardrail 绿（14 测试，sweep/api 经注入解耦，不 import agent_lifecycle face）；`node_desired_state_api`/`backflow_store` 源码零 git_platform/push_branch/open_pull_request（源码守卫测试）
- [x] 7.3 收尾门禁：`make test-pr`（4024 passed）+ `make test-integration-ci`（2086 passed, 0 failed）全绿；`make test-frontend`（111 passed）绿；mypy 改动模块（13 文件）通过；行长 100；`node/test_skill_deployer.py` resync 路径 6 passed 不变
