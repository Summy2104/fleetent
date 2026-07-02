## MODIFIED Requirements

### Requirement: Agent knowledge provider selection

`agent.knowledge` MAY 声明 `provider` 选择该 agent 的 KB 检索源。当 `provider.type` 为 `http` 时,SHALL 含远程 KB 检索端点 `url` 与服务鉴权引用(service key,沿用 `env:`/`file://` secret 引用约定);此时 agent 运行时 SHALL 经 `HttpKnowledgeProvider` 调该端点检索,而非本地 knowledge-base。

provider 默认按**部署形态**取值:**managed（node 托管）agent 未显式声明 provider 时 SHALL 默认为 `http`**——由 node 注入中心 kb-serve 的 `url` 与共享 service key `auth_ref`(node 从其配置/平台下发获知),因为 managed agent 可与 KB 分机、读不了本地 KB 文件。**standalone(`fleetent agent run`,与 KB 同机)未声明时保持 `local`**(LocalKnowledgeProvider,in-process 读本地),single-machine dev 无需任何 HTTP 配置。无论 local/http,该 agent 检索 SHALL 携带自身 `principal`(tenant),由(多租户)kb-serve 按 `principal.tenant_id` 路由。

#### Scenario: managed agent 默认 http 指向中心 kb-serve
- **WHEN** node 托管拉起的 agent 未显式声明 `knowledge.provider`
- **THEN** 运行时注入 `HttpKnowledgeProvider` 指向 node 提供的中心 kb-serve `url`(带共享 service key auth_ref)
- **AND** 该 agent 的被动 KB 检索经 HTTP 走中心 kb-serve、携自身 principal,本地不再读 knowledge-base

#### Scenario: standalone 默认仍 local
- **WHEN** `fleetent agent run`(dev,与 KB 同机)未声明 `provider`(或 `provider.type=local`)
- **THEN** 使用默认 `LocalKnowledgeProvider` 读本地 knowledge-base,无需任何远程 KB 端点配置

#### Scenario: HTTP provider points agent at a remote KB
- **WHEN** `agent.knowledge.provider.type=http` 且声明了 `url` 与鉴权引用(或 managed 注入)
- **THEN** agent 进程 boot 时注入 `HttpKnowledgeProvider` 指向该 `url`
- **AND** 该 agent 的被动 KB 检索经 HTTP 走该端点,本地不再读 knowledge-base

#### Scenario: Provider config does not carry connector construction
- **WHEN** 声明 `knowledge.provider`
- **THEN** 它只含检索端点 url 与鉴权引用
- **AND** 不含 KB 源 connector 构造细节(Google Drive folder / Confluence space 等仍不在 agent 侧)
