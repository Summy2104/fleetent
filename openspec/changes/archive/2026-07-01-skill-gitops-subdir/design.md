# Design — skill-gitops-subdir

## 设计概述

现状：pool 目录**同时**是 git 仓根（`.git` 在此，dulwich fetch/reset 在此操作）和 skill 扫描根（`registry.scan` / `list_pool_skills` 在此找 `<name>/SKILL.md`），两者都由 `skill_registry._resolve_skills_dir(None)`（= `FLEETENT_SKILLS_DIR`）解析成同一个目录。

本 change 让这两个角色可以**分离**：git 仓根继续整仓镜像（保持纯 dulwich、不引入宿主 git 的 sparse-checkout），扫描根则可以是仓根下的一个子目录（`skills_subdir`，如 `"skills"`）。最终落盘：

```
<FLEETENT_HOME>/ai-skills-library/     ← git 仓根（.git 在此，镜像整仓）
├── .git/            origin = ai-skills-library.git
├── claude/ codex/ … 杂目录（镜像带着，占磁盘，fleetent 不扫）
└── skills/          ← 扫描根：fleetent 只从这里读 skill
    ├── aa-cmp-wallet-risk/SKILL.md …
```

`skills_subdir` 为空/NULL 时，扫描根 = git 仓根，逐字节等同现状。

## 核心不变量（R1，最关键，实现时必须守住）

- `_resolve_skills_dir(None)`（即环境变量 `FLEETENT_SKILLS_DIR`）**永远是扫描根**（agent 运行时 / registry 也用它）。
- 配 `skills_subdir=skills` 时：`FLEETENT_SKILLS_DIR` 设成 `<home>/ai-skills-library/skills`；**git 仓根 = 扫描根去掉末尾 `skills_subdir` = `<home>/ai-skills-library/`**。
- 平台侧各 resolver 由扫描根反推 git 仓根（去掉 subdir 后缀）；若扫描根不以 `skills_subdir` 结尾 → 记告警并回退当 git 根用。
- 设错的后果：`reset --hard` 会 reset 错目录，或扫描器扫整仓。需加显式断言 + 告警。

## 两类变换

- **(A) 根切换**：所有「解析 skill 目录」的地方返回 `git根/<subdir>`（扫描根）。多数调用是 `dir / skill_name` 的文件系统路径，resolver 返回扫描根即可自然生效（`pool_sync` 的 `list_pool_skills` / 审计 / `materialize_builtin_skills`；`materialize._copy_skills` 的 `src`）。
- **(B) git 路径前缀**：`pool_git.py` 里「skill 名 → git 树路径」的函数，git 路径要用 `<subdir>/<name>`，对外仍暴露干净的 `<name>`。新增私有 `_skill_tree_path(subdir, name)`（空 subdir → 原样返回 name），给这些函数加 `subdir: str = ""`（默认空 = 逐字节等同现状）：`pool_version_for_skill` / `pool_skill_history` / `pool_diff_for_commit` / `pool_content_at` / `pool_bundle_at` / `commit_pool`（含 `_stage_paths`）。git 仓根级函数（`init_pool` / `init_pool_with_remote` / `fetch_remote` / `reset_pool_to` / `_lock_path`）不变——它们操作的是整个仓库，与 subdir 无关。

## 关键技术决策

1. **保持纯 dulwich 全量镜像，不用宿主 git 的 sparse-checkout**：`skills_subdir` 只影响「fleetent 从哪里扫描/寻址」，不影响「镜像了多少内容」——git 仓根永远是整仓。这样不引入宿主 git 二进制依赖，也不需要处理 sparse-checkout 与 dulwich reset 语义的冲突。
2. **`git_source_store` 是把 `skills_subdir` 送达所有消费方的现成载体**：`skill_git_source` 表的 config dict 已经是 `pool_sync` / `backflow_*` / `node_desired_state_api` / `skill_admin_api` 共同读取的配置来源，加一列即可让下游按需派生 `_git_root()` / `_scan_root()`，不需要新增配置通道。
3. **git 根/扫描根的换算下沉为一个纯函数，四处调用点复用**：在 `pool_git.py` 新增 `resolve_git_root(scan_dir: Path, subdir: str) -> Path`（纯函数，不读 DB/配置）——`subdir` 为空原样返回 `scan_dir`；非空则要求 `scan_dir` 以 `/<subdir>` 结尾，剥离后缀得到 git 根，**不满足则记告警并回退把 `scan_dir` 当 git 根用**（R1 的显式断言点，只实现一次）。`pool_sync._git_root()` 从 `git_source_store` 配置里取 `skills_subdir`，调用该纯函数；`node_desired_state_api` / `skill_admin_api` / `backflow_api` / `materialize` 各自的 pool 解析函数同样各自读配置得到 `subdir`，再调用同一个 `pool_git.resolve_git_root`——这四个模块已经因为 (B) 类函数需要 `subdir` 形参而依赖 `pool_git`，复用其纯函数不引入新的跨包依赖。禁止任何调用点自行用字符串拼接/裁剪来推导 git 根。
4. **`commit_pool`/`_stage_paths` 按树路径暂存与删除（R3）**：FS 写入落在扫描根（`<git根>/<subdir>/<name>/...`），但 commit 走 git 根开 `Repo`，暂存路径与「删除时清理前缀」都必须用 `_skill_tree_path(subdir, name)` 算出的树路径，否则暂存范围与实际改动的文件树不对应，可能漏提交或误删其它 skill 的暂存状态。
5. **node manifest / 分发链路的 skill 名保持干净（R5）**：`node_desired_state_api` 面向 node/agent 暴露的 `bundle_url`、tar 成员名不带 `skills_subdir` 前缀——subdir 是 platform 内部管理外部仓库布局的细节，不应该扩散到 node/agent 契约。
6. **`materialize._copy_skills` 的 `src` 天然正确、但 `pool_version_for_skill` 调用点必须显式改（R2/R4）**：`src = _resolve_skills_dir(None)` 本来就是扫描根，天然只拷贝真实 skill、不会把 `.git`/`claude/` 等杂目录拷进 agent 家目录；但同一函数里对 `pool_version_for_skill(src, name)` 的调用如果不改成传「git 根 + subdir」，会在扫描根（无 `.git`）上开 `Repo` 直接失败。
7. **`base_commit` 的 subdir 前缀在两处必须一致（R2）**：`materialize._copy_skills` 记录的 `base_commit` 与 node 侧 `_skill_manifests_for` 投影出的 sha 必须来自同一套「git 根 + subdir」换算，否则两处对同一次同步产出不同的版本标识，造成误报的漂移冲突。

