## 1. 数据层：迁移 + store（测试先行）

- [x] 1.1 (test) integration `tests/integration/test_migration_115_skill_git_source.py`：apply 到 115 后表 `skill_git_source` 存在、列齐、可 upsert/record_sync（参考既有 test_migration_*）→ 见红
- [x] 1.2 (impl) `migrations/versions/115_add_skill_git_source.py`：守卫式 `create_table`（照 101/103 的 `_has_table` 风格），`down_revision="112"`；downgrade `drop_table` → 见绿
- [x] 1.3 (test) integration `tests/integration/test_git_source_store.py`：get_config 缺省/ set_config upsert 幂等 / record_sync 只更新状态三列 / 未知字段拒绝 → 见红
- [x] 1.4 (impl) `src/fleetent/platform/skill_management/git_source_store.py`：手写 SQL + named params，走 `db.py`；**不在此建表** → 见绿

## 2. pool_git remote 原语

- [x] 2.1 (test) integration `tests/integration/test_pool_git_remote_sync.py`：建两个临时 dulwich repo（源/pool），`fetch_remote` 返回远端 sha、`reset_pool_to` 落工作树=源 HEAD、增量再 fetch、`list_pool_skills` 列目录、分支不存在抛 `ValueError` → 见红
- [x] 2.2 (impl) `pool_git.py` 追加 `init_pool_with_remote` / `fetch_remote` / `reset_pool_to` / `list_pool_skills`（`porcelain.fetch(..., username, password)` + `porcelain.reset(.., "hard", sha)`，持现有 `_FileLock`），更新模块 docstring（不再 local-only） → 见绿

## 3. pool_sync 同步服务

- [x] 3.1 (test) unit `tests/unit/test_pool_sync.py`：`is_sync_due` 边界（last=None / 超期 / 未超 / disabled / interval=None / 边界） → 见红
- [x] 3.2 (test) unit 同文件：`sync_external_git` 舱壁化（mock fetch raise → `record_sync(error)` 且不抛）；审计兜底（severe→`set_status("quarantined")` 且**未**调 set_current_version；clean→set_current_version 一次）；外删→`set_status("archived")`；远端 sha 未变→短路不 reset → 见红
- [x] 3.3 (impl) `src/fleetent/platform/skill_management/pool_sync.py`：`sync_external_git` / `scheduled_sweep` / `is_sync_due` / `align_pool_to_remote` / `_reconcile_catalog_after_sync`，复用 `skills.audit` / `skill_admin_store` / `skills.registry.materialize_builtin_skills` / `secret_store` / `git_source_store` / `pool_git` → 见绿
- [x] 3.4 (test) integration `tests/integration/test_pool_sync_e2e.py`：真实 dulwich+SQLite——源放 1 clean + 1 severe 注入 skill → 同步后 clean=active+有 current_version、注入=quarantined+无 version、`last_synced_commit` 正确、二次同步短路、内置 skill reset 后仍在

## 4. 触发：scheduler job + webhook

- [x] 4.1 (test) unit `tests/unit/test_skill_git_webhook.py`：webhook_decision 404/403/401/200（未配 secret→403）+ _status_payload 凭证脱敏 → 见红
- [x] 4.2 (impl) `src/fleetent/platform/skill_management/skill_git_webhook_api.py`：`POST /webhook`(复用 `webhook_router.verify_signature` + `secret_store`) + `POST /sync`(复用 `_require_admin`) + `GET /status` → 见绿
- [x] 4.3 (impl) `config.py` `SchedulingSettings` 加 `skill_git_sync_interval_seconds: int = 300`；`server.py` `_build_platform_maintenance_scheduler` 注册 `__skill_git_sync_sweep__` interval job + `include_router(skill_git_webhook_api.router)`
- [x] 4.4 (test) integration `tests/integration/test_skill_git_scheduler.py`：注入 `_scheduler` 断言 `__skill_git_sync_sweep__` job 已注册 + config 字段默认

## 5. UI 只读化

- [x] 5.1 (test) integration `tests/integration/test_skill_admin_gitops_readonly.py`：GitOps 启用时 `delete`/`restore`/`force-publish` → 409，`list` → 200，未启用不拦 → 见红
- [x] 5.2 (impl) `skill_admin_api.py`：`_reject_if_gitops` gate，6 写端点（create/edit/upload/archive/restore/force-publish）GitOps 启用返 409，保留读/绑定/启停/reload → 见绿
- [x] 5.3 (test) 前端 `frontend/src/features/skills/page.test.tsx`：无 create/edit/archive mutation、只读 Banner 渲染、git 同步状态卡片渲染、viewer 无写按钮 → 见红
- [x] 5.4 (impl) 前端 `api.ts`/`page.tsx`/`messages.ts`：移除写 mutation/入口 + 「权威源在 git」Banner + git 同步状态卡片 + `useSkillGitStatusQuery`/`useTriggerSkillGitSyncMutation` → 见绿

## 6. 运维脚本 + 文档

- [x] 6.1 (test) unit `tests/unit/test_validate_skills.py`：对 fixture skill 目录判定（frontmatter 缺失 fail / severe 注入 fail / clean pass / unsafe name fail） → 见红
- [x] 6.2 (impl) `scripts/validate_skills.py`：frontmatter + `_safe_skill_name` 语义 + 复用 `fleetent.skills.audit`（设计为可 vendoring），非零退出阻断合并 → 见绿
- [x] 6.3 (impl) `scripts/bootstrap_skill_git.py`：现有 pool 推到外部空仓（非空拒绝），`set_config(enabled=1)`；push auth 待真实 remote 手动验证
- [x] 6.4 (impl) `docs/skill-gitops.md` + `bitbucket-pipelines.yml` 模板片段（已起草，待人工确认后 commit）

## 7. Spec 同步与质量门

- [x] 7.1 spec 手工同步（openspec CLI 本机不可用）：新增 `specs/skill-git-sync/spec.md`；MODIFY `skill-pool-versioning` / `skill-admin-api` / `skill-admin-ui`
- [x] 7.2 模块边界：`check_module_boundaries.py` 通过（exit 0）；plane boundary guardrail 绿（pool_sync/webhook 经注入解耦，不 import agent_lifecycle）；agent 侧零 git 依赖
- [x] 7.3 收尾门禁：`make test-pr`（4006 passed）+ `make test-integration-ci`（2078 passed）全绿；mypy 改动模块通过；行长 100
