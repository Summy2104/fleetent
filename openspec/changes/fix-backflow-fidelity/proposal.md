## Why

回流（Change 3 `skill-backflow`）落地后审查发现两处保真度缺陷：

1. **`diff_vs_base` 功能性坏掉（bug）**：Change 2 有意把 `agent_skills.base_version` 保留为**内容 hash**（drift 检测用，工程上更稳），但 `backflow_store.get_proposal_diff` 把该内容 hash 当 git ref 传给 `pool_content_at()`（期望 git 对象）→ 无此对象 → 静默返回 None → `diff_vs_base` 退化成「整个进化内容当全新增」，而非真实的 base→evolved 增量。回流 review 最关键的「这个 agent 究竟改了什么」diff 是空壳。测试只断言 diff 是非空字符串，弱断言放过了它。
2. **多文件 bundle 回流有损（限制）**：`backflow_proposals.proposed_content` 是单个 Text，仅存 SKILL.md；accept/fork 也只写 SKILL.md。但 reflection 的 `write_skill` 能产多文件 skill（脚本/子目录），drift 检测也覆盖整个 bundle → 多文件 skill 回流时脚本/资源**静默丢失**。

两者都改 `backflow_proposals` schema 与 accept/fork 写路径，合一个 change 一次迁移修完。

## What Changes

- **记录部署时池 git sha**：materialize 覆盖 agent skill 副本时，除现有内容 hash `base_version` 外，SHALL 额外在 `agent_skills.base_commit` 记录该副本物化自的**池 git commit**（per-skill 子树版本）。`base_version`（内容 hash）继续专用于 drift 检测，语义不变；`base_commit`（git sha）专供回流重建 base。**BREAKING**（agent_skills 加列，需迁移）。
- **回流提案携带 base_commit**：提名时把 `base_commit` 快照进提案。
- **`diff_vs_base` 重建真实 base**：用 `base_commit`（git sha）从池 git 取回 base 内容做 diff，展示真实 base→evolved 增量，不再把内容 hash 当 ref。
- **回流携带完整 bundle**：提案捕获进化副本的**全部文件**（非仅 SKILL.md）；accept/fork 把完整 bundle 写回池。`backflow_proposals` 的内容列从「单 SKILL.md Text」改为「bundle（relpath→content）」。**BREAKING**（列语义变，存量行迁移为 `{"SKILL.md": <旧值>}`）。
- **回归测试补强**：新增断言 `diff_vs_base` 反映真实增量（而非仅非空），堵住放过本 bug 的弱断言。

## Capabilities

### Modified Capabilities
- `skill-backflow`: 提名捕获 `base_commit` + 完整 bundle；`diff_vs_base` 从 `base_commit` 重建真实 base 内容；accept/fork 写回完整 bundle。
- `skill-drift-protection`: materialize 除 `base_version`（内容 hash）外，额外记录 `base_commit`（部署时池 git sha），供回流重建 base；drift 判定仍仅用 `base_version`，不受影响。

## Impact

- **owning package**: `platform`（`skill_management/backflow` + `agent_lifecycle/materialize`）。
- **public API surface**:
  - `materialize`：覆盖副本时额外写 `agent_skills.base_commit = pool_version_for_skill(skill)`。
  - `backflow_store`：`create_proposal` 捕获 `base_commit` + 完整 bundle；`get_proposal_diff` 用 `base_commit` 重建真实 base。
  - `backflow_api`：accept/fork 写回完整 bundle（非仅 SKILL.md）。
  - `pool_git`：`pool_content_at` 保持按 git ref 取内容（调用方改传 `base_commit` 而非内容 hash）；如需按 bundle 取回 base，新增 bundle-aware 读取（内部）。
  - `skill_admin_store`：`agent_skills` 读写含 `base_commit`。
- **owned tables**（management.db，Alembic，**迁移号 apply 时定、不写死**）：
  - `agent_skills`：加 `base_commit`（git sha，nullable，默认 NULL，下次物化 backfill）。
  - `backflow_proposals`：加 `base_commit`；内容列由单 SKILL.md Text 改为 bundle（relpath→content JSON），存量行迁移为 `{"SKILL.md": <旧 proposed_content>}`。
- **config namespace**: 无新增。
- **cross-module dependencies**: platform 读 agent home 进化副本（含全 bundle 文件，单向 platform→agent 读）+ 用 `pool_git`；agent→platform 零反写不变。
- **migration/shim plan**: 一支 forward 迁移加 `base_commit` 两列 + 内容列转 bundle（存量转 `{"SKILL.md": …}`）；downgrade 反向。`agent_skills.base_commit` 存量 NULL → 下次物化 backfill；NULL base_commit 的提案 `diff_vs_base` 优雅降级（标注无 base 可重建）。
- **out of scope**: drift 检测机制不变（仍 content-hash）；池 git 版本化机制不变（复用 Change 2）；`docs/architecture/data-model.md` 与主 specs 不在本 change 改（集成车道统一刷）。
