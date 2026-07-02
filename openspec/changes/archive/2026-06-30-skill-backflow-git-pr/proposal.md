## Why

入站 change `skill-gitops-inbound` 已让外部 git 仓库成为 skill 内容权威源（platform 定时/webhook fetch + reset --hard 镜像进 pool）。但**出站回流**仍是老逻辑：agent 临场改 skill → node 报漂移 → platform 提名 proposal 存 bundle → admin 在后台点 accept/reject/fork，**accept 直接把 bundle 写进 pool**（`backflow_api.accept_proposal` → `_write_bundle_atomic` + `commit_pool`）。

这在 GitOps 下有两个问题：(1) accept 直写 pool 与入站「外部 git 为权威、pool 是只读镜像」冲突——下次 reset 会丢弃这次直写；(2) agent 提的 skill 改动**绕开 git**，没有 PR / review / CI / 评审留痕，拒绝即丢失。

本 change 把回流改造成「**先推备份分支保命 → 定时/手动开 PR → 人合并 main → 复用入站对齐 pool**」：agent 改动经 git 的 PR 流程评审，与人手编辑同路；备份分支保证改动不丢；git 操作**全部只在 platform 侧**，node 与 agent 零 git 依赖不变。

> 依赖：复用入站已实现的 `pool_sync.align_pool_to_remote`（合并后对齐 pool）、`git_source_store` 配置（含 115 已建的 `branch_prefix`/`auto_open_pr`/凭证 env 名）、`pool_sync.set_secret_resolver`（凭证注入）。F 的功能分支基于入站分支栈式开发（入站未合并 main 前）。

## What Changes

- **新 `integrations/git_platform` 包**（仿 `integrations/sandbox` 范式，**不依赖 platform**）：`BaseGitPlatformBackend`（`available()` 探活永不抛、`push_branch(...)` 走 dulwich git 协议推备份/fork 分支）+ capability-gated PR 生命周期（`open_pull_request`/`get_pull_request`/`merge_pull_request`/`close_pull_request` 走平台 REST，基类抛 `NotImplementedError`，调用方按 `GitPlatformCapabilities` 布尔门控、不 isinstance）+ `PullRequestRef` + `GitPlatformUnavailable`；`factory.create_git_platform` 按 provider 选型（未知 provider 记 warn 并**抛**，不 fallback）；`backends/bitbucket.py`（优先实现，Bitbucket DC REST + dulwich push、token-in-url 日志脱敏）+ `backends/{gitea,gitlab}.py` stub。
- **迁移 116 + `backflow_store` PR 列**：`backflow_proposals` 加 nullable 列 `pr_id`/`pr_branch`/`pr_url`/`pr_state`(`backed_up`|`pr_open`|`merged`|`closed`|`deferred`)/`pr_target_branch`/`pr_merge_commit`（+可选 `pr_state` 索引）；`set_pr_link`/`set_pr_state`（事务 + named params）；`_row_to_proposal` 透传 PR 列；按 PR 状态查询供 sweep 扫描。配置表 `skill_git_source` 不动（115 已含所需列）。
- **新 `backflow_pr_sweep`（platform 独立定时任务，类比 `kb_connector_sweep`）**：① 扫 pending 且未备份的 proposal → `git_platform.push_branch` 推**备份分支** `<branch_prefix>/<agent>/<skill>`（非 main，即时保命）→ `set_pr_state("backed_up")`；② 扫已备份且 `auto_open_pr` 开的 → `open_pull_request` → `set_pr_state("pr_open")`；git 不可达 → `set_pr_state("deferred")` 下轮重试，舱壁化不崩。**提名（`backflow_store.nominate`）与 node 上报路径只存 bundle、零 git 依赖**（不重新引入「提名即开 PR」钩子）。
- **`backflow_api` 治理改造**：`accept` = `merge_pull_request` → 复用 `pool_sync.align_pool_to_remote` 对齐 pool → `set_current_version`/`set_drift(False)`/`bump_resync_epoch`（不再 `_write_bundle_atomic`+`commit_pool` 直写）；`reject` = `close_pull_request`，pool 不动 + 清 drift + `bump_resync_epoch`；`fork` = push fork 分支 → 开/合 PR → 对齐 → 改绑 + 原 skill resync；新增 `POST /{id}/open-pr`（手动对单提案开 PR）+ `POST /sync-backflow`（手动触发整轮 sweep）；所有 git 调用包 `GitPlatformUnavailable` → deferred + 503，**不碰 drift/epoch**。
- **触发与配置**：`config.py` `SchedulingSettings` 加 `skill_backflow_pr_sweep_interval_seconds`（默认 120，回流保命优先）；`server.py` `_build_platform_maintenance_scheduler` 注册 `__skill_backflow_pr_sweep__` interval job。
- **（前端，单独批次）**：skills 页回流审批区展示每条提案的 PR 状态（备份分支/PR 链接/状态）+ admin「立即开 PR」「立即同步回流」手动控件。

