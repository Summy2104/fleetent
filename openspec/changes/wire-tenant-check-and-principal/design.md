## Context

#4 Identity 端口落地：`identity.Principal{user_id, tenant_id}`、`agent_app._authenticate` / `_validate_tui_token` 产出 Principal、`loop.run` / `run_stream` 收 Principal。但收尾有缺口（已核实）：

- `agent_app._check_tenant(principal, agent_tenant)` 已定义，**全仓零调用**（`grep` 无调用点）。`/chat`、`/ws` 拿 Principal 后直接 run。
- `loop.py:676` 构造 sub-agent 的 `parent_principal=Principal(user_id=user_id, tenant_id="default")`——写死 default，违反 `identity-port`「继承」要求。
- `tui/dispatch.py` 的 `Connection` 存 `user_id: str`，`_stream_run` 传 `user_id=conn.user_id` 给 `run_stream`，丢掉 Principal。
- `tools/builtin_tools.py` 的 `invoke_agent` 调 `agent_loop.run(...)` 不传 `principal`。

物理隔离（`tenant-scoped-db-routing`：按 agent 归属主体路由、进程够不到别主体库）已成立；本 change 补的是其上的**访问准入层**与**身份贯穿**。单主体（全 `default`）下全部为 no-op，价值在多主体上线前。

约束：agent 运行时不 import platform；agent 归属主体取自 agent 配置（`agent_tenant`），不耦合 `long_term_ctx`。

## Goals / Non-Goals

**Goals:**
- `/chat`、`/ws` 运行前调用跨主体校验，default-closed。
- sub-agent / `invoke_agent` 继承父/会话 Principal 的 `tenant_id`，去掉写死 default。
- TUI 全程携带 Principal，已认证 edge 不命中 principal-less `user_id` 兜底。

**Non-Goals:**
- 多主体 fan-out 路由本身（已由 `tenant-scoped-db-routing` 覆盖）。
- 移除 `loop.run` 的 `user_id` 参数/兜底（保留作无身份基线；只保证 edge 不命中它）。
- OIDC / 外部 IdP；行级资源授权（per-user auth，另一层）。

## Decisions

### D1：跨主体校验放在 edge 入口，default-closed
在 `agent_app` 的 `/chat`、`/ws` handler 解析出 Principal 后、进入 `run`/`run_stream` 前调用 `_check_tenant(principal, agent_tenant)`，不符即拒（HTTP 403 / WS close）。`agent_tenant` 取运行 agent 的归属主体（agent 配置）。**为何在 edge 而非核**：核已被设计为只按 agent 归属主体路由（信任已进来的运行），跨主体"准入"是 edge 职责；核内不应再认证/鉴权（identity-port「核不认证」）。

### D2：sub-agent / invoke_agent 走继承，不写死、不重认
sub-agent 与 `invoke_agent` 透传当前回合的 `Principal`（含 `tenant_id`），删除 `loop.py:676` 的 `tenant_id="default"`。**为何不在 sub-agent 处重新解析主体**：identity-port「继承」明确内部调用不重认；重解析既多余又可能引入不一致。

### D3：TUI 让 Connection 持 Principal
`Connection` 增加 `principal: Principal` 字段（`agent_app` 建连时已有 `tui_principal`），`_stream_run` 把 `conn.principal` 传给 `run_stream`。**为何不在 dispatch 内重建 Principal**：建连时已解析，重建会丢 `tenant_id` 或重认；持有最忠实。

### D4：保留 user_id 兜底，但 edge 不命中
不删 `loop.run` 的 `user_id` fallback（standalone / 无身份基线仍需），只保证所有**已认证 edge 路径**传 Principal。**为何不一刀切删兜底**：删它会牵动 standalone agent run / 测试等无身份场景，超出本切片且风险大；本切片只堵 edge 断链。

## Risks / Trade-offs

- [校验取错 `agent_tenant`（如取成请求者主体）导致永远放行/永远拒] → 明确 `agent_tenant` 源 = agent 配置（与路由同源 `agent_tenant`）；测试覆盖 T1 请求者 × T2 agent 必拒、同主体必过。
- [TUI/invoke 改签名牵动较多调用点] → TDD 逐点改 + 跑 TUI/sub-agent/invoke 相关测试；`run`/`run_stream` 签名已支持 Principal，无需改核签名。
- [单主体下全 no-op，测试易"假绿"] → 测试显式构造多主体（T1 请求者 + T2 agent）触发拒绝路径，确保校验真生效而非恒 True。
- [继承改动影响 cron / system 路径] → 这些路径已有独立 Principal 解析（cron `_resolve_cron_principal` / `SYSTEM_PRINCIPAL`），本 change 不动；只改 sub-agent/invoke/TUI。

## Migration Plan

1. 接 `_check_tenant` 到 `/chat`、`/ws`（先写多主体拒绝测试见红）。
2. 去 `loop.py` sub-agent 写死 tenant；`invoke_agent` 透传 Principal。
3. TUI `Connection` 持 Principal + dispatch 透传。
4. 回滚：纯行为变更、无 schema / 数据迁移；回滚即还原调用点。

## Open Questions

- 无（校验位置、继承方式、兜底保留均已定）。
