# Design — Skill Management (Admin 管理面)

本 change 设计的是 **Skill 管理面后端**（FastAPI `/admin/skills/*`），不是 Skill 引擎。引擎语义（扫描 / 关键词匹配 / 注入 system prompt / 安全审计规则 / 禁用机制 / 热加载实现）归 [skill](../../../docs/capabilities/skill.md) 域；AI 提案的产出与应用归 [reflection](../../../docs/capabilities/reflection.md) 域。本面只调用这两个域的 public API、维护管理面专属的绑定 / 来源 / 审批入口状态，并把可观察行为暴露为 REST。

## 与 skill / reflection 域的边界

| 行为 | 归属域 | 本管理面做什么 |
|------|--------|----------------|
| 扫描 `skills/`、构建索引、关键词匹配、注入 system prompt | skill | 不碰，只读其索引列出 Skill |
| 安全审计（识别注入模式，三级结论） | skill | 调用其审计 API，**展示**结论、按结论**门控**上线、维护隔离区状态 |
| 全局禁用 / agent 级禁用的运行时语义 | skill | 提供 UI 入口，写「期望禁用态」并让引擎读取；不重实现匹配逻辑 |
| 热加载（重扫描、原子切换、失败回退） | skill | 提供「重新扫描」触发入口，渲染其返回的成功 / 失败结果 |
| 生成 Skill 变更提案（create/update/delete, pending） | reflection | 不生成，只**汇总**收件箱并展示 |
| 提案 diff 的 snapshot 来源 | reflection | 读取 reflection 的 snapshot 与当前内容做 diff 展示 |
| approve 后应用提案（覆盖写入 + 热加载） | reflection | 调用其应用入口，**回写**提案状态、写审计 |
| 受管 Skill 的编译、drift 的覆盖回流（promote/discard）语义 | askit | 只标记 drift、提供回流触发入口 |

原则：**本管理面只持有"管理面专属事实"**——Skill↔Agent 绑定、来源徽章 / drift 标志、提案审批结果回写。引擎事实（索引、匹配、审计规则、注入）一律向 skill 域读取，绝不在管理面缓存或重算。

## 身份 / 数据模型

Skill 的稳定 identity 是其 **skill 名（name，来自 frontmatter）** + skill 域索引里的 skill 记录；管理面不另造主键覆盖引擎。管理面新增两张表挂在 skill 名上：

- `agent_skills`：`(agent_id, skill_name, enabled, updated_at, updated_by)`。表达「哪些 Skill 对哪个 Agent 启停」的矩阵；同时是删除引用保护的查询源（哪些 Agent 仍显式启用某 Skill）。全局禁用与 agent 级禁用是两层：全局禁用是 skill 域的 Skill 级状态，`agent_skills.enabled=0` 是 agent 级覆盖。
- `skill_provenance`：`(skill_name, source, drift, immutable_fields, last_deploy_at, updated_at)`。`source ∈ {managed, adhoc}`；`drift` 标志受管 Skill 被 UI 改动；`immutable_fields` 记录对齐 askit IMMUTABLE_FILES 的不可变字段，UI 改了会在下次 deploy 还原并给提示。

`skill_proposals` 表**复用 reflection 域已有表**（若 reflection 域尚未建，由 reflection 域负责建，本 change 不重复建表——见 tasks `## 0. 前置`）。管理面只读其 pending 行并回写 `status`（approved / rejected）+ 审批人 + 审批时间。

所有 store SQL 用 named params（`:skill_name`），schema 走 Alembic，路径常量可 monkeypatch，禁 ORM（遵循 CLAUDE.md）。

## 关键设计决策

1. **上传 / 编辑的门控流水线**：保存请求 → 校验 frontmatter（YAML 合法 + 必填字段）→ 调 skill 域安全审计 → 按结论分流：
   - 拒绝加载：不上线、写入隔离区状态、返回命中的注入模式、写审计；该 Skill 不参与任何匹配注入。
   - 可疑：上线 + 列表打「可疑」标 + 详情展示命中规则；写审计。
   - 通过：上线；写审计。
   上线动作统一触发热加载，使后续请求可匹配、进行中会话不受影响（热加载语义以 skill 域为准）。
2. **隔离区是状态而非独立表**：被判「拒绝加载」的 Skill 在管理面标记为 quarantined（隔离），不参与注入；admin 显式复核「强制上线」需二次确认（高危），强制上线写审计并把状态翻为「可疑（已强制）」，不静默转为通过。
3. **软删除 + 引用保护**：删除 = 归档，不物理删。归档前查 `agent_skills` 是否仍有 Agent `enabled=1`；有则阻止删除、列出占用方、请求不落库；无则归档（不再匹配注入、列表隐去、文件快照与历史 trace 保留），保留期内可恢复。
4. **观测是聚合视图，数据源是 observability**：按 Skill 观测页只做按 skill 的聚合（命中 / 注入次数、触发会话列表、最近 N 天是否触发、长期零触发高亮），明细 trace 下钻复用 observability，不在本面落存 trace。
5. **审批走 reflection 应用，不在管理面改 Skill**：approve 只调 reflection 应用入口并回写提案状态；reject 只关闭提案、不动 Skill。本面绝不直接覆盖写 Skill 内容，避免与 reflection snapshot 语义双源。

