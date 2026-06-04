# Platform/Agent 拆分 — Apply 决策记录

> 自主执行运行（2026-06-04 起）。按依赖顺序串行 apply 4 个 change，遇到问题依代码与上下文自行解决，
> 本文档记录每个问题、判断依据与决策，供事后统一审核。

## 范围与顺序

强制拓扑全序（依赖链为单链，无并行空间）：

1. **per-agent-im-access** — 无依赖，地基（IM 访问控制随 agent 走、本地存）
2. **agent-runtime-cli** — Depends on per-agent-im-access（standalone agent 自带访问控制）
3. **platform-control-plane** — Depends on agent-runtime-cli（平台瘦身，执行路径须先移出）
4. **platform-agent-lifecycle** — Depends on 前三个（平台落盘 home + 启停 agent 进程）

基线分支：`chore/agent-platform-split-openspec`（唯一含这 4 个 proposal 的分支）。
工作分支：`apply/platform-agent-split`。

## 执行约定

- 每 task 严格 TDD Hard Gate：写测试→看红→写实现→看绿→（可选）refactor。
- Commit 规范：`type(scope): desc`，type ∈ feat/fix/refactor/test/docs/chore。
- ruff 只格式化本次改动的文件，不跑全仓。
- 新单测进 `tests/unit/`，多模块/DB/HTTP 进 `tests/integration/`。

---

## 决策日志

<!-- 按 change 分节，逐条记录：问题 / 上下文 / 决策 / 影响 -->

### Change 1: per-agent-im-access

**D1.1 — 审批存储用 JSON，不用 SQLite。**
- 问题：design.md Open Question 留了「approval store: json vs 本地 SQLite」。
- 依据：design 自己倾向 json（"json is simplest for a single self-contained agent"）；更关键的是 CLAUDE.md 禁止扩散 `sqlite3.connect`/`_init_db()`、schema 生命周期归 Alembic。但这些规则约束的是**平台 DB**；本审批存储是 **agent home 本地文件状态**，不进平台库。用 JSON 文件（`<home>/data/im_approvals.json`，路径可注入）既符合 design，又彻底绕开 SQLite-spread/Alembic 约束。
- 决策：agent-local approval store = JSON 文件，路径参数可注入，原子写（`.tmp → rename`，复用 session_mgr 模式）。

**D1.2 — access 配置作为 `AgentFile.access` 块。**
- 在 `agent_config.py` 新增 `AgentAccess` pydantic 模型，挂到 `AgentFile.access`。字段 `allow_channels: list[str]`、`allow_users: list[str]`、`require_approval: bool = True`。
- 缺省（无 `access` 块）→ `default_factory` 给出 default-closed 实例（空 allow + require_approval=True），天然满足「无 block → 安全默认：不隐式放行、需审批」。
- inline-secret 校验对 access 块无影响（不含密钥字段），但确保 `_reject_inline_secrets` 不因新块报错。

**D1.3 — 本地访问逻辑放在 `fleetent/im_gateway/access.py`（runtime 侧），不放 `fleetent.platform.im_gateway_management`。**
- 问题：proposal/CLAUDE.md 文字说「gates now on the unified `im` module」，但当前 `im` = `fleetent.platform.im_gateway_management`，是平台 DB 后端、且在 change 3 会从 runtime 移除。把「本地、零平台 DB」的 gate 放进平台模块自相矛盾。
- 决策：新建 runtime 侧模块 `im_gateway/access.py`，承载：本地审批存储 + 本地身份解析 + 本地 channel/user gate。`normalizer.route` 改为从它取 gate，移除运行路径上对 `fleetent.platform.im_gateway_management` 的依赖。这与「agent 自包含、平台后移」方向一致，是对字面措辞的有据偏离。

**D1.4 — 运行时身份 = 平台原生 IM user id，零平台 user_store。**
- adapters（slack/telegram）当前调 `im.get_or_create()` 拿内部 `user.id` 作 `msg.user_id`。
- 决策：改为本地解析，`msg.user_id` = 平台原生 id（如 Slack `U123`）。理由：(1) spec 明确「用平台原生 id 作身份」；(2) `allow_users` 由作者写在 agent.yaml，用原生 id 最直观匹配；(3) session_id 本就用原生 id 派生，改动面小。
- 影响：memory namespace / trace key / 审批 approver 的 user_id 从内部 id 变为原生 id——对自包含 agent 可接受，记录在案。受影响测试在 4.1 迁移。

**D1.5 — route() 先解析 agent，再做本地 gate。**
- 现状 gate（channel/user）在 agent 解析之前；新设计 gate 是 per-agent 的，必须先有 agent。
- 决策：把 agent 解析上移到 gate 之前（解析本身零 DB，文件索引）。agent 解析为 None（bare run，无任何 agent 配置）时，用 `AgentAccess()` default-closed 兜底（安全默认）。

