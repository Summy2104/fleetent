## 1. wire 协议 + HttpKnowledgeProvider client

- [ ] 1.1 写 unit 测试:KnowledgeChunk ↔ wire JSON 双向序列化(字段齐全,round-trip 等价)(见红)
- [ ] 1.2 写 integration 测试:HttpKnowledgeProvider 对 fake HTTP server(respx/httpx mock)发 `{principal,query,kb_ids,limit}`、带 Bearer + X-Fleetent-Principal header、把 `{chunks:[...]}` 反序列化为 list[KnowledgeChunk](见红)
- [ ] 1.3 在 `long_term_ctx` 实现 `HttpKnowledgeProvider`(httpx + identity.encode_ingress_principal + KnowledgeChunk 反序列化),满足 KnowledgeProvider 契约;跑 1.1–1.2 见绿;确认不 import platform

## 2. 失败降级

- [ ] 2.1 写 integration 测试:fake server 返回非 2xx / 连接错 / 超时 → HttpKnowledgeProvider 记日志返回 []，build_context 不抛、memory/always-facts 仍返回(见红)
- [ ] 2.2 在 client 内兜 HTTP/网络异常返回空(与外层 _retrieve_with_timeout 分工);跑 2.1 见绿

## 3. 配置 + agent_app 注入

- [ ] 3.1 写 unit 测试:`AgentKnowledge.provider` 默认 local;agent.yaml 可解析 `provider.type=http` + url + auth_ref(见红)
- [ ] 3.2 在 `agent_config.AgentKnowledge` 加可选 `provider`(默认 local);跑 3.1 见绿
- [ ] 3.3 写 integration 测试:provider.type=http 时 agent boot 注入 HttpKnowledgeProvider 指向 url;未配置/local 时仍走默认 LocalKnowledgeProvider(行为与现状一致)(见红)
- [ ] 3.4 在 `agent_app._init_agent_db_schema`(或其调用处,kb_runtime.set_database 一带)按 `agent.knowledge.provider` 选择注入;auth_ref 经 env:/file:// 解析为 Bearer token;跑 3.3 见绿

## 4. 收尾验证

- [ ] 4.1 跑 `make test-pr` + `make test-unit-ci`(含 76% 覆盖率关)+ `make test-integration-ci`,判"对照 main 基线无新增失败、覆盖率不破 76"(注:integration 有已知并行 flaky,新增失败判定以串行复核为准)
- [ ] 4.2 ruff format/check 改动文件;module-boundaries 护栏通过(long_term_ctx ✗→ platform);`openspec validate kb-http-provider` 通过
- [ ] 4.3 更新 `docs/capabilities/` 相关:HttpKnowledgeProvider + wire 协议 + agent.knowledge.provider 配置 + 默认 local(非代码产物,人工确认后再 commit)