## 已知风险（实现时逐一覆盖）

- **R1（最高）**：git 根 / 扫描根反推。设错 → reset 错目录或扫全仓。加断言 + 告警。
- **R2**：`base_commit` 的 subdir 前缀在 `materialize._copy_skills` 与 node 投影 `_skill_manifests_for` 两处必须一致，否则假冲突。集成测试断言两处产出的 sha 一致。
- **R3**：`commit_pool`/`_stage_paths` 在「FS 写到扫描根、commit 走 git 根」时要按 `git根/subdir/name` 暂存 + 删除前缀走树路径。
- **R4**：`_copy_skills` 的 src 必须是扫描根（不变量下天然成立）；勿误用 git 根，否则把 `.git`/杂目录拷进 agent 家。
- **R5**：node manifest 的 `bundle_url` / tar 成员名保持**干净 skill 名**（不带 `skills/` 前缀）→ node/agent 契约不变、仍零 git。
- **R6**：`pool_diff_for_commit` 的 `changed_files` 会带 `skills/` 前缀（UI 展示串）；若有测试断言精确 `<name>/…` 需更新（低风险）。

## 与现状的衔接

- 现状（已核实）：`pool_git.py` 的 (B) 类函数目前都以 `pool_dir / name` 作为 skill 子树路径，隐含「pool_dir = 扫描根 = git 仓根」的假设；仓根级函数（`init_pool` 等）已经与「skill 名」无关，不需要改动。
- `git_source_store` 的 `_CONFIG_COLUMNS`/`_ALL_COLUMNS` 是唯一需要改的持久化点；`skill_git_source` 表其余列（`branch_prefix`/`auto_open_pr`/凭证 env 名等，115/116 已建）不受影响。
- 出站 `backflow_pr_sweep` / `backflow_api._fork_via_pr` 已经在调用 `push_branch(subdir=<name>)`（当前把 skill 名本身当 subdir 传给 git 平台后端，用于定位备份分支里的树路径）；本 change 把这个已有形参的取值从 `name` 改为 `_skill_tree_path(skills_subdir, name)`，空 `skills_subdir` 时不变。

## 模块边界

见 proposal.md「Impact」。要点：不新增 owning package；改动集中在 `platform.skill_management` + `platform.node_management`（`node_desired_state_api`）+ `platform.agent_lifecycle`（`materialize`）；无新表，仅给 `skill_git_source` 加列（迁移 117）；`pool_git.py` 系列公开函数新增可选 `subdir` 形参，默认值保证向后兼容；node / agent runtime 零改动、零 git 依赖，分发链路（tar 成员名/manifest）用干净 skill 名不变。

## 测试策略

- **unit**：`test_pool_git.py` 新增用例覆盖 `_skill_tree_path` 与 (B) 类函数的 `subdir` 参数（含 `commit_pool`/`_stage_paths` 的暂存/删除前缀，覆盖 R3）；`test_pool_sync.py` 断言 `_do_sync` 把 git 根传给 fetch/reset、扫描根传给 list/materialize、`subdir` 传给版本/内容；`test_backflow_pr_sweep.py` 断言 `skills_subdir` 配置下推送分支的树路径前缀正确。
- **integration**：`test_migration_117_*.py` 断言升级后有 `skills_subdir` 列、旧行 NULL、可写，新插入行 `auto_open_pr==0`，重复升级幂等；旗舰 `test_pool_sync_subdir_e2e.py`——源仓造 `skills/clean` + `skills/evil`（severe）+ 诱饵 `claude/foo`，配置 `skills_subdir="skills"` 后 `sync_external_git()`，断言 catalog 只含 `clean`（active，有版本）+ `evil`（quarantined，无版本），不含 `foo`；git 根仍有 `claude/` + `.git` 全镜像；`pool_version_for_skill(git根,"clean",subdir="skills")` 与 catalog 的 `current_version` 一致；二次同步短路。repo-root 布局的既有 e2e/单测作为回归基线，保持不动、保持绿。
- **门禁**：`make test-pr` + `make test-integration-ci` + `make test-frontend` 全绿；`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` exit 0；`test_nominate_and_node_ingestion_path_are_git_free` 仍绿（node/agent 零 git）；mypy 改动模块通过。
