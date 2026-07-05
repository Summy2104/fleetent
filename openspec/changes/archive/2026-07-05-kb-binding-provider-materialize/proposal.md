# kb-binding-provider-materialize

## Why

管理员在平台上把 agent 绑定到 KB 后，agent 实际拿到的 knowledge 配置只有 `enabled + bindings`，`provider` 落在默认值 `local`——而 KB 数据目录隔离（data-dir-isolation）后，managed agent 无法直读 kb-service 的数据文件，`provider: {type: http, url, auth_ref}` 又没有任何平台下发通路。结果是"平台绑定"这一管理动作产生一个不可用的 agent 配置，唯一 workaround 是人工编辑 agent.yaml。这是"KB 在 Agent 侧经平台管理即可用"链路上唯一的代码硬断点。

## What Changes

- **物化写入 http provider**：`platform/agent_lifecycle/materialize.py` 的 `_knowledge_for_agent` 在存在 KB 绑定且平台配置了 `Settings().kb_serve`（url + service_key_ref）时，物化 `provider: {type: "http", url: <kb_serve.url>, auth_ref: "env:<canonical env name>"}`；未配置 kb_serve 时保持现状（provider 缺省 local，dev/standalone 行为不变）。
- **secret 值下发**：`node_desired_state_api._agent_secrets` 对 referenced env 中的 KB service key 环境变量名做平台侧回填（复用既有 "referenced env → provider key 回填" 模式），使 node 落盘的 agent `.env` 拿到真实 key。不新增第四套 secret 口径：`collect_env_var_names` 已覆盖 `auth_ref: env:VAR`，三方口径（下发/自愈门禁/写盘）自动对齐。
- **embedding 硬前提文档化**（仅 docs，无 spec 变更）：KB 服务侧 embedding endpoint 已是启动硬校验（`validate_kb_service_boot`，kb-standalone-ingest spec 已覆盖），本 change 只在 `docs/capabilities/knowledge-base.md` 补一段"agent 经平台绑定使用 KB 的部署前提"（kb_serve 配置 + embedding 服务可达）。
- 不改 `agent_config.py` 的 knowledge schema（`AgentKnowledgeProvider` 校验规则复用现状）；不新增表；不新增 agent→platform 反向依赖。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `kb-agent-binding`：绑定的物化产物从"仅 bindings"升级为"bindings + 可用的 http provider 接线"；新增平台 kb_serve 配置存在性作为物化 provider 的前置条件、以及 service key 经 desired-state secrets 下发的要求。（embedding 前提在 kb-standalone-ingest 已有启动硬校验要求，本 change 不再动该 spec。）

## Impact

- **Owning package**：`fleetent.platform.agent_lifecycle`（materialize）+ `fleetent.platform.node_management`（desired-state secrets 回填）。
- **Public API surface**：无新增/变更 HTTP 端点；变化体现在物化出的 agent.yaml 内容与 desired-state `secrets` 载荷。
- **Owned tables**：无（不新增表、不改 schema）。
- **Config namespace**：复用既有 `Settings().kb_serve`（url / service_key_ref）；引入一个 canonical env 名（如 `FLEETENT_KB_SERVICE_KEY`）作为 agent 侧 auth_ref 指向，具体命名在 design 定。
- **Cross-module dependencies**：materialize（platform）读 `fleetent.config.KBServeSettings` 与 `agent_kbs_store`，方向 platform→config 合法；agent 侧只消费 agent.yaml 与进程 env，无反向依赖。
- **Migration / shim plan**：无迁移。已有手工配置 `provider: http` 的 agent 不受影响（物化仅在平台管理路径生效）；存量"绑定了但 provider 落 local"的 managed agent 在下一次物化/reconcile 后自动获得 http provider。
- **安全权衡**：v1 下发的是租户级 kb serve service key（绑定该租户 KB 的所有 agent 共享），per-agent 细粒度 key 明确 deferred，在 design 记录。
