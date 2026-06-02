# Design — askit 编排控制台 + fleetent 自管理（双层来源 / 覆盖回流）

## a+b 混合集成模型

fleetent 与 askit 的集成是 **方案 a + b 混合**（待决问题已定），fleetent 同时扮演两个角色，两角色共用同一个控制台：

- **角色 a — 跨 runtime 舰队的中央控制面**：用 askit 编排 openclaw / claude / codex / hermes 等**外部平台项目**。这些目标是文件型平台，askit deploy 直接写它们的配置文件。控制台只负责触发、看日志、审计。
- **角色 b — askit 的受管 target**：fleetent **自身**的 agent / skill 也可 spec-as-code 化，由 `deploy --target fleetent` 编译写入本平台的 agent_store / skills，享受版本化、跨环境晋升与覆盖回流。

放弃纯 (c)「内嵌 askit 子集」（重复造轮子、与上游分叉）。`lint` / `audit` / `check`(drift) 等无状态校验器 v1.0 一律走控制台调 askit，不内联；内联与否留 v1.1 评估。

```
                         ┌──────────────────────────────┐
   admin / viewer  ────► │  askit 编排控制台（platform）  │
                         │  八系列分组卡片 + 日志 + 审计   │
                         └───────────────┬──────────────┘
                                         │ 子进程（固定 askit 版本）
                                         ▼
                              ┌──────────────────────┐
                              │  askit CLI（外部域）    │
                              └─────┬────────────┬─────┘
            外部平台（角色 a）        │            │   fleetent（角色 b）
   ┌──────────────────────────┐◄───┘            └───►┌────────────────────────┐
   │ openclaw / claude / ...  │  直接写配置文件        │ fleetent-apply-api      │
   │ 文件型配置产物            │                       │ POST upsert → agent_store│
   └──────────────────────────┘                       └────────────────────────┘
```

## 与 DB-first「Agent / Skill 管理」的关系（关键）

fleetent 的「Agent 管理」「Skill 管理」（`2026-05-29-multi-agent-management`、`2026-06-02-skill-management`）是 **DB-first 即时管理**：UI 改了立即生效，适合快速实验。askit 是 **spec-first 编译管理**：以 git 里的 YAML spec / SKILL.md 为源，编译落库，适合生产、需版本化与跨环境晋升的对象。

二者不构成双源冲突，由「双层来源 + 覆盖回流」模型调和：

- 每个 agent / skill 有一个**来源归属**（provenance）标志位，写在同一行上：
  - **受管（`spec_owned`）**：源是 git spec，经 `deploy --target fleetent` 落库；列表打「受管」徽章。
  - **临管（`db_only`）**：直接在管理 UI 即时创建，git 不追踪；列表打「临管」徽章。
- **受管对象的 UI 改动 = 运行时覆盖**：UI 仍可应急改受管对象，改动经 `override sync` 捕获为 override，列表标 **drift**。drift 不阻止运行（应急即时生效），只是提醒「与 spec 不一致、待回流」。
- **回流闭环**：admin 在「覆盖回流」系列以 diff 审阅，逐条 Promote / Discard / Skip：
  - `promote` → 回流到 spec 并开 PR（转正为正式来源），合入后下次 deploy 即一致，drift 清除。
  - `discard` → 丢弃 override，下次 `deploy --target fleetent` 被 spec 内容覆盖还原，drift 清除。
- **immutable 字段**：标为 immutable 的字段（对齐 askit IMMUTABLE_FILES，fleetent 侧为 `name` = identity）UI 改了也会在下次 deploy 被 spec 还原；UI 在改动时即提示「该字段受 spec 保护，将于部署时还原」。

## fleetent-apply-api 幂等 upsert 契约

askit 的 fleetent deployer **不直接写 SQLite**，而是把编译结果经 fleetent 新增的幂等 apply API 交给 fleetent 自己落库——askit 不耦合 fleetent 表结构、跨机可用、fleetent 始终是自己 DB 的唯一写入者。

- **入口**：`POST /admin/agents/apply`（admin 鉴权；deployer 用服务 key），body 为编译后的 agent 定义。批量为 `POST /admin/agents/apply:batch`。
- **upsert 键**：优先 `agent_id`，无则按 `name` 匹配既有行。
  - 命中既有**受管**对象 → upsert 其 mutable 字段，`name` 被强制为 spec 值（immutable 还原），翻转 / 保持 `provenance=spec_owned`，清除已 discard 的 drift。
  - 命中既有**临管**对象（同名）→ 走 **adopt 收编**：沿用同 `agent_id`、翻转为 `spec_owned`（UI 确认），**不重建对象、不删除**。
  - 无命中 → 新建受管对象。