**D1.6 — bare-run（无 agent 解析）也走 default-closed，是有意的破坏性变更。**
- 冲突：迁移时发现两个旧测试（`test_normalizer_sandbox::test_route_passes_sandbox_context_to_run`、`test_normalizer_skill_scoping::test_route_no_agent_does_not_narrow`）断言「无 agent 的 bare-run 能进 loop」——这正是 spec 明确要废除的「allowlist-off = allow-all」遗留行为。
- 判断：spec scenario 只测「agent 存在但无 access 块 → default-closed」，未直接测「完全无 agent」。但把 default-closed 延伸到「无 agent」是最安全、与「默认关闭」精神一致的选择；且 standalone agent runtime（change 2 目标）永远有 agent，bare-run 只出现在平台过渡路径，而该路径在 change 3 被整体移除。
- 决策：`agent is None → AgentAccess() → 阻断`（记 pending）。据此迁移两个旧测试：sandbox 测试改为绑定一个放行 u1、无 features 的 agent 来验证 sandbox 上下文透传；skill_scoping 的 no-agent 测试改为断言「无 agent → 被 default-closed 阻断、不进 loop」。

**D1.7 — 移除测旧平台 allowlist gate 的过时测试。**
- `tests/integration/test_normalizer_allowlist.py`（4 个）整体测的是 route() 调 owner-keyed `im_channel_allowlist`/user-store 的旧运行路径——该路径已从 route() 移除。
- `tests/unit/test_normalizer::test_route_threads_owner_to_allowlist` 测「owner 透传给 im.is_allowed」，同样过时。
- 决策：删除这些过时用例；其替代覆盖由新增的 `tests/integration/test_normalizer_local_access.py`（per-agent 本地 gate）承担。平台侧 `channel_allowlist` 模块本身保留（平台 authoring 仍用），仅运行路径不再调用。

**D1.8 — 全量 suite 又抓出 9 个被本 change 破坏的 IM/route 测试，一并迁移；3 个为预存基线失败，不在本 change 范围。**
- 全量 `pytest` 后 12 个失败。回到 base 分支 `chore/agent-platform-split-openspec` 复跑判定来源：
  - **预存基线失败（base 上也红，非本 change 引入，共 4 个）**：`tests/integration/test_single_agent_runtime.py` 3 个（单文件 home 模式 `paths.agent_file()` 路径与测试写入位置不一致）+ `tests/integration/test_install_script.py::test_missing_docker_warns_but_succeeds` 1 个（install.sh 在本机检测到 docker，断言「Docker not found」失配）。均与 per-agent-im-access 无关，**保持原状**，仅记录。
  - **最终全量 gate**：3115 passed，仅上述 4 个预存基线失败，本 change 零新增失败。
  - **本 change 引入（base 上绿）**：9 个 —— `test_im_adapter_owner`(1)、`test_normalizer_vision`(3)、`test_im_gateway`(2)、`test_integration`(2)。均因（a）default-closed gate 阻断了无 access 的 agent / bare-run，或（b）adapter 改用原生 id（不再 `user.id`）。按 4.1 同样手法迁移。
  - 其中 `test_im_gateway::test_route_channel_agent_takes_priority` 暴露一个真实点：旧测试 fake `get_agent_for_context` 返回的是 `agent_store.Agent`（无 `.access`），而生产路径只返回 `AgentFile`。迁移为返回带 `access` 的 `AgentFile`，与生产类型一致。

### Change 2: agent-runtime-cli

**D2.1 — 新建 `src/fleetent/runtime/agent_app.py` 承载 standalone agent runtime，不改 `server.py` 的 app/lifespan（任务 1.2 要求 `uvicorn fleetent.server:app` 继续可用）。**
- runtime 复用既有共享件（`agent_config`、`SlackSupervisor`、`session.manager`、`mcp_client`、sandbox enablement、`run_stream`），但自带一个**精简 boot + 小 ASGI app**，不挂任何 `/admin/*`、不 import `server.py`。

**D2.2 — boot 发布「单 agent 索引」。**
- `agent run <agent-id>` 解析 home = `FLEETENT_HOME/<agent-id>/`（`--home PATH` 可覆盖），`load_agent_file` 加载该 home 的 `agent.yaml`，发布一个 forced-default 单 agent 索引（新增 `agent_config.scan_home(agent_dir)`，复用既有 `_single_agent_index`）。这样路由只解析到这一个 agent，符合「自包含单 agent 进程」。

**D2.3 — IM 绑定：当前只起 slack（schema 里 `AgentConnectors` 仅有 `slack`）。**
- proposal 写「Slack/Telegram」，但 `agent.yaml` 的 `AgentConnectors` 模型目前只有 `slack` 字段，没有 per-agent telegram。故 runtime 通过 `SlackSupervisor.start(agent_name)` 起该 agent 的 slack 连接；per-agent telegram 不在 home schema 内，**暂不纳入**（owner-level telegram 仍由平台侧管理，且平台 IM 将在 change 3 移除）。记录此偏离。