## 受管（spec-owned）/ 临管（DB-only）来源模型与 drift

与 Agent 一致（见 platform.md「fleetent 自管理：双层来源 + 覆盖回流」）：

- UI 上传 / 新建产出 **临管** Skill（`source=adhoc`），只活在 DB / 文件，git 不追踪。
- askit `deploy --target fleetent` 从 spec / `SKILL.md` 编译来的是 **受管** Skill（`source=managed`），列表打受管徽章。
- 受管 Skill 被 UI 改动 → 视为运行时覆盖，`drift=1`，列表标 drift；admin 在「覆盖回流」入口以 diff 审阅后 `promote`（开 PR 转正）或 `discard`（下次 deploy 被 spec 覆盖还原）。覆盖回流的实际语义归 askit 域，本面只标记并触发。
- 不可变字段（对齐 askit IMMUTABLE_FILES）UI 改了也会在下次 deploy 被 spec 还原，UI 给明确提示。
- identity = 稳定的 skill 名，「受管 / 临管」只是同一行上的标志位；临管转受管走 askit `decompile` / `deploy adopt`，绑定与历史 trace 天然续上。

## 安全审计隔离区

隔离区不是新表，而是 skill 域审计结论 + 管理面 quarantine 标志的组合视图：

- 列表 / 详情展示每个 Skill 的最近一次审计结论（通过 / 可疑 / 拒绝加载）与命中规则。
- 「拒绝加载」→ quarantined，不参与注入；viewer 可见、不可操作。
- 强制上线是唯一能离开隔离区的写操作，仅 admin、要求二次确认、写审计；强制上线后保留「可疑（已强制）」标记供持续复核。

## 热加载触发

「重新扫描」按钮调用 skill 域热加载入口（等价 CLI / 管理 API 触发的重扫描）：

- 重扫描期间继续用旧索引服务请求；完成后原子切换（语义以 skill 域为准）。
- 扫描失败保留旧索引并在 UI 告警；本面把 skill 域返回的成功 / 失败结果如实渲染，不自行重试或吞错。

## 按 Agent 启停（Skill ↔ Agent 矩阵）

- 在 Agent 详情勾选可用 Skill，或在 Skill 详情查看 / 调整启用它的 Agent 列表——两处共用 `agent_skills` 同一引用视图。
- agent 级停用：`agent_skills.enabled=0`，该 Agent 不注入该 Skill，其他启用了该 Skill 的 Agent 不受影响（匹配语义最终以 skill 域读取该期望态为准）。
- 同一引用视图供删除引用保护复用：归档前查"哪些 Agent 仍 enabled=1"。

## 权限与审计

- 复用 user-management 的 `auth.require_role`：`/admin/skills/*` 写操作要求 `role ∈ {admin, built_in_admin}`，viewer 一律 403；viewer 仅可浏览列表、审计结论、观测。
- 高危动作（归档、强制上线疑似注入 Skill、approve 提案）要求二次确认。
- 所有写操作经 `audit_log` 落「谁 / 何时 / 对哪个 Skill / 做了什么」。

## 测试隔离策略（遵循 CLAUDE.md）

- 新 store（`skill_admin_store`）路径可 monkeypatch 到 `tmp_path`；或复用统一 DB fixture；不触碰 `data/`。
- skill 域安全审计 / 热加载 / 禁用 / 索引列出：在单测中 mock skill 域 public API，断言被调用与分流，不依赖真实文件扫描或注入模式库。
- reflection 域提案应用：mock reflection 应用入口，断言 approve 调用 + 状态回写、reject 不调用应用，不真实改 Skill。
- 文件上传 / frontmatter 校验：构造内存内容，单测验证校验通过 / 拒绝分支，不写真实 `skills/` 目录。
- API 层（`skill_admin_api`）：FastAPI TestClient 验证角色守卫（无 session 401、viewer 写 403、admin 通过）、门控分流（拒绝 / 可疑 / 通过）、引用保护阻止删除、审批端点回写。导入 server 链路需 Python 3.12（PEP 695，见仓库版本约定）。
- 观测聚合：mock observability 查询，断言按 skill 聚合形态，不发真实 trace 查询。
- 测试分层：store / 校验 / 门控分流入 `tests/unit/`（mock 外部域）；Alembic 迁移 + FastAPI TestClient 路由入 `tests/integration/`。
