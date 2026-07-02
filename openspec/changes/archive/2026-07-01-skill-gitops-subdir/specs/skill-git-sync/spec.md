## ADDED Requirements

### Requirement: 外部仓库子目录作为 skill 扫描根

平台 SHALL 支持把外部 git 仓库的某个子目录（配置项 `skills_subdir`）当作 skill 扫描根，而非仓库根本身。启用后，git 仓根 SHALL 继续整仓镜像（dulwich `fetch` + `reset --hard` 操作对象不变，不引入宿主 git 的 sparse-checkout）；skill 扫描（`list_pool_skills`、审计、内置 seed 恢复、per-skill 版本/历史/diff/bundle 寻址）SHALL 只针对仓根下的 `skills_subdir` 子目录，仓根下的其它目录（如 monorepo 中并列的 `claude/` `codex/` 等）SHALL NOT 被扫描或列为 skill。`skills_subdir` 为空/NULL 时，扫描根 SHALL 等于仓根，行为与未配置子目录时完全一致（向后兼容）。

#### Scenario: 配置子目录后只扫描该子目录

- **WHEN** 外部 git 源配置 `skills_subdir="skills"`，仓库根下同时存在 `skills/` 与 `claude/` 两个目录
- **THEN** 同步后的 catalog 只包含 `skills/` 下的 skill，`claude/` 下的内容不出现在 catalog 中

#### Scenario: 仓根仍整仓镜像

- **WHEN** 外部 git 源配置了 `skills_subdir`
- **THEN** 本地 git 仓根目录下仍能看到仓库的全部顶层目录（包括非 `skills_subdir` 的目录）与 `.git`，镜像范围不因 `skills_subdir` 收窄

#### Scenario: 未配置子目录时行为不变

- **WHEN** 外部 git 源的 `skills_subdir` 为空或未配置
- **THEN** 扫描根等于仓库根，同步、审计、版本重算行为与不支持 `skills_subdir` 之前完全一致
