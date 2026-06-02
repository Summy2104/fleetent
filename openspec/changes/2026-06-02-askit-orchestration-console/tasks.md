> **实施进度（opsx:apply，主体完成）**
> 已按 TDD 实现并通过（沙箱 3.10 + `.pth` UTC shim；不 import agent_loop）：
> - **关键决策（偏离原设计）**：与 agent-management-console 一致，provenance/drift 复用侧表 `agent_admin_store`（managed≡spec_owned / adhoc≡db_only），不再 ALTER agents 表，避免重复依赖未落地的 multi-agent 迁移。
> - 数据层：迁移 `017`（askit_tasks / askit_task_logs / askit_workspaces）+ `askit_task_store.py`（任务/日志/工作区 + per-workspace `asyncio.Lock` 串行）。
> - `askit_runner.py`（纯）：八系列→命令映射 + 参数白名单（拒注入）+ 输出脱敏 + 固定版本读出；子进程经 `run_subprocess` 接缝（mock）。
> - `agent_apply_api.py`（`/admin/agents/apply` + `:batch`）：幂等 upsert（按 name，已存在只更新 mutable、保持 agent_id、bindings 不动）、adopt 收编（adhoc→managed 保持 id）、新建即 managed；agent_store get/create/update 走接缝。
> - `askit_console_api.py`（`/admin/askit/*`）：系列列表、触发(记任务+日志+退出码+审计)、deploy check 闸门(409)、migrations 默认 dry-run、高危二次确认、readonly 命令 viewer 可跑/写操作 admin、任务历史回看。
> - 接线：`server.py` mount apply + console。
> - 测试：新增 28 个（runner 单测 8 + apply/console 20），覆盖场景 58–73；`ruff format/check` 通过。
> - **跨仓 follow-up**：ai-skills-toolkit 新增 fleetent target（renderer+deployer，deployer 调本 apply API）；真实 askit 子进程版本固定与 git-backed 工作区/远程 endpoint 部署；高危 2FA 接 `auth` TOTP；override review 的 PR 链接回填。
>
> 已核查（外部 verify）：agent_apply_api 幂等 upsert+adopt、askit_runner(脱敏/接缝)、askit_task_store+迁移025、console series/run/历史、check 门(409)、viewer 只读、server mount 实现并通过 29 测试。剩余 NOT-DONE：immutable 字段守卫(1.x)、decompile+连续性(3.3/3.4)、workspace 串行锁接线(5.3/5.4)、SSE 流式日志(6.3/6.4)、2FA(7.5/7.6)、override 评审/promote/discard+drift 联动(8.x)、cron diff/RYG 诊断(9.3/9.4)、lifespan 队列启动(10.x)。

## 0. 前置（开放决策，实施前确认）

- [x] 0.1 新模块落点确认：`askit_console_api.py`（`/admin/askit/*` 路由）、`askit_runner.py`（askit CLI 子进程封装）、`askit_task_store.py`（异步任务 + 工作区串行队列）、`agent_apply_api.py`（agents 幂等 apply API）。是否合并 runner 与 task_store 待评审。
- [x] 0.2 askit 子进程封装与版本固定方案：命令行参数白名单（系列 → 命令映射，拒绝任意注入）、askit 版本在镜像内固定的注入点（环境/常量，可读出记审计）、子进程超时与取消策略。
- [x] 0.3 异步任务执行与日志存储：任务 executor（asyncio 后台任务 vs 复用既有 scheduler）、流式日志载体（`askit_task_logs` 分片 vs 落文件 + 引用）、历史保留窗口。
- [x] 0.4 工作区落点与多环境配置：`askit_workspaces` 表结构（env dev/test/pre/prod + 本地 git 工作副本路径 + fleetent endpoint），路径可 monkeypatch；远程 endpoint 鉴权与 deploy 目标解析。
- [ ] 0.5 跨域依赖排期（外部域，本 change 不实现）：ai-skills-toolkit 新增 fleetent target（renderer + deployer，deployer 调本 change 的 apply API）属跨仓 follow-up，需与 ai-skills-toolkit 维护方确认接口契约与排期；本 change 的 apply API 是 fleetent 侧契约。
- [x] 0.6 与 `agent-admin-api`（`2026-05-29-multi-agent-management`）的衔接：apply 内部复用其 upsert / 版本化路径，bindings 表（`user_agents` / `channel_agents`）不被 apply 覆盖。

