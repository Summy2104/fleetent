## ADDED Requirements

### Requirement: GitOps 模式下 skill 内容写端点只读

当配置外部 git 源（见 `skill-git-sync`）时，skill 内容的写端点 SHALL 返回 409 并提示「内容改到 git 仓库提 PR」：`POST /admin/skills`（create / upload）、`PUT /admin/skills/{name}`（edit）、archive / restore、force-publish。读取与运维端点 SHALL 保留正常工作：list、content、版本历史 / diff、per-skill observability、global enable / disable、per-agent 绑定、hot reload。内容安全审计在此模式下由入站同步兜底（见 `skill-git-sync`），不再经写端点执行。

#### Scenario: 写端点在 GitOps 下 409
- **WHEN** 外部 git 源已启用，admin 调 create / upload / edit / archive / restore / force-publish
- **THEN** 返回 409 并提示改到 git 提 PR，池内容不变、不持久化

#### Scenario: 读与运维端点保留
- **WHEN** 外部 git 源已启用，admin 调 list / content / versions / diff / enable-disable / 绑定 / reload
- **THEN** 正常工作（这些不写 skill 内容）

#### Scenario: 未启用外部源时写端点不变
- **WHEN** 未配置外部 git 源
- **THEN** 既有写端点（create/edit/archive 等）行为不变
