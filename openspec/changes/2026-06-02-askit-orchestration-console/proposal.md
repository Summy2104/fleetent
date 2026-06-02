## Why

fleetent 要把 askit（ai-skills-toolkit，spec 驱动编译器）的整套命令面收敛为后台一个**按系列分类的编排控制台**，让 admin 在 UI 里按系列触发操作、看实时日志与结果、走审批与审计，**无需登录服务器敲命令**。对照 `docs/capabilities/platform.md` 「askit 编排控制台」一节，缺口为：

1. **没有控制面**：askit 的 build / deploy / override / cron / doctor / migrate 等命令今天只能在服务器上手敲，无统一触发入口、无实时日志回流、无权限与审计。
2. **fleetent 自管理双源未调和**：fleetent 的「Agent 管理」「Skill 管理」是 DB-first 即时管理，askit 是 spec-first 编译管理；缺少「双层来源 + 覆盖回流」模型时，spec 与 DB 谁说了算无法表达，受管对象的应急 UI 改动无处回流。
3. **askit 无法落库 fleetent**：askit 今天只能编译到文件型平台（openclaw / claude / codex / hermes），无法把受管 agent / skill 编译进 fleetent 自身的 agent_store / skills 并享受版本化、跨环境晋升与覆盖回流。
4. **来源切换会丢历史**：临管对象转受管、或 deploy 命中同名对象时，若重建对象则历史 trace 与绑定断裂。

本 change 提供 askit 编排控制台的**控制面**（触发、参数表单、日志流、结果展示、权限与审计），并补齐 fleetent 自管理的双层来源 + 覆盖回流模型与 fleetent 侧幂等 apply API。**职责边界**：askit 的编译 / 校验 / 部署 / 覆盖回流 / 迁移等实际语义与产物正确性归 ai-skills-toolkit 外部工具域，本 change 不重复定义，仅以系列为单位编排调用并观察其行为。

## What Changes

**ADDED**

- `askit-console-api`：八系列分组的控制面——① 作者 / 脚手架（`init-repo` / `new-agent` / `new-skill` / `init-from-excel`）；② 构建与校验（`build` / `lint` / `check` / `audit` / `catalog export`，作为发布前闸门）；③ 部署（`deploy --target {fleetent|openclaw|claude|codex|hermes}` + `provision`，含 `--dry-run` 预演，部署前强制过 ② 的 check 绿灯）；④ 依赖（`install` 写 skills.lock）；⑤ 覆盖回流（`override sync/review/promote/discard/cleanup` + `decompile`）；⑥ 定时任务（`cron diff/install/remove/list`）；⑦ 环境与连接器（`doctor` / `env doctor` / `env-sync` / `mcp doctor` / `sync allowlist`，红黄绿 + 脱敏）；⑧ 迁移（`migrate-*`，默认 dry-run）。运行模型：每次系列操作 = 一个异步任务，实时流式 stdout/stderr + 历史，写审计，同工作区写操作串行排队。权限矩阵 admin（触发写）/ viewer（只读诊断与列表）。
- `fleetent-self-managed-provenance`：fleetent 自管理双层来源 + 覆盖回流——受管（spec-owned）vs 临管（DB-only）徽章；受管对象 UI 改动 → override 标 drift → sync/review → promote 开 PR 或 discard 被 spec 还原；immutable 字段（如 identity / name）被 spec 还原；临管转受管 `decompile`，deploy 命中同名临管走 adopt 收编；identity = 稳定 agent_id，切换来源不重建对象，历史 trace 与绑定天然续上。
- `fleetent-apply-api`：fleetent 新增的**幂等 apply API**（POST，按 agent_id / name upsert）供 askit 的 fleetent deployer 调用，把编译结果落 agent_store、skills 投递共享目录触发 hot reload；spec 只拥有 agent 定义（`name` immutable / `system_prompt`·`allowed_tools`·`model` mutable），bindings 留运行态 deploy 不覆盖。fleetent 始终是自己 DB 的唯一写入者，askit 不耦合 fleetent 表结构。