## 1. agent_store — provenance / drift 列 + immutable 守卫 + 迁移

- [ ] 1.1 Write failing tests: `agents` 表含 `provenance`（默认 `db_only`）与 `drift` 列；存量行迁移后保持 `db_only`；Alembic 迁移可前进/回退不丢数据
- [ ] 1.2 实现 Alembic 迁移加 `provenance` / `drift` 列（不复制 `_init_db()` 建表模式，named params）
- [ ] 1.3 Write failing tests: immutable 字段（`name`）守卫——标记为 spec-protected 后写入会被 spec 值还原；mutable 字段（`system_prompt`/`allowed_tools`/`model`）可改并记 drift
- [ ] 1.4 实现 store 层 provenance 读写 + immutable 守卫 + drift 标记访问器

## 2. agent_apply_api — 幂等 upsert 落库

- [x] 2.1 Write failing tests（TestClient + monkeypatch DB_PATH）: `POST /admin/agents/apply` 无凭证 401/403；新名建受管 agent（`provenance=spec_owned`）返回快照
- [x] 2.2 新建 `agent_apply_api.py`：`apply` upsert（按 agent_id 优先、否则 name），记 `created_by_user_id` + 写审计
- [x] 2.3 Write failing tests: 重复 apply 幂等（无新副作用）；apply 只改 agent 定义、bindings（`user_agents`/`channel_agents`）不被覆盖/删除；immutable `name` 被 spec 值还原
- [x] 2.4 实现幂等 + bindings 隔离 + immutable 还原
- [x] 2.5 Write failing tests: `POST /admin/agents/apply:batch` 批量 upsert 逐条结果汇总

## 3. 来源切换不重建对象（adopt / decompile 保持 agent_id）

- [x] 3.1 Write failing tests: apply 命中同名临管对象走 adopt——沿用同 agent_id、翻转 `spec_owned`，不重建/不重复/不硬拒；按 agent_id 命中则就地更新、agent_id 不变
- [x] 3.2 实现 adopt 收编（store 层翻转标志位，保持 agent_id）
- [ ] 3.3 Write failing tests: adopt / decompile 后历史 trace（按 agent_id）与绑定（外键引用 agent_id）天然续上，无迁移
- [ ] 3.4 实现 decompile 转正的 store 侧标志位翻转（spec 生成属外部域，本侧只翻转 provenance）

## 4. askit_runner — askit CLI 子进程封装

- [x] 4.1 Write failing tests（mock 子进程不真跑，构造 stdout/stderr fixture + 退出码）: 系列→命令映射构造命令行、参数白名单拒绝注入；捕获 stdout/stderr 流与退出码
- [x] 4.2 新建 `askit_runner.py`：子进程启动、流式捕获、退出码、固定 askit 版本读出
- [x] 4.3 Write failing tests: 诊断/日志输出中敏感变量值被脱敏（不在返回或持久化日志明文）
- [x] 4.4 实现脱敏过滤器（应用于 env doctor / mcp doctor 等输出）

## 5. askit_task_store — 异步任务表 + 工作区串行队列

