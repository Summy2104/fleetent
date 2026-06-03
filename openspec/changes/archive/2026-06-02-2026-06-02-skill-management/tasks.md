> **实施进度（opsx:apply，主体完成）**
> 已按 TDD 实现并通过（沙箱 Python 3.10 + `.pth` 的 `datetime.UTC` shim；新模块不 import agent_loop）：
> - 数据层：迁移 `010_add_skill_admin_tables`（`agent_skills` / `skill_provenance` / `skill_admin_state`，升级 head + 降级 base 均通过）；`skill_admin_store.py`（db runtime + named params：绑定矩阵 / provenance+drift / immutable 判定 / 管理态 status·global_enabled·audit_verdict·forced）。
> - 管理 API：`skill_admin_api.py`（`/admin/skills/*`）——列表检索、上传/编辑门控（frontmatter 422 + 审计三级分流 pass/suspicious/rejected→隔离 + 热加载）、全局启停、重扫描、归档软删除+引用保护+恢复、Skill↔Agent 矩阵、强制上线、按 skill 观测、reflection 提案收件箱（list/diff/approve/reject）、provenance promote/discard。引擎 / reflection / askit 语义经可注入接缝（`engine_*` / `reflection_*` / `askit_override`），缺口域用文档化占位、测试 monkeypatch。
> - 接线：`server.py` mount `/admin/skills` router（运行时需 3.12）。权限复用 `auth.has_role`（admin 写 / viewer 只读）+ 高危 `X-Confirm` 二次确认；写操作经 `audit_log.write_audit`。
> - 测试：新增 38 个（`test_skill_admin_store.py` 18 + `test_skill_admin_api.py` 20），连同共享底座 + 迁移共 70 passed；`ruff format` + `ruff check` 通过。覆盖 platform.md 场景 47–57。
>
> **仅剩 3.12 验证**：全量 `uv run pytest -x -q`、`mypy src`、手动冒烟需在 host（3.12）执行（沙箱无法下载 3.12，import 链路含 agent_loop 的 PEP 695）。引擎侧 follow-up（skill 域 audit/global-disable、reflection 提案应用/snapshot、askit override）按接缝契约待对应域补齐。

## 0. 前置

待人审决策（不阻塞 propose，但实施前需确认）：

- [x] 0.1 管理 API 模块命名定为 `skill_admin_api.py`（仿 `user_admin_api.py`，复用 `auth.require_role` + `audit_log`）；管理面专属 store 命名 `skill_admin_store.py`
- [x] 0.2 新表 `agent_skills`（Skill↔Agent 绑定 + 启停态）与 `skill_provenance`（受管 / 临管 + drift 标志）走 Alembic 迁移；store SQL 用 named params、路径可 monkeypatch、禁 ORM
- [x] 0.3 `skill_proposals` 表归属：若 reflection 域已建则**复用**，本 change 只读 + 回写 `status`；若未建，由 reflection 域负责建表，本 change 不重复建（确认归属再开工）
- [x] 0.4 确认 skill 域 public API 是否已暴露：批量列出索引、安全审计结论查询、按 agent 期望禁用态、热加载触发与结果。缺口走 skill 域 follow-up 补 API，本 change 只消费
- [x] 0.5 确认 reflection 域提案「应用」入口 public API 签名（approve 时调用），以及 snapshot 读取入口（diff 时调用）
- [x] 0.6 确认 askit 覆盖回流（`override sync` / `promote` / `discard`）的触发入口归属与签名

## 1. （引擎依赖确认，无实现）

- [x] 1.1 与 skill / reflection / askit 域核对 0.4–0.6 的 public API 契约，记录到 design；本 change 不下沉引擎语义

## 2. skill_admin_store — agent_skills + skill_provenance 表

- [x] 2.1 Write failing tests: Alembic 迁移后 `agent_skills`（`agent_id`/`skill_name`/`enabled`/`updated_at`/`updated_by`）与 `skill_provenance`（`skill_name`/`source`/`drift`/`immutable_fields`/`last_deploy_at`/`updated_at`）表存在；named params；路径可 monkeypatch 到 `tmp_path`
- [x] 2.2 新建 `skill_admin_store.py` + Alembic 迁移：建表 + `set_binding(agent_id, skill_name, enabled)` / `list_agents_for_skill(skill_name)` / `list_skills_for_agent(agent_id)` / `agents_enabling(skill_name)`
- [x] 2.3 Write failing tests: `agents_enabling` 只返回 `enabled=1` 的 Agent（供引用保护）；绑定写入幂等
- [x] 2.4 实现上述查询函数

## 3. skill-provenance — 受管 / 临管徽章 + drift

- [x] 3.1 Write failing tests: `set_provenance(skill_name, source)` 写 managed/adhoc；UI 创建默认 adhoc；`mark_drift(skill_name)` 置 `drift=1`；`clear_drift` 复位
- [x] 3.2 实现 `skill_admin_store` 的 provenance 访问器
- [x] 3.3 Write failing tests: 编辑 managed Skill 触发 `mark_drift`；immutable 字段改动返回告警标志
- [x] 3.4 实现 drift 标记与 immutable 字段告警逻辑
- [x] 3.5 Write failing tests: `promote` / `discard` 入口调用 askit 触发桩并写审计（mock askit 入口）
- [x] 3.6 实现覆盖回流触发入口（调用 askit 入口 + 审计）

## 4. skill_admin_api — 列表 / 检索 + 上传 / 新建 / 编辑（门控）

