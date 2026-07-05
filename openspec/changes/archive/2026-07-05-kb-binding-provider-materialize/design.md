# kb-binding-provider-materialize — Design

## Context

KB 现代化后目标态是"KB 单机多租户中心 = 唯一访问点，agent 皆 HTTP 客户端"。agent 侧消费链路已就绪：`agent.yaml` 的 `knowledge.provider.{type,url,auth_ref}`（`agent_config.py` 的 `AgentKnowledgeProvider`，`type=http` 时强制要求 url + auth_ref）→ `agent_app._configure_knowledge_provider` 选型 → `HttpKnowledgeProvider` 带 `Authorization: Bearer <service key>` + ingress principal 头调 kb serve `POST /search`。

平台侧管理链路也就绪：`agent_kbs` 绑定表 + `/admin/kb/{kb_id}/agents` 绑定 API + `Settings().kb_serve`（`KBServeSettings`: `url` / `service_key_ref` / `timeout_seconds`，platform 自己经 `KBServeClient` 代理管理请求）。

断点只有一处：`materialize._knowledge_for_agent`（materialize.py:512）物化绑定时只产出 `enabled + bindings(kb_id, default)`，`provider` 落默认 `local`。数据目录隔离后 managed agent 直读不到 kb-service 数据；http 所需的 url/auth_ref 无下发通路。

secret 下发既有机制（本设计全部复用，不新增通道）：

- `collect_env_var_names`（agent_config.py:875）是唯一权威口径，**已覆盖 `auth_ref: env:VAR` 形式**（key 以 `auth_ref` 结尾且值以 `env:` 开头即收集）；
- node 路径：`node_desired_state_api._agent_secrets`（:320）= per-agent `secret_store` 解密 ∪ "referenced env → provider key 回填"（`provider_key_for_env` 先例）；
- node 写盘 `ensure_env_scaffold` 只写 referenced env、自愈门禁 `_env_has_secret_values` 只对"被引用且非空"者要求落盘——只要 env 名经 auth_ref 被引用，三方口径自动对齐，无孤儿 credential slot 风险。

## Goals / Non-Goals

**Goals:**

- 管理员在平台完成 KB↔agent 绑定后，下一次物化/reconcile 即产出可直接工作的 http provider 配置，agent 无需人工改 agent.yaml。
- service key 值经既有 desired-state secrets 通道到达 node 并落 agent `.env`，不引入第四套 secret 口径。
- 平台未配置 kb_serve 时行为完全不变（dev/standalone、手工 agent.yaml 均不受影响）。

**Non-Goals:**

- 不做 per-agent 细粒度 KB 访问 key（v1 下发租户级共享 service key，见 Risks）。
- 不改 `AgentKnowledgeProvider` schema 与校验规则。
- 不做 kb serve 的每-node 寻址差异化（见 Risks 与 Open Questions）。
- 不碰 GraphRAG / retrieval_policy 的物化（保持 agent.yaml 手工可调）。

## Decisions

**D1 — provider 物化条件：绑定非空 ∧ `Settings().kb_serve.url` 与 `service_key_ref` 均已配置 → 写 `provider: {type: http, url, auth_ref}`；任一未配置 → 保持现状（默认 local），物化不失败。**
替代方案 a）总是写 http、缺配置时报错：会把 dev/单机部署（agent 与 KB 同机同布局，local 可用）变成强制配置负担，拒绝。b）由 node 侧改写 agent.yaml：node 不该拥有 agent.yaml 语义（platform 是物化唯一 owner），拒绝。选择"配置存在才升级"使行为向后兼容且可灰度。

**D2 — auth_ref 指向 canonical env 名 `FLEETENT_KB_SERVICE_KEY`，值由平台回填，不透传平台自己的 service_key_ref 原文。**
平台的 `service_key_ref` 可能是 `env:PLATFORM_SIDE_NAME` 或 `file://...`——两者在 agent 宿主机上都不成立。物化时统一写 `auth_ref: "env:FLEETENT_KB_SERVICE_KEY"`，平台在装配 secrets 时**解析自己的 ref 得到值**、以 canonical 名下发。agent 侧只看到一个稳定 env 名，与宿主机布局解耦。

