## Why

skill GitOps 入站（`skill-gitops-inbound`）与出站（`skill-backflow-git-pr`）已实现并归档，但都假设「外部仓库根就是 skill 目录」——pool 这**一个目录**同时是 git 仓根（`.git` 在此、fetch/reset 在此）**和** skill 扫描根（`registry.scan` 找 `<name>/SKILL.md`），两者都由 `skill_registry._resolve_skills_dir(None)` 解析。

但真实要接入的权威源 `bitbucket.org/antalphadev/ai-skills-library` 是个 **monorepo**：skill 在 `skills/<name>/` 子目录下，同级还有 `claude/ codex/ hermes/ …` 等非 skill 目录。若直接把仓库根配成外部源，`reset --hard` 会把整仓镜像进 pool，扫描器把 `claude/ codex/` 也当成 skill、`list_pool_skills` 也把它们列成 skill —— **skill 列表脏**。

本 change 让 fleetent 能把外部仓的某个**子目录**（如 `skills/`）当作 skill 扫描根，从而直接用 ai-skills-library 真实 `main` 当权威源，不必维护「skills 摊在仓库根」的重构分支或引入宿主 git 的 sparse-checkout。

## What Changes

- **新迁移 117**：`skill_git_source` 加列 `skills_subdir`（nullable TEXT，NULL = skill 在仓库根 = 现状）；顺带把 `auto_open_pr` 的默认值从 115 的 `1` 翻成 `0`（对齐「PR 一律人工」，115 已发布不可改列定义本身，用 `alter_column(server_default=...)` + 守卫式 `UPDATE` 收敛存量行）。
- **`git_source_store`**：`_CONFIG_COLUMNS`/`_ALL_COLUMNS` 加 `skills_subdir`，`set_config`/`get_config` 透传。
- **`pool_git.py`**（B 类变换：git 路径前缀）：新增私有 `_skill_tree_path(subdir, name)`（空 subdir 原样返回 `name`）；`pool_version_for_skill` / `pool_skill_history` / `pool_diff_for_commit` / `pool_content_at` / `pool_bundle_at` / `commit_pool`（含 `_stage_paths`）加 `subdir: str = ""` 形参，内部按树路径寻址/暂存/删除。仓根级函数（`init_pool` / `init_pool_with_remote` / `fetch_remote` / `reset_pool_to` / `_lock_path`）不变。`list_pool_skills` / `backfill_current_versions` 保持接口不变，改由调用方传扫描根。
- **`pool_sync.py`**（A 类变换：根切换）：新增 `_git_root()` / `_scan_root(config)`（从 `config["skills_subdir"]` 派生）；`_do_sync` / `_reconcile_catalog_after_sync` / `align_pool_to_remote` 中 fetch/reset 走 git 根，`list_pool_skills` / 审计 / `materialize_builtin_skills` 走扫描根，`pool_version_for_skill` / `pool_content_at` 传 `subdir`。
- **`node_desired_state_api.py`**：拆分 git 根 vs 扫描根；node manifest 的 skill 名/tar 成员名保持干净（不带 `skills/` 前缀，node/agent 契约不变）。
- **`materialize.py` `_copy_skills`**：`src` 继续用 `_resolve_skills_dir(None)`（= 扫描根，天然只拷真 skill）；`pool_version_for_skill` 调用改传 git 根 + `subdir`（否则在扫描根开 `Repo` 会因缺 `.git` 而失败）。
- **`skill_admin_api.py` / `backflow_api.py` / `backflow_store.get_proposal_diff`**：各自的 pool 解析拆成 git 根 vs 扫描根；bundle/内容/FS 操作用扫描根，`pool_version_for_skill` / 历史 / diff 传 `subdir`。
- **出站 `backflow_pr_sweep._back_up` / `backflow_api._fork_via_pr`**：`push_branch(subdir=...)` 前缀改为 `<skills_subdir>/<name>`，使人工合并到 main 后 skill 落在仓库的正确子目录下；空 `skills_subdir` 时保持 `subdir==name`，现有断言不破。

`skills_subdir` 为空/NULL 时，以上所有改动 SHALL 逐字节等同现状（完全向后兼容），现有 e2e/单测（repo-root 布局）作为回归基线。

## Capabilities

### Modified Capabilities

- `skill-git-sync`：支持把外部仓库的某个子目录配置为 skill 扫描根（`skills_subdir`），git 仓根仍整仓镜像（dulwich fetch + reset --hard 不变），非 skill 目录不进入 catalog。
- `skill-pool-versioning`：「池可作为外部 git 的本地镜像」场景下，per-skill 版本解析（子树最后 commit）需按 `skills_subdir` 前缀定位子树，而非直接以 skill 名为树路径。
- `skill-backflow`：备份分支 / fork 分支推送的树路径按 `skills_subdir` 加前缀，使这些分支的内容布局与权威仓库一致，人工合并到 main 后 skill 落在正确子目录。

## Impact

- **owning package**：改动集中在 `platform.skill_management`（`pool_git.py` / `pool_sync.py` / `git_source_store.py` / `backflow_api.py` / `backflow_pr_sweep.py` / `backflow_store.py`）+ `platform.node_management`（`node_desired_state_api.py`）+ `platform.agent_lifecycle`（`materialize.py`）。新增 Alembic `117`。
- **public API surface**：`pool_git.py` 的 `pool_version_for_skill` / `pool_skill_history` / `pool_diff_for_commit` / `pool_content_at` / `pool_bundle_at` / `commit_pool` 新增可选形参 `subdir: str = ""`（向后兼容，不改变现有调用点行为）；`backflow_store.get_proposal_diff` 同样新增 `subdir: str = ""`；无新增/删除 HTTP 端点。
- **owned tables**：`skill_git_source`（`platform.skill_management` 独占）仅加 nullable 列 `skills_subdir`；无新表。
- **config namespace**：复用 DB `skill_git_source`，无新增 config namespace。
- **cross-module dependencies**：不变；`node_desired_state_api` 仍只读 `pool_version_for_skill`（新增 subdir 实参，无新依赖方向）；`node` / agent runtime 零改动、零 git 依赖。
- **migration / shim plan**：仅新增 Alembic `117_add_skill_git_source_skills_subdir`（`down_revision="116"`，当前 head；116 只动 `backflow_proposals` 表，未碰 `skill_git_source`；守卫式 `add_column` + `auto_open_pr` server_default 翻转）；无 shim；`skills_subdir` 默认 NULL，等价于「skill 在仓库根」的现状语义。
