## 1. 迁移 117：`skill_git_source.skills_subdir` + `auto_open_pr` 默认翻 0

- [x] 1.1 (test) integration `tests/integration/test_migration_117_skills_subdir.py`：升级到 `117` 后 `skill_git_source` 含 `skills_subdir`（nullable TEXT），存量行为 NULL、可写读；存量 `auto_open_pr=1` 的行升级后被收敛为 `0`（feature 未上线，安全）；新 INSERT 不显式给 `auto_open_pr` 时默认落 `0`；重复升级到 `117` 幂等（不报错、不重复执行 UPDATE）；`downgrade` 能把 `skills_subdir` 列 drop 掉 → 见红
- [x] 1.2 (impl) `migrations/versions/117_add_skill_git_source_skills_subdir.py`：`revision="117"`，`down_revision="116"`（当前 head，116 未碰 `skill_git_source` 表）；照 116 的 `_has_table`/`_has_column` 守卫式风格：`add_column("skill_git_source", "skills_subdir", sa.Text(), nullable=True)`；`batch_alter_table("skill_git_source")` 内 `alter_column("auto_open_pr", server_default="0")`；守卫式 `op.execute("UPDATE skill_git_source SET auto_open_pr = 0 WHERE auto_open_pr = 1")`（docstring 注明：feature 未上线，翻转历史行是安全的，不影响任何在跑的 PR 自动化）；`downgrade` drop `skills_subdir` 列（`auto_open_pr` 的历史翻转不做反向回填，docstring 注明原因） → 见绿

## 2. `git_source_store` 加列

- [x] 2.1 (test) 追加 `tests/integration/test_git_source_store.py`：`set_config(skills_subdir="skills")` 后 `get_config()["skills_subdir"] == "skills"`；未设置时为 `None`；`set_config` 仍拒绝不在 `_CONFIG_COLUMNS` 内的未知字段（现有断言回归） → 见红
- [x] 2.2 (impl) `git_source_store.py`：`_CONFIG_COLUMNS` 加 `"skills_subdir"`；`_ALL_COLUMNS`（SELECT 列清单）同步加入，位置紧跟 `branch_prefix`之后即可，`get_config`/`set_config`/`record_sync` 无需其它改动（沿用现有通用 upsert 逻辑） → 见绿

## 3. `pool_git.py`：`_skill_tree_path` + `resolve_git_root`（R1 唯一实现）+ (B) 类函数 + `_stage_paths`（R3，最吃重）

- [x] 3.1 (test) 追加 `tests/integration/test_pool_git.py`（或新文件 `tests/integration/test_pool_git_subdir.py`，与现有 `test_pool_git_skill_version.py` 风格一致，真实临时 dulwich 仓）：
  - `_skill_tree_path("skills", "foo") == "skills/foo"`；`_skill_tree_path("", "foo") == "foo"`
  - `resolve_git_root(scan_dir, "skills")`：当 `scan_dir` 以 `.../skills` 结尾时返回去掉该后缀的父目录；`resolve_git_root(scan_dir, "")` 原样返回 `scan_dir`；当 `scan_dir` **不**以 `/<subdir>` 结尾时记一条 warning 日志（用 `caplog` 断言）并回退返回 `scan_dir` 本身（R1 显式断言点）
  - 造 `<repo>/skills/foo/SKILL.md` + 诱饵 `<repo>/claude/bar/SKILL.md` 并各自 commit：`pool_version_for_skill(repo, "foo", subdir="skills")` 命中非 None 的 sha；`list_pool_skills(repo/"skills")` 只返回 `["foo"]`（不含从 `repo` 根扫描会带出的 `claude`）
  - `commit_pool(repo, message=..., author=..., skill_name="foo", subdir="skills")` 改动 `skills/foo` 下文件（新增/修改/删除各一种）后，新 commit 只暂存 `skills/foo/**` 的变更，`claude/bar/**` 不受影响（覆盖 R3 的 `_stage_paths`）
  - `pool_skill_history` / `pool_diff_for_commit` / `pool_content_at` / `pool_bundle_at` 传 `subdir="skills"` 后只作用于 `skills/foo` 子树，返回内容与树路径为 `skills/foo` 时一致
  - 以上所有函数 `subdir=""`（默认值）时的行为与本 task 之前逐字节一致（回归用例，复用现有测试断言）
  → 见红
