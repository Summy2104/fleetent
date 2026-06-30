## ADDED Requirements

### Requirement: Agent knowledge provider selection

`agent.knowledge` MAY 声明 `provider` 选择该 agent 的 KB 检索源,默认 `local`(嵌入式,读本地 knowledge-base)。当 `provider.type` 为 `http` 时,SHALL 含远程 KB 检索端点 `url` 与服务鉴权引用(service key,沿用 `env:`/`file://` secret 引用约定);此时 agent 运行时 SHALL 经 `HttpKnowledgeProvider` 调该端点检索,而非本地 knowledge-base。未声明 `provider` 或 `provider.type=local` 时,行为与现状一致(LocalKnowledgeProvider),single-machine 部署无需任何 HTTP 配置。

#### Scenario: Default provider is local
- **WHEN** `agent.knowledge` 未声明 `provider`(或 `provider.type=local`)
- **THEN** agent 运行时使用默认 `LocalKnowledgeProvider`,读本地 knowledge-base
- **AND** 无需任何远程 KB 端点配置

#### Scenario: HTTP provider points agent at a remote KB
- **WHEN** `agent.knowledge.provider.type=http` 且声明了 `url` 与鉴权引用
- **THEN** agent 进程 boot 时注入 `HttpKnowledgeProvider` 指向该 `url`
- **AND** 该 agent 的被动 KB 检索经 HTTP 走远程端点,本地不再读 knowledge-base

#### Scenario: Provider config does not carry connector construction
- **WHEN** 声明 `knowledge.provider`
- **THEN** 它只含检索端点 url 与鉴权引用
- **AND** 不含 KB 源 connector 构造细节(Google Drive folder / Confluence space 等仍不在 agent 侧)