**D2.4 — boot 的基础设施（sandbox 探测 / MCP 注册 / session 维护）走可注入开关 + 可 mock 的 seam，单测默认 `with_infra=False` + 注入 mock supervisor，避免触碰 docker/网络。**

**D2.5 — `--port` 才挂 HTTP。**
- `build_app(agent)` 构造只含 `/chat`(SSE，应用 home agent 的 system_prompt/allowed_tools/allowed_skills via `run_stream`)、`/ws`(复用 `tui.dispatch`)、`/health` 的小 app；无 `--port` 时根本不构造/不监听。auth 直接用 `user_store.authenticate`，不经由 `server.py` 的 `_authenticate`（避免平台依赖）。

**D2.6 — 闭环：无 server/IM 测试需迁移；3 个预存基线失败保持原状。**
- `server.py` 未改动，`uvicorn fleetent.server:app` 仍可用，全部 server/server_lifespan 测试通过——任务 4.1 无迁移工作量。
- `test_single_agent_runtime.py` 3 个仍红，是 change 1 已确认的预存基线失败（单文件 home 模式 `paths.agent_file()=config/agent.yaml` 与测试写 `tmp_path/agent.yaml` 位置不符）。它与 agent-runtime-cli 的 home 布局（`FLEETENT_HOME/<agent-id>/`，走新增 `scan_home`）正交，本 change 不触碰该路径，故**保持原状**，仅记录；4.3 判据为「不新增失败」，已满足。

### Change 3: platform-control-plane

**D3.1 — lifespan 精简范围（严格按 D1）。**
- 移除：sandbox 探测+orphan 清理、agent-use MCP（mcp.yaml 加载 / register_global_store_servers / start_health_monitor）、session 维护、IM（`_connector_manager.start_all_enabled` / `_slack_supervisor.start_from_index` / admin_api 的 start/stop connector seam）、webhook 源加载；shutdown 里对应的 connector/supervisor/mcp/session 收尾也一并移除。
- 保留：scan_skills、`agent_config.scan`（authoring/console 读取用）、load_plugins（console 列举用，无害）、cleanup_stale_approvals、builtin-admin seed、全部 admin 路由、`/health`、`/approvals`(+resolve)、平台 cron（monitoring + playground retention）、**admin 控制台 Chat playground seam**（按需执行、非 boot-time loop，属 console 工具，保留）。

**D3.2 — 仅移除 `/chat`、`/ws`、`/webhook/*` 三个执行路由（spec/任务只点名这三个）。`/approvals`/`/approvals/{id}/resolve`/`/health` 不在移除清单，保留。**

**D3.3 — `/health` 安全：`request.app.state.sandbox_mode` 用 `getattr(..., Mode.OFF)` 兜底，故移除 sandbox 探测后 health 仍 200（sandbox 显示 off）。**

**D3.4 — 测试迁移（3.1）：删除测「已移除端点」的用例，把 `/ws` 迁到 agent runtime。**
- 删除 `test_webhook_server.py`（平台 `/webhook` 整体移除、未迁到别处；签名逻辑仍由 `test_webhook_router.py` 单测覆盖）。
- 删除 `test_tui_ws_endpoint.py`，新建 `test_agent_runtime_ws.py`：`/ws` 行为迁到 `agent_app.build_app`，握手/ready/parse-error/auth 测试指向 agent runtime。
- `test_server.py` 删除全部 13 个 `/chat` 执行测试（平台 `/chat` 已移除；平台特有的 quota/scope/disabled-agent 门控随之消失，agent runtime 的 `/chat` 不复刻这些），保留 control-plane + lifespan(cron/plugins/monitoring) + agent-store seam 测试。
- `test_server_lifespan.py`(unit) 删除 mcp.yaml / sandbox 探测·健康·清理 的用例；(integration) 删除 `test_lifespan_starts_connectors_via_manager`（control-plane「不启 IM」由新 `test_platform_control_plane.py` 覆盖）。

**D3.5 — 顺带修复 change 2 的真实 bug：`agent_app.py` 的 `/ws`(及 `/chat`) 因 `from __future__ import annotations` + 函数内局部 import，FastAPI `get_type_hints()` 在建路由时无法解析 `WebSocket`/`ChatRequest` → 端点请求期 `NameError`、`/ws` 连接被 1008 关闭。change 2 的测试只断言「路由存在」未实际打请求，故漏掉。修复：把 `FastAPI`/`WebSocket`/`WebSocketDisconnect`/`StreamingResponse`/`user_store` 提升到模块级、`ChatRequest` 提到模块级；并补一个真正打 `/chat` 的功能测试 + 迁移后的 `/ws` 测试作回归护栏。这是「行为测试」抓 bug 的范例。

### Change 4: platform-agent-lifecycle

（待开始）