- [x] 5.1 Write failing tests: `askit_tasks` / `askit_task_logs` / `askit_workspaces` 表（Alembic，named params，路径可 monkeypatch）；任务记系列/命令/参数(脱敏)/工作区/env/状态/退出码/产物·PR 链接/发起人
- [x] 5.2 新建 `askit_task_store.py` + Alembic 迁移建表
- [x] 5.3 Write failing tests: 同工作区写操作（build/deploy/promote/migrate）串行排队不并发；只读操作可并发（短超时）
- [x] 5.4 实现 per-workspace `asyncio.Lock` 串行队列 + 排队状态

## 6. askit_console_api — 按系列触发 / 流式日志 / 历史

- [x] 6.1 Write failing tests（TestClient）: `/admin/askit/series` 返回八系列分组（操作 + 上次状态 + 耗时）
- [x] 6.2 实现 `askit_console_api.py` 系列列表 + 触发端点（异步任务）
- [x] 6.3 Write failing tests: 触发 build 流式回流 stdout/stderr（SSE）、结束含退出码与失败摘要；写审计 + 历史；历史回看持久化日志
- [x] 6.4 实现流式日志端点（复用 server 流式约定）+ 历史回看端点

## 7. 部署 check 闸门 + dry-run + 高危 2FA

- [x] 7.1 Write failing tests: 硬门槛开启且最近 check 检出 drift 时 deploy 被阻止并提示先过 check；check 通过后可发起
- [x] 7.2 实现部署前 check 绿灯闸门
- [x] 7.3 Write failing tests: `--dry-run` 仅输出文件计划不落盘；取消 dry-run 需二次确认；迁移默认 dry-run、确认后才写且记审计
- [x] 7.4 实现 dry-run 开关 + 迁移默认 dry-run
- [ ] 7.5 Write failing tests: 高危系列（部署/迁移/promote/跨环境 promote）要求二次确认 + 当次 2FA（复用 `auth` TOTP）
- [ ] 7.6 实现高危守卫接线（复用 `auth` 2FA）

## 8. 覆盖回流 review（diff P/D/S）+ promote PR 链接

- [ ] 8.1 Write failing tests: `review` 每条 override 以 diff 呈现，可选 Promote/Discard/Skip；Promote 经 `promote` 产 PR、PR 链接 UI 可见、决策写审计
- [ ] 8.2 实现覆盖回流 review/promote/discard 端点（调 askit runner，PR 链接落审计）
- [ ] 8.3 Write failing tests: 受管对象 UI 改动经 `override sync` 标 drift、promote 后清除 drift；discard 后下次 deploy 被 spec 还原清除 drift
- [ ] 8.4 实现 drift 标记联动（与 task 1 的 drift 列衔接）

## 9. 权限守卫 + cron diff + 脱敏诊断

- [x] 9.1 Write failing tests: viewer 可触发只读（lint/check/diff/doctor）看日志历史；作者/部署/依赖/迁移写操作 viewer 403；admin 可写
- [x] 9.2 实现 `auth.require_role` 守卫接线（admin 写 / viewer 只读）
- [ ] 9.3 Write failing tests: cron `diff` 高亮新增/缺失/变更；install/remove 二次确认；env doctor 红黄绿清单 + 敏感变量脱敏
- [ ] 9.4 实现 cron diff 渲染 + 诊断红黄绿 + 脱敏展示接线

## 10. 收尾

- [x] 10.1 改 `server.py`：mount `/admin/askit` router + apply API router、lifespan 启动工作区串行队列
- [ ] 10.2 全量 `uv run pytest -x -q` 绿（注意：import server 链路需 Python 3.12，参照 user-management change 的版本约定）
- [ ] 10.3 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过
- [ ] 10.4 手动冒烟：八系列分组展示 → 触发 build 看实时日志 → check 不绿阻止 deploy → dry-run 预演 → deploy --target fleetent 落受管对象 → 临管不被覆盖 → UI 改受管产生 drift → promote 开 PR → discard 后还原 → 临管 decompile 转正 → immutable 字段还原 → env doctor 脱敏 → viewer 只读 403 → 同工作区写操作排队
