## ADDED Requirements

### Requirement: Skills managed natively in the React SPA

The React admin SPA SHALL render the skills domain natively (not a deep-link to legacy) and SHALL support, against the existing admin API: list skills, view skill content (read-only), enable / disable, manage agent bindings, view versions and version diffs, reload, and view per-skill observability. The proposals area SHALL remain **read-only** (list + diff, no approve/reject — proposal approval is agent-owned and delivered via DM).

When an external git source is configured (GitOps mode), the skills page SHALL be **content read-only**: it SHALL NOT offer create / edit / upload / archive / restore / force-publish controls (those backend endpoints return 409), SHALL show a banner indicating that skill content is authored in the external git repo (open a PR), and SHALL surface a **git sync status** card (last synced commit / time / error) with an admin "sync now" action against `/admin/skills/git/{status,sync}`.

#### Scenario: List skills and toggle enable

- **WHEN** an admin opens the skills view and enables/disables a skill
- **THEN** skills are listed via `GET /admin/skills` and the toggle calls `POST /admin/skills/{name}/enable`|`/disable`, refreshing the row

#### Scenario: GitOps mode hides content-write controls

- **WHEN** an external git source is configured and an admin opens the skills view
- **THEN** there are no create / edit / upload / archive / restore / force-publish controls, a "content authored in git" banner is shown, and a git sync status card with a "sync now" action is rendered

#### Scenario: View proposals read-only

- **WHEN** an admin opens the proposals area and selects a proposal
- **THEN** proposals are listed via `GET /admin/skills/proposals` and the diff via `GET /admin/skills/proposals/{id}/diff`, with no approve/reject controls

#### Scenario: Skills no longer deep-link to legacy

- **WHEN** the SPA navigation is rendered
- **THEN** Skills is a native route, not an entry in the legacy deep-link list

### Requirement: 回流审批区（平台治理，含决策控件）

React admin SPA SHALL 在 skills 域渲染一个**回流（backflow）审批区**，对接 backflow 端点（`GET /admin/skills/backflow`、`GET /admin/skills/backflow/{id}/diff`、`POST /admin/skills/backflow/{id}/accept|reject|fork`）：列出待审回流提案、查看单提案 diff、提供 accept / reject / fork 决策控件。该区是**平台治理**决策区，与既有 reflection proposals **只读**区相互独立、互不混用（后者对接 `/admin/skills/proposals`，是 agent-owned、DM 审批，故只读；本区对接 `/admin/skills/backflow`，是平台治理审批，故有决策控件）。

冲突提案（`conflict=1`）的 accept SHALL 要求显式二次确认，并在确认后携带 `X-Confirm: true` 提交；用户取消确认 SHALL NOT 发起请求。

#### Scenario: 列出回流待审并看 diff
- **WHEN** admin 打开 skills 视图的回流审批区并选中一条提案
- **THEN** 待审经 `GET /admin/skills/backflow` 列出、diff 经 `GET /admin/skills/backflow/{id}/diff` 展示

#### Scenario: accept / reject / fork 决策
- **WHEN** admin 对一条回流提案点击 accept / reject / fork
- **THEN** 分别调用 `POST /admin/skills/backflow/{id}/accept|reject|fork`（fork 携带 `fork_name`），成功后刷新待审列表

#### Scenario: 冲突项 accept 需二次确认
- **WHEN** admin 对一条 `conflict=1` 的提案点击 accept
- **THEN** 先弹出二次确认；确认后请求携带 `X-Confirm: true`；取消则不发请求

#### Scenario: 回流区不与 reflection 只读区混用
- **WHEN** SPA 渲染 skills 视图
- **THEN** reflection proposals 区仍只读（无 approve/reject），回流审批区独立存在并提供决策控件
