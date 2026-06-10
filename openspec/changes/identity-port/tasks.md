## 1. Principal + Identity 端口（基座）

- [x] 1.1 写失败测试：`Principal{user_id, tenant_id}` 类型存在且精瘦（无 role/scopes/team）；构造/字段断言
- [x] 1.2 实现 `Principal` + 基座 `Identity` 端口协议（`凭证 → Principal | None`），跑绿 1.1
- [x] 1.3 写失败测试 + 实现：单机本地 bearer 适配器（env/static token 或 agent 侧 key 解析）产出 `Principal`，**不 import platform**

## 2. bearer 拆分 → 根除 #1（核心目标）

- [x] 2.1 写失败测试：依赖护栏断言 agent 运行时解析路径（含 bearer 适配器）**无 `import fleetent.platform.*`**；且「无 platform、platform 表不存在」下 standalone bearer 解析可用
- [x] 2.2 实现：platform 的 `api_keys` 解析下沉为 **platform 侧适配器**；改 `user_store.authenticate` 去掉无条件 `from fleetent.platform... import`，改由注入的端口适配器，跑绿 2.1
- [x] 2.3 跑既有 server/agent_app 鉴权测试确认行为不变（有效 key 过、吊销/过期/blocked 拒）

## 3. 渠道担保解析器（IM）

- [x] 3.1 写失败测试：IM `(platform, platform_user_id)` 经渠道担保适配器产出 `Principal`，保留"原生 id 作 user_id、不读 user_store"语义
- [x] 3.2 实现：把 `im_gateway/access.resolve_identity` 包成端口适配器（产出 Principal），跑绿 3.1

## 4. 核消费 Principal + edge 接线

- [x] 4.1 写失败测试：`loop.run`/`run_stream` 接收 `Principal`；核内部用 `principal.user_id` 维持 memory/session/budget scope 行为不变（带过渡兼容：`Principal | str` 归一）
- [x] 4.2 实现核签名改造 + 过渡兼容，跑绿 4.1
- [x] 4.3 写失败测试 + 实现：edge 在入口解析 `Principal` 并传核——`server._authenticate` / `agent_app._authenticate` 返回 Principal；`_validate_tui_token` 通过后产出 local Principal；edge 校验 `Principal.tenant_id == agent 主体`（跨主体拒）
- [ ] 4.4 跑既有 /chat、/ws、TUI 端到端测试确认行为不变

## 5. cron 存档复检 + system 路径 + 收口

- [ ] 5.1 写失败测试 + 实现：cron 从 `scheduled_tasks.user_id` load 后**复检状态**（block/删/移出主体则拒），产出 Principal 传核
- [ ] 5.2 写失败测试 + 实现：纯基础设施任务（TTL 清理等）用显式 `system` 标识，不冒充 user，审计记 `system`
- [ ] 5.3 收口核签名为纯 `Principal`（去过渡兼容）；全仓确认核/edge 不再直传裸 `user_id` 绕过 Principal
- [ ] 5.4 change 收尾：依赖护栏（agent 运行时无 platform import）+ standalone 无 platform 鉴权基线 + `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate identity-port --strict`