- [x] 3.2 (impl) `pool_git.py`：
  - 新增 `_skill_tree_path(subdir: str, name: str) -> str`（空 `subdir` 原样返回 `name`，否则 `f"{subdir}/{name}"`）
  - 新增公开 `resolve_git_root(scan_dir: Path, subdir: str) -> Path`：空 `subdir` 原样返回 `scan_dir`；非空时校验 `scan_dir` 的最后一段路径等于 `subdir`（支持多级 subdir 如 `"a/b"`），满足则返回剥离该后缀的父目录，不满足则 `logger.warning(...)` 并回退返回 `scan_dir`（这是 R1 「设错告警 + 回退」的唯一实现，后续模块全部复用它，不重复实现）
  - 给 `pool_version_for_skill` / `pool_skill_history` / `pool_diff_for_commit` / `pool_content_at` / `pool_bundle_at` / `commit_pool`（含 `_stage_paths`）加 `subdir: str = ""` 关键字参数，内部把原来直接用 `skill_name` 构造 git 树路径 / dulwich `paths=[...]` 过滤 / `changed_files` 前缀过滤的地方，统一替换成 `_skill_tree_path(subdir, skill_name)`
  - `list_pool_skills` / `backfill_current_versions` 签名不变；读现有实现确认 `backfill_current_versions` 内部是否调用了 `pool_version_for_skill`——若调用，改造该内部调用以支持从调用方传入 `subdir`（该函数当前签名不接受 subdir，若确有需要则一并加 `subdir: str = ""` 形参；若发现该函数当前从未在外部 git 源场景下被调用，则维持现状并在 PR 描述里注明）
  → 见绿

## 4. `pool_sync.py`：`_git_root` 串联 + 旗舰 e2e（验证 R1 集成正确性）

- [x] 4.1 (test) 追加 `tests/unit/test_pool_sync.py`：mock `git_source_store.get_config()` 返回含 `skills_subdir="skills"` 的 config；断言 `_do_sync` 把 `pool_git.resolve_git_root(...)` 计算出的 git 根传给 `fetch_remote` / `reset_pool_to` / `init_pool_with_remote`，把扫描根（`_pool_dir()`）传给 `list_pool_skills` / 审计 / `materialize_builtin_skills` 相关调用，把 `subdir="skills"` 传给 `pool_version_for_skill` / `pool_content_at`；另起一例 `skills_subdir=None`（或未配置）时上述全部退化为「git 根==扫描根、`subdir=""`」，与本 task 之前的既有测试断言完全一致（回归） → 见红
- [x] 4.2 (impl) `pool_sync.py`：新增 `_git_root(config: dict[str, Any]) -> Path`（内部 `pool_git.resolve_git_root(_pool_dir(), config.get("skills_subdir") or "")`）；`_do_sync` 里 `init_pool_with_remote` / `fetch_remote` / `reset_pool_to` 调用改传 `_git_root(config)`；`_reconcile_catalog_after_sync`（含 `list_pool_skills`、审计、内置 seed 相关文件系统操作）继续传扫描根 `_pool_dir()`，但其中调用 `pool_version_for_skill` 的地方改传 `_git_root(config)` + `subdir=config.get("skills_subdir") or ""`；`align_pool_to_remote` 同样按 fetch/reset 走 git 根改造 → 见绿
- [x] 4.3 (test) 旗舰集成 `tests/integration/test_pool_sync_subdir_e2e.py`：本地临时目录建一个源 git 仓，造 `skills/clean/SKILL.md`（正常内容）+ `skills/evil/SKILL.md`（内容触发现有 severe 审计规则）+ 诱饵 `claude/foo/SKILL.md`；`monkeypatch.setenv("FLEETENT_SKILLS_DIR", f"{home}/ai-skills-library/skills")`；`git_source_store.set_config(remote_url=<源仓 file:// 路径>, branch="main", skills_subdir="skills", provider="bitbucket", auto_open_pr=0, enabled=1)`；调 `pool_sync.sync_external_git(trigger="manual")`；断言：catalog 只含 `clean`（active，`current_version` 非空）与 `evil`（quarantined，`current_version` 为空），**不含** `foo`；`<home>/ai-skills-library/` 目录下仍能看到 `.git` 与 `claude/`（git 根整仓镜像未收窄）；`pool_git.pool_version_for_skill(<git根>, "clean", subdir="skills")` 等于 catalog 里 `clean` 的 `current_version`；对同一 commit 二次调用 `sync_external_git` 短路（不产生新 commit、不重复跑审计）。既有 repo-root 布局的旗舰 e2e（`test_pool_sync_e2e.py`，`skills_subdir` 未配置）作为回归基线，保持不动且仍绿 → 见红（依赖 4.2 尚未实现的行为）→ 4.2 完成后见绿