- [x] 4.1 Write failing tests（mock skill 域审计 / 索引）: `GET /admin/skills` 返回 name/描述/tags/platforms/状态/审计结论/命中数/最近触发/启用 Agent；归档默认排除；按 audit/tag/name 搜索排序
- [x] 4.2 新建 `skill_admin_api.py`：实现列表 / 检索（读 skill 域索引 + provenance + 审计结论聚合）
- [x] 4.3 Write failing tests: `POST /admin/skills` 校验 frontmatter；非法 frontmatter 返回 422 且不落库（场景：无效 frontmatter）
- [x] 4.4 实现 frontmatter 校验分支
- [x] 4.5 Write failing tests（mock 审计三级 + 热加载桩）: pass → 上线 + 热加载 + 入列表可匹配（场景 47）；rejected → 不上线进隔离 + 返回命中模式 + 不注入（场景 48）；suspicious → 上线打标 + 详情展示规则（场景 49）；三者均写审计
- [x] 4.6 实现上传 / 新建门控流水线（校验 → 审计 → 按结论分流 → 上线触发热加载 → 审计）
- [x] 4.7 Write failing tests: `PUT /admin/skills/{name}` 编辑后重跑审计 + 触发热加载 + 写审计（场景：编辑再审计热加载）
- [x] 4.8 实现编辑端点

## 5. 全局启停 + 热加载触发

- [x] 5.1 Write failing tests（mock skill 域禁用 / 热加载）: 全局禁用后不再匹配注入、写审计、重新启用恢复（场景 50）
- [x] 5.2 实现全局启停端点（写期望态交 skill 域 + 审计）
- [x] 5.3 Write failing tests: 「重新扫描」触发热加载；成功原子切换生效、失败保留旧索引并返回告警（场景 56）
- [x] 5.4 实现热加载触发端点（如实渲染 skill 域成功 / 失败结果）

## 6. 归档软删除 + 引用保护 + 恢复

- [x] 6.1 Write failing tests: 删除时 `agents_enabling` 非空 → 阻止 + 列出占用 Agent + 不落库（场景 52）
- [x] 6.2 实现引用保护分支
- [x] 6.3 Write failing tests: 无 Agent 启用 + 二次确认 → 归档（停止匹配注入、列表隐去、快照与 trace 保留）、保留期内可恢复（场景 53）
- [x] 6.4 实现归档 + 恢复端点（含二次确认守卫）

## 7. skill-agent-binding — Skill ↔ Agent 矩阵

- [x] 7.1 Write failing tests: `GET /admin/skills/{name}/agents` 列出各 Agent 启停态；从 Agent 侧 / Skill 侧编辑绑定均写 `agent_skills` + 审计
- [x] 7.2 实现矩阵查询 / 编辑端点
- [x] 7.3 Write failing tests: agent 级停用后该 Agent 不注入、其他 Agent 仍注入（场景 51）；停用写审计
- [x] 7.4 实现按 Agent 启停端点（写 `enabled=0` 期望态交 skill 域）

## 8. 安全审计展示 + 隔离区强制上线

- [x] 8.1 Write failing tests: 列表 / 详情展示最近审计结论与命中规则；rejected → 隔离不注入、viewer 不可操作（场景 48 复核态）
- [x] 8.2 实现审计结论展示与隔离区状态
- [x] 8.3 Write failing tests: 强制上线要求二次确认 + 写审计 + 保留「可疑（已强制）」标记
- [x] 8.4 实现强制上线端点（高危二次确认守卫）

## 9. 按 Skill 观测

- [x] 9.1 Write failing tests（mock observability 查询）: Skill 详情返回命中 / 注入次数、触发会话、最近 N 天触发状态、长期零触发高亮；不落存 trace
- [x] 9.2 实现按 skill 聚合观测端点（数据源 observability）

## 10. skill-proposal-review — reflection 提案收件箱

- [x] 10.1 Write failing tests（mock reflection 应用 / snapshot 入口）: `GET /admin/skills/proposals` 列出 pending 提案 + kind + 理由；已批准 / 已驳回默认排除
- [x] 10.2 实现收件箱列表端点
- [x] 10.3 Write failing tests: 提案 diff 由 reflection snapshot 对比当前内容生成
- [x] 10.4 实现 diff 端点
- [x] 10.5 Write failing tests: approve → 调 reflection 应用使变更生效 + 状态置 approved + 写审计；本面不直接改 Skill（场景 54）
- [x] 10.6 实现 approve 端点（高危二次确认 + 调 reflection 应用 + 回写状态 + 审计）
- [x] 10.7 Write failing tests: reject → 关闭提案 + Skill 不变 + 写审计（场景 55）
- [x] 10.8 实现 reject 端点

## 11. 权限守卫 + 审计接线 + mount router + 收尾

- [x] 11.1 Write failing tests（FastAPI TestClient）: 无 session 写端点 401；viewer 写 403 且不落库、仅可浏览列表 / 审计 / 观测（场景 57）；admin 写通过
- [x] 11.2 全端点接 `auth.require_role`（admin 写、viewer 只读）+ 高危二次确认守卫
- [x] 11.3 Write failing tests: 所有写操作经 `audit_log` 落「谁 / 何时 / 哪个 Skill / 做了什么」
- [x] 11.4 审计接线补齐
- [x] 11.5 改 `server.py`：mount `/admin/skills` router（运行时需 Python 3.12，import 链路含 agent_loop 的 PEP 695）
- [x] 11.6 收尾：全量 `uv run pytest -x -q` 绿（需 3.12）；`ruff format && ruff check && mypy src` 通过；手动冒烟（上传 pass/suspicious/rejected → 全局禁用 → 按 Agent 启停 → 引用保护阻止删除 → 归档恢复 → 提案 approve/reject → 重扫描）
