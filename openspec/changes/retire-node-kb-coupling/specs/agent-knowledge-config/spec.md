# agent-knowledge-config — Delta

## MODIFIED Requirements

### Requirement: Agent knowledge provider selection

`agent.knowledge` MAY 声明 `provider` 选择该 agent 的 KB 检索源。当 `provider.type` 为 `http` 时,SHALL 含远程 KB 检索端点 `url` 与服务鉴权引用(service key,沿用 `env:`/`file://` secret 引用约定);此时 agent 运行时 SHALL 经 `HttpKnowledgeProvider` 调该端点检索,而非本地 knowledge-base。

managed（node 托管）agent 的 http provider SHALL 由 **platform 物化唯一注入**（有 KB 绑定 ∧ 平台已配置 `Settings().kb_serve` 时产出 `provider: http`,见 `kb-agent-binding`）；**node MUST NOT 注入或改写任何 knowledge 配置**——node 落盘 agent.yaml 时对 knowledge 段原样透传,不读 kb-service.yaml、不产生 knowledge secret。平台未配置 `kb_serve` 时 provider 保持 `local`——**local 仅在 agent 与 KB 同机（standalone dev,`fleetent agent run`）时有效**,managed 部署下等同于无可用检索,配置缺失 SHALL 以此显性暴露而非被兜底掩盖。无论 local/http,该 agent 检索 SHALL 携带自身 `principal`(tenant),由(多租户)kb-serve 按 `principal.tenant_id` 路由。

#### Scenario: managed agent 的 http provider 来自 platform 物化
- **WHEN** node 托管拉起一个有 KB 绑定的 agent,且平台已配置 `kb_serve`
- **THEN** agent.yaml 的 `provider: http`（url/auth_ref）来自 platform 物化产物,node 原样落盘
- **AND** 该 agent 的被动 KB 检索经 HTTP 走中心 kb-serve、携自身 principal,本地不再读 knowledge-base

#### Scenario: node 不注入 knowledge 配置
- **WHEN** node 落盘一份含 KB 绑定、`provider` 非 http 的 agent 配置（平台未配置 kb_serve 的产物）
- **THEN** node 原样写入,不注入 provider、不读同机 kb-service.yaml、不产生任何 knowledge secret
- **AND** 该配置缺失以"managed 下检索不可用"显性暴露,由管理员在平台配置 `kb_serve` 修复

#### Scenario: standalone 默认仍 local
- **WHEN** `fleetent agent run`(dev,与 KB 同机)未声明 `provider`(或 `provider.type=local`)
- **THEN** 使用默认 `LocalKnowledgeProvider` 读本地 knowledge-base,无需任何远程 KB 端点配置

#### Scenario: HTTP provider points agent at a remote KB
- **WHEN** `agent.knowledge.provider.type=http` 且声明了 `url` 与鉴权引用(或经 platform 物化)
- **THEN** agent 进程 boot 时注入 `HttpKnowledgeProvider` 指向该 `url`
- **AND** 该 agent 的被动 KB 检索经 HTTP 走该端点,本地不再读 knowledge-base

#### Scenario: Provider config does not carry connector construction
- **WHEN** 声明 `knowledge.provider`
- **THEN** 它只含检索端点 url 与鉴权引用
- **AND** 不含 KB 源 connector 构造细节(Google Drive folder / Confluence space 等仍不在 agent 侧)
