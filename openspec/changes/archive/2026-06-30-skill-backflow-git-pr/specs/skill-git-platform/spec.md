## ADDED Requirements

### Requirement: 可插拔 git 平台后端抽象

平台 SHALL 提供一个可插拔的 git 平台后端抽象（仿 `integrations/sandbox` 范式，**不依赖 platform**）：`BaseGitPlatformBackend` 定义 mandatory 的 `available()`（探活，永不抛）与 `push_branch(*, branch, bundle, subdir, base_ref, message, author)`（唯一走 dulwich git 协议，推备份/fork 分支），以及 capability-gated 的 PR 生命周期 `open_pull_request` / `get_pull_request` / `merge_pull_request` / `close_pull_request`（走平台 REST，基类未实现时抛 `NotImplementedError`）。能力差异 SHALL 经 `GitPlatformCapabilities`（frozen dataclass）声明，调用方 SHALL 按布尔能力门控，SHALL NOT 用 isinstance 判型。所有 git 交互 SHALL 只在 platform 侧发生。

#### Scenario: push_branch 走 git 协议推分支
- **WHEN** 调用 `push_branch` 把一个 skill 的 bundle 推到 `<branch>` 子目录
- **THEN** 经 dulwich 推一个新分支到远端，返回新分支 commit；token 在日志中脱敏

#### Scenario: 不支持的能力按门控跳过
- **WHEN** 某 backend 的 `GitPlatformCapabilities.open_pr` 为假，调用方欲开 PR
- **THEN** 调用方据能力布尔跳过/降级，而非 isinstance 判型；直接调用基类未实现方法 SHALL 抛 `NotImplementedError`

### Requirement: provider 选型与未知拒绝

平台 SHALL 经 `create_git_platform(*, config)` 按 `config.provider` 选型后端（config 由调用方从 `skill_git_source` 读出传入），优先支持 `bitbucket`，`gitea` / `gitlab` 预留 stub。未知 provider SHALL 记 warn 并**抛出**（SHALL NOT fallback 到任意 backend——写错权威 git 后果严重）。

#### Scenario: 已知 provider 选型成功
- **WHEN** `config.provider="bitbucket"`
- **THEN** 返回 Bitbucket backend 实例

#### Scenario: 未知 provider 抛出
- **WHEN** `config.provider` 为未知值
- **THEN** 记 warn 并抛错，不返回任意 backend

### Requirement: git 不可达经类型化异常暴露

后端探活失败或远端不可达时 SHALL 经 `GitPlatformUnavailable`（或 `available()` 返回假）暴露，SHALL NOT 让底层连接异常裸传到调用方。调用方据此降级（标 deferred、下轮重试），SHALL NOT 因单次 git 不可达而崩溃定时任务或误改治理状态。

#### Scenario: 远端不可达暴露为 GitPlatformUnavailable
- **WHEN** push 或 PR 操作时远端不可达
- **THEN** 抛 `GitPlatformUnavailable`（而非裸连接异常），调用方据此降级重试
