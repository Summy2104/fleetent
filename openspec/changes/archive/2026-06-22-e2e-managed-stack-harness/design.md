## Context

- 现有 e2e helper（**复用基**）：`tests/e2e/_entrypoint_smoke.py` 的 `repo_root()` / `child_env(extra=)` / `reserve_port()` / `running_process(argv, env, cwd)`(ctx mgr) / `wait_for_http_ready(proc, url)`；`tests/integration/_migration_template.py::apply_migrations(db_path)`（迁移好的临时管理库）。
- platform 起法（boot smoke 已示范）：`python -m uvicorn fleetent.server:app --host 127.0.0.1 --port <p>`，env 带 `DATABASE_URL`/`FLEETENT_HOME`。
- node 起法：`python -m fleetent node start`（+ 先 `python -m fleetent admin node register` provision）。
- agent 由 node spawn（`fleetent agent run`，loopback 端口，node 管）。
- model client 用 `base_url`（resolver.py:44/72）+ protocol `openai_chat`（D3 实证）。
- managed 起栈姿势/坑见 [[managed-stack-live-e2e]]（dev master key、双认证、forwarder host override 等）+ make dev-stack 目标。

## Goals / Non-Goals

**Goals:**
- 可复用多进程栈 fixture（platform+node+agent 真进程，隔离、干净 teardown）。
- 确定性 LLM stub（OpenAI 兼容 SSE，无云）。
- E2E-1 managed chat ingress 端到端流式 + E2E-2 node 生命周期。

**Non-Goals:**
- IM/审批/身份/KB/记忆等 e2e（后续 change 复用 harness）；e2e 进 per-merge 门禁；改 src 产品行为。

## Decisions

- **D1 · H1 = 扩展 _entrypoint_smoke 成 `managed_stack` fixture**：apply_migrations 起临时管理库 → 生成/写 dev `FLEETENT_SECRET_KEY` → reserve 端口 → 起 platform uvicorn（wait /health）→ `fleetent admin node register`(provision, 拿/落 service key, 仿 scripts/dev_node_provision) → 起 `fleetent node start`（env: FLEETENT_HOME/DATABASE_URL/NODE_PLATFORM_URL/FLEETENT_SECRET_KEY/FLEETENT_FORWARDER_HOST_OVERRIDE=127.0.0.1）→ node spawn agent → wait agent /health。yield 句柄（platform_url、admin creds、agent_name）；teardown 反序停、bulkhead。
- **D2 · H2 = 确定性 LLM stub**：tests/e2e 内起一个本地 **OpenAI 兼容 `/v1/chat/completions` SSE** 小服务（确定性 echo/固定回复），reserve 端口；测试 agent 的 model target 配 `base_url=http://127.0.0.1:<stub>/v1`、`protocol=openai_chat`、`api_key_env` 指一个 env 占位。agent 进程经此不触真 LLM。
- **D3 · H8 复用** `apply_migrations`；agent 侧 per-agent 库走嵌入式迁移（agent boot 自建）。
- **D4 · 测试用一个最小 agent**（仿 demobot：openai_chat 指 stub、少量 allowed_tools），materialize/或预置 agent.yaml。
- **D5 · 慢 lane**：`make test-e2e` 跑这批；不进 `make test-pr`。CI 配置（slow/nightly）本切片可注明、不强求接（与现状 e2e 不进门禁一致）。

## Risks / Trade-offs

- **多进程起栈的脆弱性**：端口竞争、启动时序（platform 先 ready 才能 provision、node 才能 spawn agent）、teardown 残留进程。靠 `wait_for_http_ready` 串行就绪 + 反序 bulkhead 停 + reserve_port 防撞。CI 上比单进程慢且更易 flaky——故进 slow lane、不进 per-merge。
- **dev master key/服务 key 衔接**（D3 教训）：provision 必须在 `FLEETENT_SECRET_KEY` 在场时跑（否则 secret_store.set 静默失败、ingress 503）。harness 必须先设 key 再 provision。
- **stub LLM 协议保真**：stub 要够像 openai_chat SSE（chunk 格式、`data: [DONE]`），否则 agent 解析失败。最小实现先覆盖纯文本流式回复；工具调用等后续 e2e 需要时再扩 stub。
- **forwarder host override**：单机 e2e 下平台拨 node forwarder 要 `FLEETENT_FORWARDER_HOST_OVERRIDE=127.0.0.1`（D3 落地的 dev override），否则 `<node>.internal` 不解析。
- **flaky/慢**：多进程 e2e 天然慢、偶发 flaky；slow lane 容忍，但 harness 要把就绪/超时做稳，避免污染。