## Capabilities

### New Capabilities

- `skill-git-platform`：platform 侧可插拔的 git 平台后端抽象——push 备份/fork 分支（dulwich git 协议）+ capability-gated 的 PR 生命周期（开/查/合/关，走平台 REST），优先 Bitbucket，Gitea/GitLab 预留 stub；factory 未知 provider 直接抛。

### Modified Capabilities

- `skill-backflow`：回流由「accept 直写 pool」改为「定时推备份分支 → 开 PR → 人合并 main → 复用入站对齐 pool」；nominate/node 上报仍只存 bundle、零 git；accept/reject/fork 改为操作 PR；新增手动 open-pr / sync-backflow。

## Impact

- **owning package**：新增 `fleetent.integrations.git_platform`（底层、不依赖 platform）；改动归 `platform.skill_management`（新 `backflow_pr_sweep.py`，改 `backflow_store.py`/`backflow_api.py`）；`server.py`（注册 sweep）；`config.py`（SchedulingSettings 加间隔）；`frontend/src/features/skills/`（回流区 PR 态 + 手动控件，单独批次）。
- **public API surface**：`git_platform.__init__` 导出 `BaseGitPlatformBackend`/`GitPlatformCapabilities`/`PullRequestRef`/`GitPlatformUnavailable`/`create_git_platform`；`backflow_store` 新增 `set_pr_link`/`set_pr_state` + 按 PR 状态查询；`backflow_pr_sweep` 导出 `sweep`/`run_now`；HTTP 新增 `POST /admin/skills/backflow/{id}/open-pr` + `POST /admin/skills/backflow/sync-backflow`。skill_management 只经 git_platform public API 调用，不 import `backends.*`。
- **owned tables**：`backflow_proposals`（skill_management 独占）仅加 nullable PR 列；`git_platform` 包无表；`skill_git_source` 复用不动（115 已含 branch_prefix/auto_open_pr/凭证 env 名）。
- **config namespace**：新增 `scheduling.skill_backflow_pr_sweep_interval_seconds`（默认 120）；复用 DB `skill_git_source`（remote_url/branch/branch_prefix/auto_open_pr）+ `agent_secrets`（凭证 env 名引用）。
- **cross-module dependencies**：`backflow_api / backflow_pr_sweep → git_platform(public) + pool_sync(align_pool_to_remote) + backflow_store + git_source_store + secret_store(注入)`；`git_platform → dulwich / httpx / paths`（**不反依赖 platform**）；`server → backflow_pr_sweep`。**`node_desired_state_api` 仍零 git 钩子；agent runtime / node 零改动、零 git 依赖、node 不引入 DB**；分发链路不改。
- **migration / shim plan**：仅新增 Alembic `116_backflow_pr_link`（`down_revision="115"`，守卫式 add_column，照 101/103 风格）；无 shim；旧 proposal `pr_*=NULL` 视为未备份、由 sweep 补推；回滚 drop columns。
