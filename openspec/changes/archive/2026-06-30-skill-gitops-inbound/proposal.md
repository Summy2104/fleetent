## Why

fleetent 的 skill 内容当前以 platform 进程内的 dulwich git pool（`pool_git.py`）为权威源——有版本/diff/回滚，但这个 git **无 remote**：无法 clone、无法在 Bitbucket/Gitea 发 PR 评审、无法外部 CI 校验、开发者无法用 git 工具链写 skill 再 push。写入口只有内置 seed、后台 UI（`create_skill` → `_write_skill_content` 落盘 + commit）、agent 回流。

本 change 把**外部 git 仓库**变成 skill 内容的唯一权威源（GitOps 入站半边）：platform 定时/webhook 从外部 git 拉取（fetch + reset --hard 镜像）进本地 pool，再经**现有分发链路**下发 agent；UI 转纯只读。出站回流（agent 改动 → 备份分支 + PR）拆到后续 change `skill-backflow-git-pr`。

> 与在途 change 的关系：`skill-create-persist-content`（已实现 inline create 落盘）的写入口将被本 change 的只读化**有意取代**（GitOps 下内容只从 git 来）；`node-skill-sync-cleanup`（在途 proposal，未来或把下游分发由 bundle 改 desired-state 内嵌）与本 change **正交**——因 skill version = pool commit SHA，下游读 pool 的方式无论怎么变，「pool 内容正确 + current_version 更新」这一入站契约不变。

## What Changes

- **`pool_git` 加 remote 同步原语**：`init_pool_with_remote` / `fetch_remote`（→远端 sha）/ `reset_pool_to` / `list_pool_skills`；基于 dulwich `porcelain.fetch`（接受 basic auth）+ `reset --hard`（镜像语义，避免合并）；全程持现有 `_FileLock` 与 `commit_pool` 串行化。
- **新 `pool_sync` 同步服务**：`sync_external_git`——fetch → 远端 sha 未变则短路 → reset → 逐 skill 入站审计兜底（复用 `skills/audit.py`，severe → quarantine、不进 current_version）→ 重算 `current_version`（`pool_version_for_skill`）→ 外部已删的 skill 软删（archived，保绑定）→ `materialize_builtin_skills` 恢复内置 seed 并 commit → 记录同步状态；最外层舱壁化（失败写 `last_sync_error`，绝不抛）。`is_sync_due` 纯函数；`align_pool_to_remote` 供后续出站 change 复用。
- **新 `git_source_store` + 表 `skill_git_source`（迁移 115）**：统一外部 git 源配置（provider/url/branch/凭证 env 名/同步间隔等）+ 同步状态（last_synced_commit/at/error）；凭证值走 `agent_secrets`（env 名引用），不入库明文、不进 git。
- **触发**：`server.py` 的 `_build_platform_maintenance_scheduler`（现为空壳）首次注册 interval job `__skill_git_sync_sweep__`；新 `skill_git_webhook_api`：`POST /webhook`（HMAC 校验复用 `webhook_router.verify_signature`，强制配 secret 否则拒收，payload 仅触发、内容以 fetch 为准）+ `POST /sync`（admin 手动）+ `GET /status`（凭证脱敏）。
- **UI 只读化**：`skill_admin_api` 的内容写端点（`create`/`edit`/`upload`/`archive`/`restore`/`force_publish`）改返 409；**保留** 读取/绑定矩阵/启停/版本历史/diff/observability/reload。前端 skills 页移除写入口 + 加「权威源在 git」只读 Banner + git 同步状态卡片。
- **运维脚本与文档**：`scripts/bootstrap_skill_git.py`（首次把现有 pool 推到外部空仓，非空拒绝）+ `scripts/validate_skills.py`（外部仓 CI 校验：frontmatter + safe name + 复用 `fleetent.skills.audit`）+ `docs/skill-gitops.md`。

## Capabilities

### New Capabilities

- `skill-git-sync`：platform 把外部 git 仓库作为 skill 权威源，定时/webhook 经 fetch + reset --hard 镜像进本地 pool，落地时审计兜底并重算版本，再交既有分发链路下发。

### Modified Capabilities

- `skill-pool-versioning`：pool 由「platform 内部自管 git」转为「外部 git 的本地只读镜像」；version 仍 = pool commit SHA，但 commit 由外部 git 同步而来（非 UI 写入）。
- `skill-admin-api`：skill 内容的写端点在 GitOps 下改为 409（只读）；新增 git 源配置/手动同步/同步状态端点；保留读/绑定/启停/版本/diff。
- `skill-admin-ui`：skills 管理页转只读（无内容编辑入口），新增 git 同步状态展示与手动同步。

## Impact

- **owning package**：`platform.skill_management`（新 `pool_sync.py` / `git_source_store.py` / `skill_git_webhook_api.py`，改 `pool_git.py` / `skill_admin_api.py`）；`server.py`（注册 sweep + webhook router）；`config.py`（SchedulingSettings 加间隔）；`frontend/src/features/skills/`；`scripts/`、`docs/`。
- **public API surface**：`pool_git` 追加 `init_pool_with_remote/fetch_remote/reset_pool_to/list_pool_skills`；`pool_sync` 导出 `sync_external_git/scheduled_sweep/align_pool_to_remote/is_sync_due`；`git_source_store` 导出 `get_config/set_config/record_sync`；`skill_git_webhook_api.router`；HTTP `/admin/skills/git/{webhook,sync,status}`；`skill_admin_api` 内容写端点改 409。
- **owned tables**：新增 `skill_git_source`（管理库，本 change 独占）；不动 `skills`/`agent_skills`（现有 current_version/status/source/audit_verdict 列足够）。
- **config namespace**：`scheduling.skill_git_sync_interval_seconds`（默认 300）；运营配置在 DB `skill_git_source`；凭证在 `agent_secrets`（env 名引用）。
- **cross-module dependencies**：`pool_sync → pool_git / skills.audit / skill_admin_store / skills.registry(materialize_builtin_skills, _resolve_skills_dir) / secret_store / git_source_store / webhook_router.verify_signature`；`server → pool_sync`。**agent runtime / node 零改动、零 git 依赖**；下游分发（node_desired_state_api / materialize / skill_deployer）不改。
- **migration / shim plan**：仅新增 Alembic `115_add_skill_git_source`（守卫式 create_table，照 101/103 风格）；无 shim；回滚 drop_table。旧 pool 首次启用经 `bootstrap_skill_git.py` 推到外部仓。
