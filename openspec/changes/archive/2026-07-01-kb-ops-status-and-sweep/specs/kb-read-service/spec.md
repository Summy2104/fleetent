## ADDED Requirements

### Requirement: KB 服务状态只读端点

kb-serve SHALL 提供只读 `GET /status`,暴露本租户的 connector 同步状态与近期 ingest job 状态(含 status / 结果摘要),供运维观测 ingest 进度与失败原因。鉴权 SHALL 与 `/search` 一致(Bearer service key + ingress principal,principal.tenant_id 须与服务绑定租户一致)。kb-serve SHALL 为纯读服务,SHALL NOT 承载 connector sweep 调度(调度归 kb-worker,见 `kb-standalone-ingest`)。

#### Scenario: 查询连接器与 job 状态
- **WHEN** 运维以合法 Bearer + principal 请求 `GET /status`
- **THEN** 返回本租户 connector 状态(来自 `knowledge_connector_status`)与近期 ingest job(来自 `kb_ingest_jobs`,含 status 与结果摘要)
- **AND** 跨租户(principal.tenant_id ≠ 绑定租户)被拒绝

#### Scenario: kb-serve 不承载 sweep
- **WHEN** 只启动 kb-serve(未启动 kb-worker)
- **THEN** kb-serve 提供检索与状态读取,但不运行 connector sweep 调度
