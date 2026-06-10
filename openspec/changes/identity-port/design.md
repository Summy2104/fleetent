## Context

设计已在 `target-architecture-proposal.md §6` + memory `identity-auth-model` 定稿，本 doc 只把它对齐到当前真实代码 + 落 apply 策略。

现状（已核实）：
- **#1 泄漏**：`user_store.authenticate`（user_store.py:54-75）懒导入 `platform.user_management.api_key_store` 并调 `resolve()`。
- **认证散在 5 处**：`server._authenticate`（server.py:406）、`agent_app._authenticate`（agent_app.py:489）均调 `user_store.authenticate`；`_validate_tui_token`（agent_app.py:73，env 等值、user_id="local"）；`im_gateway/access.resolve_identity`（access.py:71，直接返回平台原生 id、不读 user_store）；`auth.validate_session`（auth.py:76，进程内 session→user_id）。
- **核无 Principal**：`loop.run/run_stream(user_id: str = "default")`（loop.py:1426/2031），字符串身份，用于 memory/session/budget/audit scope。
- **cron**：`scheduled_tasks.user_id` → `loop.run(user_id=…)`（cron_scheduler.py:82）。
- 前置已具备：`tenants`/`users.tenant_id`（#2.5，迁移 067-069）。

## Goals / Non-Goals

**Goals:**
- 立 `Principal{user_id, tenant_id}` + 基座 `Identity` 端口（凭证→Principal）。
- bearer / 渠道担保两解析器；agent 侧解析器不 import platform → 根除 #1。
- 核 `run/run_stream` 消费 `Principal`；edge 在入口解析。
- cron 存档复检、system 路径成文。

**Non-Goals:**
- OIDC/Google 适配器实现（端口已为其留位，本切片不落）。
- 现有 edge 机制（TUI token / IM allowlist / 密码登录）的重写——它们成为端口后的适配器、行为不变。
- #3 物理库 / platform 只读投影。
- 给 Principal 加 `role`/`scopes`/team（刻意挡在端口外）。

## Decisions

**D1 端口在基座、核与 edge 只依赖端口类型。** authn 实现按部署可插拔（单机本地 / platform / 将来 OIDC）。
- 备选：核直接 import 某个 authn 实现。否决——正是 #1 的成因。

**D2 bearer 解析拆「agent 侧适配器（不 import platform）」与「platform 侧适配器（api_keys 表）」。** standalone agent 用前者；platform 部署注入后者。`user_store.authenticate` 去掉无条件 platform import。
- 备选：保留 `user_store.authenticate` 懒 import。否决——懒 import 仍是反向依赖，standalone 仍"够得到"platform。

**D3 核签名 `user_id: str` → `Principal`。** 核内部 `principal.user_id` 维持现有 scope 行为，`tenant_id` 备 routing/审计。
- 备选：再加一个 `tenant_id: str` 参数、不引 Principal。否决——身份是一个对象、edge 一次解析整体传入，符合 §6；零散参数易漏配。
- 注：为降低 ripple，可保留 `user_id` 关键字的**过渡兼容**（内部包成 `Principal(user_id, tenant_id="default")`），apply 末段再收口为纯 Principal。

**D4 `Principal`（请求者）≠ `AgentContextIdentity`（运行的 agent）。** 物理路由（#3）按 agent 主体，不在本切片；本切片只立 Principal + 在 edge 校验 `Principal.tenant_id == agent 主体`（防跨主体）。

**D5 非凭证路径**：继承（不重认）、cron 存档复检（load `scheduled_tasks.user_id` + 复检 block/删/移出主体）、system（基础设施不冒充 user、显式标识、如实审计）。

## Risks / Trade-offs

- **核签名改动 ripple 大**（`run/run_stream` 全调用点 + 测试）。→ 缓解：D3 的过渡兼容（先接受 `Principal | str`、内部归一），分阶段收口；每阶段红绿。
- **遗漏某条 authn 路径仍 import platform**。→ 缓解：加依赖护栏断言「agent 运行时 + 其 bearer 适配器无 `import fleetent.platform.*`」；并跑「无 platform、platform 表不存在」下的 standalone 鉴权基线。
- **IM 身份语义**：当前 IM 用平台原生 id 作 user_id（access.py:71，不读 user_store）。→ 渠道担保解析器要保持此行为（信任渠道、无密钥），只是包成 `Principal`，不引入对 user_store 的新依赖。
- **session 进程内态**：`auth._SESSIONS` 是进程内 dict（单实例）。→ 本切片不改其存储模型，只把"session→user_id"包进 bearer 类解析器。

## Migration Plan（apply 分阶段，串行红绿）

1. 立 `Principal` + `Identity` 端口类型（基座）+ 单机本地 bearer 适配器。
2. bearer 拆分：platform api_key 解析下沉为 platform 侧适配器；`user_store.authenticate` 去无条件 platform import（#1 修复）+ 依赖护栏。
3. 渠道担保解析器（IM）包成端口适配器（保留原生 id 语义）。
4. `loop.run/run_stream` 收 `Principal`（带过渡兼容）；edge（server/agent_app/tui）在入口解析并传入。
5. cron 存档复检 + system 路径成文；收口核签名为纯 Principal（去过渡兼容）。

- **回滚**：全程 feat 分支；未上线，回滚 = revert。
- **apply 体量提示**：本 change 较大；若一会话难以收完，可按上述阶段切成 #4a（端口+Principal+#1 修复）/ #4b（核签名+edge 接线）/ #4c（cron/system 收口）——propose 阶段先锁完整设计，apply 时按需再分。

## Open Questions

- 核签名最终形态：`run(principal: Principal, …)` 一步到位，还是长期保留 `user_id` 兼容糖？倾向 apply 末段收口为纯 `Principal`。
- IM 渠道担保产出的 `Principal.tenant_id` 取值：来自连接器绑定的主体（edge 已知），spec 时定具体来源字段。