## Capabilities

### New Capabilities

- `askit-console-api`
- `fleetent-self-managed-provenance`
- `fleetent-apply-api`

## Impact

- **代码**：
  - 新增：`askit_console_api.py`（`/admin/askit/*` 路由：按系列触发、任务日志流、历史、审计）、`askit_runner.py`（askit CLI 子进程封装：固定版本、参数白名单、stdout/stderr 流式捕获、退出码、脱敏过滤器）、`askit_task_store.py`（异步任务表 + 工作区串行队列）、`agent_apply_api.py`（agents 幂等 apply API + provenance 字段读写）。
  - 复用：`auth.require_role`（admin 触发写 / viewer 只读诊断与列表）、`auth` 的 2FA（高危系列：部署 / 迁移 / promote 二次确认 + 2FA）、`audit_log`（发起人 / 系列 / 命令 / 参数 / 退出码 / 产物·PR 链接全写审计）。
  - 修改：`server.py`（mount router、lifespan 启动工作区队列）、`agent_store.py`（加 provenance 标志位 + immutable 字段守卫 + adopt 收编，不重建对象 / 不动 bindings）、`skill_registry`（受管 skill 投递共享目录触发 hot reload）。
- **数据**：新增 `askit_tasks`（任务定义 + 状态 + 退出码 + 日志引用 + 工作区 + 环境）、`askit_task_logs`（流式 stdout/stderr 分片，或落文件 + 引用）、`askit_workspaces`（git-backed spec 工作副本按 env：dev/test/pre/prod + fleetent endpoint）表；`agents` 表加 `provenance`（`spec_owned` / `db_only`）+ `drift`（override 待回流标志）列。新表 / 新列经 **Alembic**（不复制 `_init_db()` 建表模式），named params `:x`，路径可 monkeypatch。
- **跨域 follow-up（外部域，本 change 不实现）**：
  - **ai-skills-toolkit 需新增 fleetent target**（renderer + deployer）：把 spec 编译进 fleetent，且 deployer **不直接写 SQLite**，而是调本 change 的 `fleetent-apply-api`；属外部工具域工作，排期独立、跨仓依赖。
  - **fleetent 侧需新增 agents 批量 apply API**：即本 change 的 `fleetent-apply-api`（fleetent 内部交付，供外部 askit deployer 调用，是跨域协作的 fleetent 侧契约）。
  - 控制台以**子进程**调 askit CLI + **镜像内固定 askit 版本**，**不引库 API**（不把 ai-skills-toolkit 作为 Python 依赖引入），编排外部平台直接子进程、fleetent 自管理落库经 apply API 完成。
- **破坏性**：无新增破坏性。`agents` 加 provenance 列默认 `db_only`（存量临管），不改既有行为；deploy 命中同名临管走 adopt 翻转（UI 确认），不删不覆盖。

## Commit 切分建议

每个 commit 自包含、内部 TDD（测试先红 → 实现 → 绿）：

1. `feat(agent_store): provenance/drift columns + immutable guard + migration`（provenance 标志位与 immutable 字段守卫，1.x）
2. `feat(agent_apply_api): idempotent agents apply API (upsert by agent_id/name, no binding overwrite)`（2.x）
3. `feat(agent_store): adopt by name keeps agent_id; decompile/source switch no rebuild`（来源切换不重建对象，3.x）
4. `feat(askit_runner): askit CLI subprocess wrapper (pinned version, arg allowlist, stream, redaction)`（4.x）
5. `feat(askit_task_store): async task table + per-workspace serial queue + history`（5.x）
6. `feat(askit_console_api): series-grouped trigger / streaming logs / history endpoints`（6.x）
7. `feat(askit_console_api): deploy check-gate + dry-run + high-risk 2FA confirm`（7.x）
8. `feat(askit_console_api): override-flow review (diff P/D/S) + promote PR link in audit`（8.x）
9. `feat(askit_console_api): role guard (admin write / viewer read-only) + redacted diagnostics`（9.x）