- **字段所有权**：spec 只拥有 **agent 定义**——`name`（immutable）、`system_prompt` / `allowed_tools` / `model`（mutable，UI 改记 override）。**bindings（user / channel / 默认）留运行态，apply 不覆盖、不删除**（与 `agent-admin-api` 的 `user_agents` / `channel_agents` 解耦）。
- **幂等**：同一 spec 重复 apply 结果一致（无新副作用，除审计与版本时间戳）；与 `agent-admin-api` 的 PATCH 版本化衔接——apply 内部走同一 upsert 落 agent_store，受管来源的 apply 记 `created_by_user_id`（发起 deploy 的 admin）。
- **skills 投递**：受管 skill 不走 apply API，而是投递到共享 skills 目录后触发 hot reload（`skill_registry` 重扫）。

## 来源切换边界（decompile / adopt 保持 agent_id）

核心原则：**identity = 稳定的 agent_id，「受管 / 临管」只是同一行上的标志位，切换来源不重建对象**。

- **临管转受管（decompile）**：对临管对象执行 `decompile` 反编译为 spec、纳入 git；之后即变受管。agent_id 不变。
- **adopt 收编**：`deploy --target fleetent` 命中同名临管对象时，沿用同 agent_id、翻转为受管（UI 确认），不覆盖、不硬拒。
- 因 agent_id 不变，历史 trace（按 agent_id 查 `traces`）与绑定（`user_agents` / `channel_agents` 外键引用 agent_id）天然续上，无需迁移。

## 子进程调用形态与固定版本

- 控制台以**子进程调 askit CLI**，**不引库 API**（不把 ai-skills-toolkit 作为 Python 依赖）。`askit_runner.py` 封装：构造命令行（系列 → 命令 + 受控参数白名单，拒绝任意 shell 注入）、设工作目录为目标工作区、捕获 stdout/stderr 流、读退出码、对输出做敏感变量脱敏。
- **固定 askit 版本**：版本在**镜像内固定**（运行时不联网升级），保证编排可复现；版本号记入任务审计。
- 编排外部平台（角色 a）直接子进程产出文件型配置；fleetent 自管理（角色 b）的「落库」经 apply API 完成（deployer 在 askit 侧调，控制台只触发）。

## 工作区与多环境 / 远程 endpoint

- 控制台持 **git-backed 的 spec 工作副本，按环境分（dev / test / pre / prod）**，对齐 askit 分支 env 检测。每个工作区记录其 env、本地路径（可 monkeypatch）、关联的 fleetent endpoint。
- `deploy` 指向**某环境的 fleetent endpoint**（可远程，不要求与 spec 仓库同机）；spec 仓库（SoT）与运行 DB 经 endpoint 解耦连接。
- **跨环境 promote 需 admin + 2FA**（复用高危二次确认）；deploy / 迁移同属高危系列。

## 异步任务 + 流式日志 + 串行排队

- 每次系列操作 = 一个**异步任务**（`askit_tasks` 行）：记系列、命令、参数（脱敏后）、工作区、env、状态（queued / running / done / failed）、退出码、产物 / PR 链接、发起人、时间。
- **流式日志**：子进程 stdout/stderr 实时回流到 UI（SSE，复用 server 既有流式约定），并持久化（`askit_task_logs` 分片或落文件 + 引用）供历史回看；结束展示退出码与失败摘要。
- **串行排队**：同一工作区的**写操作**（build / deploy / override promote / migrate）串行排队，避免并发踩踏；按工作区一把 `asyncio.Lock`（仿 `session_mgr` per-session lock 思路）。只读操作（lint / check / diff / doctor）可并发。

## 权限与审计

- 复用 `auth.require_role`：viewer 可触发**只读类**操作（lint / check / diff / 各类 doctor）、看日志与历史；作者 / 部署 / 依赖 / 迁移等写操作仅 admin（viewer 按钮不可见或返回 403）。
- **高危系列**（部署 / 迁移 / promote / 跨环境 promote）要求二次确认 + 当次 2FA 校验（复用 `auth` 的 TOTP 守卫）。
- **审计**：每次操作落 `audit_log` 一条——发起人、系列、命令、参数（脱敏）、退出码、产物 / PR 链接全写；deploy 命中 adopt、override promote / discard 决策、immutable 还原均记录。

## 测试隔离（遵循 CLAUDE.md）

- **mock askit 子进程不真跑**：patch `askit_runner` 的子进程启动点，注入构造的 stdout/stderr fixture 与退出码；单元测试不真实调 askit CLI、不真实联网、不真改 git。
- **流式日志**：以构造的分片序列断言 UI 收到顺序与持久化内容，不依赖真实子进程时序。
- **apply API**：用 FastAPI TestClient + monkeypatch `DB_PATH` 到 `tmp_path`；断言 upsert 幂等、adopt 保持 agent_id、bindings 不被覆盖、immutable 还原、provenance / drift 标志位变化。
- **工作区路径**：`askit_workspaces` 路径与 git 工作副本路径可 monkeypatch 到 `tmp_path`，绝不触碰 `data/` 与真实仓库。
- **串行队列**：构造两个同工作区写任务，断言后者排队不并发（短超时，避免测试阻塞）。
- **权限 / 2FA / 脱敏**：TestClient 断言 viewer 写 403、高危未过 2FA 拒绝、诊断输出中敏感变量值已脱敏（不在响应或持久化日志中明文）。
