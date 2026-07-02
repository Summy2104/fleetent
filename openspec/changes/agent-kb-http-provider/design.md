## Context

Change C 把 KB 变成单机多租户中心服务；agent node 多机、读不了本地 KB 文件，须经 kb-serve HTTP。现 managed agent 默认 `LocalKnowledgeProvider`（in-process），分机即读不到。`HttpKnowledgeProvider`（long_term_ctx:312）与 `AgentKnowledgeProvider`（agent_config:253，支持 type=http/url/auth_ref）都已在——本 change 是 **managed 默认选择 + URL/key 注入接线**。

## Goals / Non-Goals

**Goals**
- managed（node 托管）agent 默认经 HttpKnowledgeProvider 读中心 kb-serve。
- node 注入 kb-serve URL + 共享 service key；agent 携 principal（tenant）由多租户 kb-serve 路由。
- 消 colocation 硬伤 + RO-mount WAL 隐患。

**Non-Goals**
- 不改 kb-serve/worker（C）、不改平台（B）、不改 provider 协议/检索语义。
- standalone `agent run`（同机）不强制 http（保持 local 默认）。

## Decisions

**D1：managed=http 默认，standalone=local 默认。** 判据 = agent 是否 node 托管。node 拉起 agent 时（materialize/spawn 接线），若 agent 未显式声明 `knowledge.provider`，注入 `type=http` + 中心 kb-serve URL + 共享 service key auth_ref。`fleetent agent run`（dev，与 KB 同机）保持 local。理由：托管=多机=必须 HTTP；standalone=同机=in-process 更省。

**D2：kb-serve URL/key 由 node 获知并注入。** node 知道平台/kb-serve 地址（node 配置或平台下发，沿用 node secret/env 注入路径）。注入进 agent 的 `knowledge.provider.url` + `auth_ref`（service key 走 `env:`/`file://` 引用，落 agent `.env`，不进程 env 明文）。apply 时对齐 Change C 落地的 kb-serve 监听地址与共享 service-key 形状。

**D3：租户路由靠 principal。** agent 检索请求携带自身 principal（user_id/tenant_id）；多租户 kb-serve（C）按 principal.tenant_id 路由。agent 侧无需知道"多租户"，只管带 principal 打一个中心 URL。

**D4：复用现有熔断。** provider 失败熔断（`provider_failure_threshold`）已在 agent_config；HTTP provider 沿用，kb-serve 不可达时按既有降级路径。

## Risks / Trade-offs

- **kb-serve 成 agent 读 KB 的硬依赖**（managed 下）→ kb-serve 挂则 agent 检索降级；靠现有熔断 + kb-serve 高可用（单机中心，与平台同域）。
- **URL/key 注入接线依赖 C 的落地形状** → gated on C；apply 时先核 C 落地的监听地址/鉴权，再定注入细节。
- **standalone vs managed 默认分叉** → 明确以"是否 node 托管"为判据，文档写清；避免 dev 误配。

## Migration Plan

无迁移。managed agent 下次 materialize/spawn 即注入 http provider。回滚 = revert（managed 回落 local，仅在 agent 与 KB 同机时可用）。

## Open Questions

无（URL/key 注入的具体字段在 apply 时对齐 C 落地实现）。
