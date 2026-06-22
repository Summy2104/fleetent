## Why

e2e 覆盖极薄——只有 boot 烟测（platform/agent /health、sandbox、slack helper）。**真实多进程 managed 拓扑（platform 进程 + node 进程 + 每 agent 进程，经 forwarder/HTTP 通信）的完整流程零 e2e 覆盖**。unit/integration 全是单进程 + mock LLM/TestClient，**结构上碰不到这层**——而本会话刚落地的车道 D 6 切片 + 管理栈整合恰恰活在这层，"各组件绿、整合炸"的集成 bug（D3 当初手动逮出的 streaming + secret-key）就藏这儿。

本切片（e2e 批量补的**地基 Change A**）建**可复用多进程栈 harness** + 第一批两条 P0 e2e，证明 harness 可用；后续 e2e（IM/审批、身份流、KB、记忆…）各自复用同一 harness、可并行补。

## What Changes

- **H1 多进程栈 harness**：**扩展现有** `tests/e2e/_entrypoint_smoke.py`（`running_process`/`child_env`/`reserve_port`/`wait_for_http_ready`）成一个**起整栈 fixture**：隔离 tmp home + dev master key（`FLEETENT_SECRET_KEY`）+ 端口分配 → 起 platform(uvicorn) → node-provision(register, 落 service key) → node start → node spawn agent；teardown 干净停。
- **H2 确定性 LLM stub**：本地 **OpenAI 兼容 SSE 服务**（确定性回复、无云依赖），agent 的 model target `base_url` 指它（protocol `openai_chat`）——让独立 agent 进程不调真 LLM、可断言固定回复。
- **H8 复用**：`tests/integration/_migration_template.py::apply_migrations`（迁移好的临时管理库）。
- **conftest**：tests/e2e 的栈/stub fixtures。
- **E2E-1 · managed chat ingress**：起栈 → admin 登录(Session) → `POST /admin/agents/{name}/chat` → 断言**端到端流式回复**（platform→node forwarder→agent→stub LLM→流回 operator）。
- **E2E-2 · node 生命周期**：node 注册 → 拉 desired-state → spawn agent → agent `/health` healthy（真 subprocess 启停）。

### 不在本切片（后续 change 复用 harness）
- IM 入站+审批 e2e（加 stub IM）、身份流 e2e（mock OIDC+stub IM）、KB/记忆/MCP/多租户/cron e2e。
- e2e 进 per-merge 门禁（e2e 慢、跑独立 slow/nightly lane，沿用现状不进 PR gate）。

## Capabilities

### New Capabilities
- `e2e-managed-stack-coverage`: 提供可复用多进程栈 harness（起 platform+node+agent 真进程 + 确定性 LLM stub + 隔离库）；用它覆盖 **managed chat ingress 端到端流式** + **node 生命周期（注册→desired-state→spawn→health）** 两条 P0 路径；e2e 跑独立 slow lane、不进 per-merge 门禁。

## Impact

- **owning packages**：`tests/e2e`（harness 扩展 + stub LLM + conftest + 两条 e2e）；复用 `tests/integration/_migration_template`
- **public API surface**：无（纯测试侧；**不改 src 产品行为**——agent 经既有 model `base_url` 配置指向 stub，无需改 src）
- **owned tables**：无（测试用隔离临时库）
- **config namespace**：无（测试经隔离 FLEETENT_HOME + env 起栈）
- **cross-module dependencies**：测试编排 platform/node/agent 三进程；不引入 src 跨模块依赖
- **migration / shim**：无（复用 apply_migrations）
- **CI**：新增/扩展 `make test-e2e`（或 e2e 子目标）跑这批；进 **slow/nightly lane**，**不进 per-merge `make test-pr`**（e2e 慢、需起多进程；沿用 AGENTS.md "e2e 默认不进 PR 门禁"）
- 风险低（test-only）；但 harness（起栈/端口/进程生命周期/teardown）是实在的脚手架活，本切片用 2 条 P0 测试压实其设计
