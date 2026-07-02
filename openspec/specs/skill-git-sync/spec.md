# skill-git-sync Specification

## Purpose
把外部 git 仓库配置为 skill 内容的权威源：平台经 dulwich `fetch` + `reset --hard` 把外部分支镜像进本地池（外部权威、本地只读），同步落地后逐 skill 审计兜底与版本重算、`reset --hard` 后恢复内置 seed，并经定时 / webhook / 手动三种方式触发。全程舱壁化（任一步失败不抛、不崩调度）、凭证隔离（密文走 agent_secrets、仅以 env 名引用），且所有 git 交互只发生在 platform 侧，node 与 agent 不接触外部 git。

## Requirements

### Requirement: 外部 git 源镜像同步（fetch + reset）

平台 SHALL 支持把一个外部 git 仓库配置为 skill 内容权威源。启用后，平台 SHALL 经 dulwich `fetch`（支持 http(s) basic auth）取配置分支的远端 commit，再 `reset --hard` 到该 commit，使本地 pool 工作树与外部分支完全一致（镜像语义：外部权威、本地只读）。远端 commit 未变化时 SHALL 短路（不 reset、不重算）。同步 SHALL 经纯 Python（dulwich），不依赖宿主 git 二进制。所有 git 交互 SHALL 只发生在 platform 侧，node 与 agent SHALL NOT 接触外部 git。

#### Scenario: 首次同步把外部主分支镜像进 pool
- **WHEN** 配置并启用外部 git 源后首次同步
- **THEN** 本地 pool 工作树等于外部分支 HEAD，记录 last_synced_commit

#### Scenario: 远端无变化时短路
- **WHEN** 同步时远端 commit 与上次 last_synced_commit 相同
- **THEN** 不执行 reset、不重算版本，仅更新 last_sync_at

### Requirement: 入站审计兜底与版本重算

同步落地后，平台 SHALL 逐 skill 跑安全审计（与 agent 加载审计同一套规则）：审计为 severe 的 skill SHALL 被隔离（quarantine）且不更新其 current_version（不进分发）；通过的 skill SHALL 标 active 并把 current_version 更新为其子树最后 commit。外部仓中已删除的 skill SHALL 软删（archived，保留绑定），不物理删行。

#### Scenario: 注入 skill 被隔离不分发
- **WHEN** 外部仓某 skill 内容触发 severe 审计规则，同步落地
- **THEN** 该 skill 被隔离、不更新 current_version、不进入分发

#### Scenario: 干净 skill 激活并前移版本
- **WHEN** 外部仓某 skill 通过审计，同步落地
- **THEN** 该 skill 标 active，current_version = 其子树最后 commit

#### Scenario: 外部删除的 skill 软删
- **WHEN** 某 skill 在外部仓被删除后同步
- **THEN** 该 skill 标 archived（保留绑定），不物理删除

### Requirement: 内置 seed 在镜像后恢复

因 `reset --hard` 会清掉外部仓不含的内置 skill，平台 SHALL 在每次 reset 后重新种入内置 skill（`materialize_builtin_skills`）并提交，保证内置 skill 始终可分发。

#### Scenario: reset 后内置 skill 仍在
- **WHEN** 外部仓不含内置 skill，同步执行 reset --hard
- **THEN** reset 后内置 skill 被重新种入并提交，仍出现在 pool 与分发中

### Requirement: 同步触发（定时 + webhook + 手动）

平台 SHALL 经 platform 维护调度器按可配间隔定时触发同步；SHALL 暴露 `POST /admin/skills/git/webhook` 供外部 git 平台推送钩子触发，仅经 HMAC 校验（强制配置 secret，否则拒收），且 SHALL NOT 信任 payload 内容（仅作触发信号，内容一律以 fetch 结果为准）；SHALL 暴露 `POST /admin/skills/git/sync`（admin 手动）与 `GET /admin/skills/git/status`（同步状态，凭证脱敏）。

#### Scenario: webhook 经 HMAC 触发同步
- **WHEN** 外部 git 平台以正确 HMAC 签名推送 push 钩子
- **THEN** 校验通过并触发一次同步；签名错误返回 401；未配置 secret 时拒收

#### Scenario: 手动同步与状态查询
- **WHEN** admin 调 `POST /admin/skills/git/sync` 或查 `GET /admin/skills/git/status`
- **THEN** 前者触发同步，后者返回 last_synced_commit / last_sync_at / last_sync_error（凭证仅返回 env 名，绝不返回密文）

### Requirement: 同步舱壁化与凭证隔离

同步过程 SHALL 舱壁化：任一步失败 SHALL 记录 last_sync_error 且绝不抛出（不影响其它维护任务、webhook 请求线程、服务启动）；启动期 SHALL NOT 强制接触外部网络（remote 配置延迟到首次同步）。外部 git 源运营配置 SHALL 存于管理库，凭证值 SHALL 经 agent_secrets 以 env 名引用方式存取，SHALL NOT 入库明文、SHALL NOT 进 yaml / git / 日志。

#### Scenario: 同步失败不崩调度
- **WHEN** fetch 因网络或认证失败
- **THEN** 记录 last_sync_error、不抛出、下次到期重试，其它维护任务不受影响

#### Scenario: 凭证不泄露
- **WHEN** 查询同步状态或配置
- **THEN** 仅返回凭证的 env 名，绝不返回密文

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