## 5. `node_desired_state_api.py` 拆根（R5：node manifest 名称保持干净）

- [x] 5.1 (test) 追加 `tests/integration/test_node_desired_state_api.py`：配置 `skills_subdir="skills"` 场景下，触发 `_skill_manifests_for` 路径（node 状态上报/desired-state 查询）返回的 skill manifest 中版本字段与 `pool_git.pool_version_for_skill(<git根>, name, subdir="skills")` 一致；manifest 里的 skill 名 / `bundle_url` / 任何路径片段都不含 `skills/` 前缀（R5，断言响应体与既有「零 git 依赖」源码守卫测试都仍成立） → 见红
- [x] 5.2 (impl) `node_desired_state_api.py`：新增 `_git_root()`（读 `git_source_store.get_config()`，调用 `pool_git.resolve_git_root(_skill_pool_dir(), config.get("skills_subdir") or "")`）；`_skill_manifests_for` 里原 `pool_version_for_skill(pool_dir, skill_name)` 调用改为 `pool_version_for_skill(_git_root(), skill_name, subdir=config.get("skills_subdir") or "")`；`_skill_pool_dir()`（扫描根）及其余调用点（`bundle_cache.ensure_bundle_cached` / `skill_directory_version` / `backflow_store.nominate_if_absent`）保持传扫描根不变 → 见绿

## 6. `materialize.py` `_copy_skills`（R2/R4：与 node 投影的 sha 一致）

- [x] 6.1 (test) 追加 `tests/integration/test_materialize_base_version.py`：`skills_subdir="skills"` 场景下，`_copy_skills` 仍只把扫描根下的真实 skill 拷进 agent home（不拷 `.git` / `claude/` 等杂目录，R4 回归）；写入 `skill_admin_store` 的 `base_commit` 等于 `pool_git.pool_version_for_skill(<git根>, name, subdir="skills")`，且与 task 5 中 node 投影产出的 sha **完全一致**（R2 交叉校验：同一次同步，两处必须给出相同版本标识） → 见红
- [x] 6.2 (impl) `materialize.py` `_copy_skills`：`src = _resolve_skills_dir(None)`（扫描根）不变；原 `pool_version_for_skill(src, skill_dir.name)` 调用改为先取 `skills_subdir = git_source_store.get_config().get("skills_subdir") or ""`（无配置/表不存在时按 best-effort 回退为 `""`），`git_root = pool_git.resolve_git_root(src, skills_subdir)`，再调 `pool_version_for_skill(git_root, skill_dir.name, subdir=skills_subdir)` → 见绿

## 7. `skill_admin_api.py` + `backflow_api.py` + `backflow_store.get_proposal_diff` 拆根/串 subdir

