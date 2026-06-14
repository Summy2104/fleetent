## Why

Change 1 落地了 content-hash 版本机制（`_skill_dir_version` + `agent_skills.base_version`）让部署保护跑通，但 `skills.current_version` 仍是未填充的占位，且 content-hash 是不透明、无历史、不可 diff 的版本身份。回流（第 3 期）需要的**版本历史、diff、冲突检测、可归因的变更记录、稳定的版本 ref**，content-hash 都给不了。

本 change（3 期路线第 2 期）把公共池升级为 **git-on-disk** 版本化底座：池目录成为 git 仓库，每次池变更落一次可归因 commit，`current_version`/`base_version` 升级为 git sha，并暴露**只读**的版本历史 / diff 接口。git 全程本地、不出内网、无新增云依赖（合数据主权）。

读侧（历史 / diff）本身就有企业 on-prem 审计价值（「谁何时改了哪个池 skill」），同时是第 3 期回流 review 的读侧地基；回流的**写 / 调和路径**留给第 3 期，本 change 不做。

## What Changes

- **池目录成为 git 仓库**：首次使用时幂等 `git init`；builtin skill seed 作为一次 commit 落入；非 git 仓库的存量池在升级时初始化并提交当前内容为初始 commit。
- **每次池变更提交一次 commit**：admin create/edit/upload/archive 等写路径在改完文件后提交，附可归因信息（操作者 / `system` for seed）。
- **`current_version` 升级为 git 版本并填充**：每个 skill 的 `current_version` SHALL = **最后触及该 skill 子树的 commit 标识**（per-skill 版本，单仓内精确到子树）。
- **`base_version` 升级为 git sha**：materialize 记录的 `base_version` 从 content-hash 改为对应池版本的 git 标识；存量 content-hash base 平滑过渡（首次 post-升级物化时无法解析为 git 对象 → 回退内容比对并 re-baseline，避免误判全员 drift）。
- **新增只读版本接口**：`GET /admin/skills/{name}/versions`（历史）+ `GET /admin/skills/{name}/versions/{ref}/diff`（某版本 diff），供审计与第 3 期 review 读侧。
- **池 git 写串行化**：单机文件锁，避免并发写池仓损坏。
- 实现层用 **纯 Python git 库（dulwich）**，不依赖宿主 `git` 二进制（保持自包含部署）。

## Capabilities

### New Capabilities
- `skill-pool-versioning`: 公共 skill 池作为 git-on-disk 仓库的版本化——池仓初始化与 seed 提交、每次池变更可归因 commit、per-skill 版本 = 子树最后 commit、只读版本历史 / diff、池写串行化。

### Modified Capabilities
- `skill-catalog`: `skills.current_version` 从「未填充的 head 指针占位」升级为「池 git 中该 skill 子树的最后 commit 标识，随池变更更新」。
- `skill-drift-protection`: materialize 记录的 `base_version` 从 content-hash 升级为池版本的 git 标识；存量 content-hash base 的过渡 / re-baseline 规则。

## Impact

- **owning package**: `platform`（`skill_management` 新增池 git 模块 + `agent_lifecycle/materialize`）。
- **public API surface**:
  - 新增池版本化模块（如 `skill_management/pool_git.py`）：`commit_pool(...)` / `pool_version_for_skill(name)` / `pool_diff(name, ref)` / `pool_content_at(name, ref)` 等。
  - `skill_admin_store`：`current_version` 读写改由池版本驱动。
  - `skill_admin_api`：新增 2 个只读版本端点；create/edit/upload/archive 写路径接池 commit。
  - `materialize`：`base_version` 写 git 标识 + content-hash 过渡逻辑。
- **owned tables**: **无 schema 变更**（`current_version`/`base_version` 列已于 Change 1 存在，本 change 只改填充语义）；故**无 Alembic 迁移**。池仓初始化 + `current_version` backfill 走 scan/init 数据步骤，不是 schema 迁移。
- **config namespace**: 无新增（池目录沿用 `FLEETENT_SKILLS_DIR` > `./skills`）。
- **new dependency**: `dulwich`（纯 Python git，Apache-2.0，可自托管、无宿主 git 依赖）。
- **cross-module dependencies**: 池 git 全在 platform 侧；agent 运行时不感知 git、仍只读自己 home 的 skill 文件——单向 platform→（池/agent home）读写，agent→platform 零反写不变。
- **migration/shim plan**: 无 schema 迁移。存量非 git 池在 init 时提交初始 commit；存量 `agent_skills.base_version`（content-hash）在首次 post-升级物化时 re-baseline 为 git 标识。
- **out of scope**: 回流写 / 调和路径（promote/discard/fork、池 commit-on-accept）属第 3 期 `skill-backflow`；多租户 per-tenant 池仓（远期）；`docs/architecture/data-model.md` 与主 specs 不在本 change 改（集成车道统一刷）。