**D3 — secret 值回填位置：`node_desired_state_api._agent_secrets`，模式复刻既有 model provider key 回填。**
现有代码对 referenced env 已有回填先例（`provider_key_for_env`）：per-agent 显式 secret 优先，未命中再回填。KB key 加同一段逻辑：`env_name == FLEETENT_KB_SERVICE_KEY` 且 kb_serve 已配置时，回填 `_resolve_auth_ref(kb_serve.service_key_ref)` 的值。替代方案——要求管理员对每个 agent 手工 `set_agent_secret`：破坏"绑定即生效"，拒绝；desired-state 新增专用字段下发 url/key：第四套口径，违反 referenced_env_names 唯一权威原则，拒绝。

**D4 — 优先级：per-agent 显式 secret > 平台回填。**
与既有 model key 回填语义一致（"not already supplied by a per-agent inject slot"）。留出租户内个别 agent 用独立 key 的旋钮，也让未来 per-agent key 演进不破坏契约。

**D5 — `_resolve_auth_ref` 从 `kb_serve_client.py` 提升为可复用 helper（platform 内部），desired-state 与 KBServeClient 共用。**
避免解析逻辑复制两份；仍在 platform 包内，不跨边界。

**D6 — embedding 前提只补文档。**
`validate_kb_service_boot`（service_config.py:370）已对 embedding endpoint 启动即失败，kb-standalone-ingest spec 已固化该要求；本 change 仅在 `docs/capabilities/knowledge-base.md` 补"平台绑定使用 KB 的部署前提"一段，无 spec/代码变更。

## Risks / Trade-offs

- **[kb_serve.url 的可达性歧义]** 平台配置的 url 是"platform 可达"的地址；多机部署下 agent 所在 node 未必可达（如 loopback、Docker 网络名）。→ Mitigation：文档明确 kb_serve.url 必须是 agent 网络可达地址（禁 loopback，除非单机）；每-node 差异化寻址（类比 `forward_host` 机制）明确 deferred，记入 Open Questions。
- **[租户级共享 key 的爆炸半径]** 同租户所有绑定 agent 持同一把 kb serve key；key 泄露影响整租户 KB 读面。→ Mitigation：kb serve 本就按 ingress principal 限租户路由（key 只解锁本租户）；per-agent key 列为后续演进，D4 的优先级设计已为其留缝。
- **[存量 agent 的收敛节奏]** 已绑定但 provider=local 的存量 managed agent 依赖下一次物化才升级。→ Mitigation：物化在 reconcile/重启/绑定变更时自然发生；无需数据迁移，接受最终一致。
- **[平台侧 env 缺失时的回填失败]** kb_serve 配置了 ref 但平台进程 env 缺值时 `_resolve_auth_ref` 抛错。→ Mitigation：回填段 try/except 降级为"跳过回填 + 记 warning"，不让单个 agent 的 desired-state 组装 500（与舱壁化原则一致）；agent 侧 node 自愈门禁会持续报缺 secret，可观测。

## Migration Plan

无 DB 迁移。部署顺序：platform 先升级（物化+回填逻辑）→ node 无需改动（消费既有契约）→ 管理员确认 `Settings().kb_serve` 已配置。回滚 = 回退 platform 版本，已物化的 http provider 配置在下次物化时回落 local（agent.yaml 由物化全量重写，无残留）。

## Open Questions

- 每-node 的 kb serve 寻址差异（类比 nodes.forward_host 的上报/覆盖链）是否需要？本 change 按单一 url 处理，等真实多机部署反馈再立项。
- per-agent KB key（配合 kb serve 侧 key→scope 映射）放到哪条线：安全演进线 or KB 线？本 change 不阻塞该决策。
