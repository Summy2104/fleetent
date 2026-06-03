## Why

平台的 Skill 目前只有引擎层（`skill_registry` 扫描 / 关键词匹配 / 注入 system prompt），管理面是空白：领域专家想上线一条行为指南，必须登录服务器改 `skills/` 目录里的文件、再手动触发重扫描，既不可审计也不可按 Agent 分配。对照 `platform.md` 的「Skill 管理」一节，缺口集中在：

1. **没有后台管理入口**：列表 / 检索 / 上传 / 新建 / 编辑 / 启停 / 归档全部缺失，无法在 UI 里把 Skill 当成可上传、可启停、可观测的一等公民。
2. **安全审计结论无处可见**：`skill` 域已规划「拒绝加载 / 可疑 / 通过」三级审计，但管理面没有展示与隔离区，被判注入的 Skill 无法被复核拦截。
3. **启停只有引擎语义、没有 UI 入口**：`skill` 域规划了全局禁用与 agent 级禁用，但缺一个「哪些 Skill 对哪个 Agent 可用」的可视化矩阵，也没有删除时的引用保护。
4. **reflection 提案无收件箱**：`reflection` 域在 prod 产出的 Skill 变更提案（create / update / delete，状态 pending）落在 `skill_proposals`，但 admin 没有逐条看 diff、approve / reject 的待办面。
5. **来源归属缺失**：askit `deploy --target fleetent` 编译来的「受管」Skill 与 UI 即时产出的「临管」Skill 没有徽章区分，受管对象被 UI 改动也不标 drift。
6. **无按 Skill 观测**：命中 / 注入次数、触发会话、长期零触发高亮等聚合视图缺失，无法支撑 reflection 的 delete 依据。

本 change 把以上补齐为一套 Skill 管理面。**只做管理面**：Skill 的扫描 / 匹配 / 注入 / 安全审计 / 禁用语义归 [skill](../../../docs/capabilities/skill.md) 域，AI 提案的产出与应用归 [reflection](../../../docs/capabilities/reflection.md) 域，本 change 仅提供这些能力的 `/admin/skills/*` 后端入口并交叉引用，绝不重复定义引擎语义。

## What Changes

**ADDED**

- `skill-admin-api`：`/admin/skills` 列表与检索（按名称 / tag / 状态 / 审计结论搜索排序）；上传（`SKILL.md` 或目录包）/ 在线新建 / 编辑，保存前校验 frontmatter 并触发 `skill` 域安全审计——「拒绝加载」进隔离区不上线、「可疑」上线打标、「通过」直接上线，上线即触发热加载；全局启停；软删除（归档）+ 引用保护 + 保留期恢复；触发「重新扫描」热加载入口；安全审计结论展示与隔离区强制上线（二次确认）；按 Skill 观测聚合视图；权限守卫（admin 写、viewer 只读）与全量审计。
- `skill-agent-binding`：Skill ↔ Agent 矩阵——在 Agent 详情或 Skill 详情按 Agent 维度启停某 Skill；该引用视图同时供「按 Agent 启停」与删除引用保护复用。
- `skill-proposal-review`：reflection 提案收件箱——汇总 `skill_proposals` 里的 pending 提案，逐条展示理由与 diff（基于 reflection snapshot 对比当前内容），approve 交回 reflection 应用、reject 关闭提案，审批结果回写状态并写审计。
- `skill-provenance`：受管（spec-owned）/ 临管（DB-only）徽章；受管 Skill 被 UI 改动标 drift，与 askit 覆盖回流（`override sync` / `promote` / `discard`）对接。

**MODIFIED**

- 无引擎语义改动。本 change 仅在 `skill` 域既有 public API 之上调用（安全审计、热加载、禁用、列出索引），不修改其契约；若 `skill` 域 public API 缺口（如批量列出索引、按 agent 查禁用态），以 follow-up 在 `skill` 域补充，本 change 不擅自下沉。

## Capabilities

### New Capabilities

- `skill-admin-api`
- `skill-agent-binding`
- `skill-proposal-review`
- `skill-provenance`

### Modified Capabilities

- 无

## Impact

- **代码**：
  - 新增：`skill_admin_api.py`（`/admin/skills` 路由，仿 `user_admin_api.py`；复用 `auth.require_role` 与 `audit_log`）、`skill_admin_store.py`（`agent_skills` 绑定表 + `skill_provenance` 来源标志的 store 边界，named params，路径可 monkeypatch）。
  - 修改：`server.py`（mount `/admin/skills` router）；`skill_registry`（仅在缺 public API 时由 `skill` 域 follow-up 补出 list/disable/audit 查询入口，本 change 通过既有 public API 调用，不改其内部）。
- **依赖**：无新依赖。文件包上传走标准库；审计 / 热加载 / 禁用复用 `skill` 域 API；提案应用复用 `reflection` 域 API。
- **数据**：新增 `agent_skills`（Skill↔Agent 绑定 + 启停态）、`skill_provenance`（每个 Skill 的受管 / 临管标志 + drift 标记）两表，走 Alembic 迁移；`skill_proposals` 若已由 reflection 域建表则复用、不重复建（见 `## 0. 前置`）。
- **认证依赖**：复用 user-management change 的 `auth.require_role`（admin 写、viewer 只读）与 `audit_log`（所有写操作落审计），不自建鉴权。
- **跨域 follow-up**：
  - `skill` 域：若安全审计结论、按 agent 禁用态、热加载结果未通过 public API 暴露，需在 `skill` 域补 public API（本 change 只消费）。
  - `reflection` 域：提案 approve 的实际应用（snapshot 覆盖写入 + 热加载）由 reflection 域执行；本 change 只调其应用入口并回写状态。
  - askit 域：受管 Skill 的 drift 捕获与 `promote` / `discard` 覆盖回流语义归 askit 外部工具域，本 change 只标记 drift 并提供回流入口。
- **破坏性**：无。新增表与路由，不改既有契约；存量 Skill 默认按「临管 + 审计未知」初始化，首次扫描后回填审计结论。

## Commit 切分建议

每个 commit 自包含、内部 TDD（测试先红 → 实现 → 绿）：

1. `feat(skill_admin_store): agent_skills binding + skill_provenance tables + migration`（2.x）
2. `feat(skill_provenance): managed/ad-hoc badge + drift marking`（3.x）
3. `feat(skill_admin_api): list/search + upload/create/edit with frontmatter validation + security audit gating`（4.x）
4. `feat(skill_admin_api): global enable/disable + hot reload trigger`（5.x）
5. `feat(skill_admin_api): archive soft-delete + reference protection + restore`（6.x）
6. `feat(skill_agent_binding): Skill↔Agent matrix endpoints`（7.x）
7. `feat(skill_admin_api): security audit display + quarantine force-publish`（8.x）
8. `feat(skill_admin_api): per-skill observability aggregation view`（9.x）
9. `feat(skill_proposal_review): reflection proposal inbox + diff + approve/reject`（10.x）
10. `feat(skill_admin_api): role guard + audit wiring + mount router`（11.x）
