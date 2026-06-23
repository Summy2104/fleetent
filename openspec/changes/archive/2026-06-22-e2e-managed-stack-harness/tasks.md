## 1. H2 确定性 LLM stub

- [x] 1.1 **测试（红）**：tests/e2e 内确定性 LLM stub——本地 OpenAI 兼容 `/v1/chat/completions` SSE 服务，给定 prompt 返固定流式回复（chunk + `data: [DONE]`）。先写一个直接打 stub 的最小断言（拿到确定性流）。先跑见红。
- [x] 1.2 **实现（绿）**：stub 服务 + reserve_port 起停 fixture。跑见绿。

## 2. H1 多进程栈 fixture（扩展 _entrypoint_smoke）

- [x] 2.1 **测试（红）**：`managed_stack` fixture 起 platform+node+agent 并都 /health 健康（隔离 home + dev FLEETENT_SECRET_KEY + 端口 + FORWARDER_HOST_OVERRIDE=127.0.0.1）；yield 句柄；teardown 干净停无残留。先写一个"起栈→三方就绪→停"的最小测试。先跑见红。
- [x] 2.2 **实现（绿）**：扩展 `_entrypoint_smoke` helper：apply_migrations 起库 → 写 dev key → 起 platform(wait /health) → `python -m fleetent admin node register`(provision, ★必须在 key 在场后) → `python -m fleetent node start`(env 齐) → node spawn agent(指向 H2 stub base_url 的最小 agent) → wait agent /health。反序 bulkhead teardown。跑见绿。

## 3. E2E-1 managed chat ingress

- [x] 3.1 **测试（红）**：用 managed_stack：admin 登录(Session) → `POST /admin/agents/{name}/chat` → 断言收到**端到端非空流式回复**（来自 H2 stub，经 platform→node forwarder→agent）。先跑见红。
- [x] 3.2 **绿**：让它过（harness + stub 就绪即应绿；若红则定位是栈/鉴权/forwarder/流式哪段——这正是 e2e 要抓的整合 bug）。

## 4. E2E-2 node 生命周期

- [x] 4.1 **测试（红）**：用 managed_stack（或更细粒度）：node 注册 → 拉 desired-state（含某 agent）→ spawn agent 子进程 → agent loopback `/health` 健康；可加 node 上报 status 含该 agent。先跑见红。
- [x] 4.2 **绿**：让它过。

## 5. 收尾 + lane

- [x] 5.1 `make test-e2e` 跑这批（含新 harness/stub/2 测试）；确认**不在** `make test-pr` 里（slow lane，沿用现状 e2e 不进 PR 门禁）。
- [x] 5.2 `make test-pr` 仍全绿（本 change 纯 test 侧、不碰 src，对照 main 基线无新增失败）；覆盖率门禁不受影响（e2e 不计 unit 覆盖）。
- [x] 5.3 边界：纯 tests/e2e + 复用 _migration_template；不改 src 产品代码（agent 经既有 model base_url 配置指 stub）。如确需 src 改动（如测试 hook），最小化并说明。
- [x] 5.4 （注明）CI slow/nightly lane 接入：本切片把测试就位 + `make test-e2e` 可跑；接进 CI 定时/手动 pipeline 可同切片或紧随（与现状 e2e 不进 per-merge 一致）。