- [x] 7.1 (test) 追加 `tests/integration/test_skill_admin_api.py` 与 `tests/unit/test_backflow_api_pr.py`：`skills_subdir="skills"` 场景下，`GET /admin/skills/{name}/versions`、`GET /admin/skills/{name}/versions/{ref}/diff` 与回流提案 diff 端点均正常返回（不因 `_pool_dir()` 在「扫描根本身没有 `.git`」时误判为非 git 仓而返回错误/空列表）；`backflow_store.get_proposal_diff(..., subdir="skills")` 能正确从 `pool_bundle_at` 重建 base 内容 → 见红
- [x] 7.2 (impl)：
  - `skill_admin_api.py`：`_pool_dir()` 改为先算 `scan_dir = Path(engine_skills_dir())`、`skills_subdir = git_source_store.get_config()` 里的值（表不存在/未配置按 `""` 处理）、`git_root = pool_git.resolve_git_root(scan_dir, skills_subdir)`，再校验 `git_root`（而非 `scan_dir`）是否为 git 仓；`skill_versions` / `skill_version_diff` 调 `pool_skill_history` / `pool_diff_for_commit` 时传 `subdir=skills_subdir`
  - `backflow_api.py`：`_pool_dir()` 同样拆根；已实现的 PR 治理路径（`_fork_via_pr` 里 `pool_version_for_skill` 调用）与合并后取新版本的调用传 `subdir`；`_accept_legacy` / `_fork_legacy`（未配置外部源场景，`skills_subdir` 恒为空）不受影响
  - `backflow_store.get_proposal_diff`：加 `subdir: str = ""` 关键字参数，内部 `pool_bundle_at(pool_dir, skill_name, base_commit, subdir=subdir)` 透传；调用方（`backflow_api`）传 `git_root` + `skills_subdir`
  → 见绿

## 8. 出站 `backflow_pr_sweep` + `backflow_api._fork_via_pr` push 路径加 subdir 前缀

- [x] 8.1 (test) 追加 `tests/unit/test_backflow_pr_sweep.py` 与 `tests/unit/test_backflow_api_pr.py`：`config["skills_subdir"]="skills"` 时，`FakeGitPlatformBackend.push_branch` 收到的 `subdir` 实参为 `"skills/crm-ops"`（备份分支场景）/ `"skills/<fork_name>"`（fork 场景）；`skills_subdir` 为空或未配置时保持现有断言 `subdir=="crm-ops"` / `subdir=="<fork_name>"` 不破 → 见红
- [x] 8.2 (impl)：`backflow_pr_sweep._back_up` 与 `backflow_api._fork_via_pr` 里 `push_branch(subdir=...)` 的实参从直接传 `skill_name`/`fork_name`，改为 `pool_git._skill_tree_path(config.get("skills_subdir") or "", skill_name)` / `..._skill_tree_path(..., fork_name)`（直接复用 task 3 实现的 `_skill_tree_path`，不在两处各自重新实现同一条空 subdir 判断规则） → 见绿

## 9. Spec 同步与质量门

- [x] 9.1 spec 手工同步（openspec CLI 本机不可用）：把本 change `specs/skill-git-sync/spec.md`（ADDED）、`specs/skill-pool-versioning/spec.md`（MODIFIED）、`specs/skill-backflow/spec.md`（MODIFIED）的 delta 合入对应主 spec `openspec/specs/{skill-git-sync,skill-pool-versioning,skill-backflow}/spec.md`：ADDED 追加到 `## Requirements` 下，MODIFIED 整段替换同名 Requirement
- [x] 9.2 模块边界与护栏：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` exit 0；`test_nominate_and_node_ingestion_path_are_git_free` 仍绿（node/agent 零 git）；`tests/unit/test_module_dependency_guardrails.py` 仍绿
- [x] 9.3 收尾门禁：`make test-pr` + `make test-integration-ci` + `make test-frontend` 全绿（本 change 不改前端代码，跑 `make test-frontend` 只为确认无意外破坏）；`uv run mypy src`（至少覆盖本次改动的 8 个模块）通过；repo-root 布局（`skills_subdir` 未配置）的既有 e2e/单测作为回归基线，保持绿
