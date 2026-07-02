# Design — skill-gitops-inbound

## 设计概述（入站数据流）

外部 git 仓库 = skill 权威源。platform 进程内的 `pool_sync` 定时（platform maintenance scheduler）或经 webhook 触发，用 dulwich `porcelain.fetch`（basic auth）抓外部仓主分支进本地 pool，再 `porcelain.reset --hard <fetched_sha>` 让工作树与远端 commit 完全一致（mirror 语义：外部权威、本地只镜像，避免合并冲突）。落地后逐 skill 跑入站审计兜底 + 重算 current_version，再交**既有分发链路**（bundle manifest + node reconcile，零改动）下发 agent。UI 转只读。

```
外部 git repo (main = 权威)
   │ fetch + reset --hard（pool_sync：定时 sweep / webhook）
   ▼
本地 pool（git 只读镜像） ── 审计兜底(severe→quarantine) + 重算 current_version + 内置 seed 恢复
   │ 既有 _skill_manifests_for（commit SHA + bundle 哈希，零改动）
   ▼
node reconcile（零改动）→ agent home/skills → 注入 prompt
```

## 关键技术决策

1. **fetch + reset，而非 pull/clone**：已验证 dulwich 1.2.6 `porcelain.fetch` 接受 `username/password`，但 `porcelain.pull/clone` 封装不接受 → 入站统一 `fetch`（拿远端 sha）+ `reset --hard`（落工作树）。reset 语义天然实现「外部权威、本地镜像」，无三方合并。
2. **审计兜底（quarantine）**：reset 后逐 skill 复用 `skills/audit.py`（与 agent 加载审计同一套规则）；`has_severe` → `set_status("quarantined")` 且**不**更新 current_version（隔离、不进分发）；clean → active + `set_current_version`；外部删除的 skill → `set_status("archived")` 软删（保绑定）。
3. **reset 清内置 seed 的恢复**：外部仓通常不含内置 skill，`reset --hard` 会删掉它们 → reset 后必 `materialize_builtin_skills()` 恢复并 `commit_pool`，否则内置 skill 从分发消失（e2e 覆盖）。
4. **触发**：`_build_platform_maintenance_scheduler`（现为空壳）首次注册 interval job；webhook 仅 HMAC 鉴权（复用 `webhook_router.verify_signature`，constant-time），强制配 secret 否则拒收，payload 不被信任（只触发 fetch，内容以 fetch 为准）。
5. **舱壁化**：`sync_external_git` 最外层 try/except，失败写 `last_sync_error` 绝不抛（不崩 cron/webhook/boot）；boot 不接外部网络（remote 延迟到首次 sweep）；fetch 只写 object store 不动工作树，reset 失败工作树仍是旧版本（安全），下次重试。
6. **凭证**：git 源运营配置在 DB `skill_git_source`；凭证值走 `agent_secrets`（shared scope，env 名引用），不入库明文、不进 yaml/git。

## 与现状 / 在途 change 的衔接

- 现状（origin/main 已核实）：pool 是 platform 内部 dulwich git（`pool_git.py` 无 remote）；`create_skill` 已落盘（`skill-create-persist-content` 已实现）；node 分发仍是 bundle_url（`node-skill-sync-cleanup` 仅 proposal）。
- `skill-create-persist-content`：其 inline create 落盘入口被本 change 只读化（409）**有意取代**——GitOps 下内容只从 git 来。
- `node-skill-sync-cleanup`（在途）：未来或把下游分发由 bundle 改 desired-state 内嵌；与本 change **正交**——version=commit SHA 解耦，入站只保证「pool 内容正确 + current_version 更新」，下游怎么读 pool 不影响。
- 出站回流（`skill-backflow-git-pr`，后续 change）：复用本 change 的 `align_pool_to_remote`（合并 PR 后对齐 pool）+ `git_source_store` 配置。

## 模块边界

见 proposal.md「Impact」。要点：改动只在 platform 侧 + config + 前端 + scripts；**agent runtime / node 零改动、零 git 依赖**；新表 `skill_git_source` 经 Alembic 115；凭证走 agent_secrets。`scripts/check_module_boundaries.py` 须仍通过。

## 测试策略

- **unit**（mock）：`is_sync_due` 边界；`sync_external_git` 舱壁化 + 审计兜底 + 外删 archived + sha 未变短路；webhook 签名/重入/手动/状态脱敏；写端点 409 / 读端点保留；前端无写入口 + 只读 Banner + git 状态卡片。
- **integration**（真实 dulwich + SQLite + Alembic）：`fetch_remote`/`reset_pool_to`/`list_pool_skills` 双 repo 往返；`sync_external_git` e2e（clean / severe / 内置恢复 / 短路 / last_synced_commit）；迁移 115 建表；`git_source_store` upsert/record_sync。
- **回归**：`node/test_skill_deployer.py` resync 路径不变（确认 manifest 未动）。
