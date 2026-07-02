# Tasks: agent-kb-http-provider (Change D)

> **gated on Change C 落地**（多租户 kb-serve + 共享 service-key）：开工前 `git pull origin main` 确认 C 已在 main；apply 时对齐 C 落地的 kb-serve 监听地址与共享 service-key 形状。
> 复用现成 HttpKnowledgeProvider + AgentKnowledgeProvider(type=http)；本 change 主要是 managed 默认选择 + URL/key 注入接线。与 Change B 无文件重叠，可并行。
> TDD Hard Gate：测试在实现前，最窄命令红→绿。

## 1. managed agent 默认 http provider

- [ ] 1.1 [test-red] 测：node 托管拉起 agent、未显式声明 `knowledge.provider` 时，运行时注入 `HttpKnowledgeProvider` 指向注入的中心 kb-serve URL（带共享 service key auth_ref）；standalone `agent run` 未声明时仍 `LocalKnowledgeProvider`。跑最窄命令 → 见红。
- [ ] 1.2 [impl] 在 node 托管拉起 agent 的接线处（materialize/spawn）：未声明 provider 时注入 `type=http` + 中心 kb-serve `url` + `auth_ref`；`runtime/agent_app` boot 时据此装 `HttpKnowledgeProvider`（复用 `long_term_ctx` 现有装配）。standalone 分支保持 local 默认。跑 → 见绿。

## 2. kb-serve URL/key 注入来源

- [ ] 2.1 [impl] node 从其配置/平台下发获知中心 kb-serve 地址 + 共享 service key，经既有 node secret/env 注入路径写入 agent 的 `knowledge.provider.url` + `auth_ref`（service key 走 `env:`/`file://` 引用、落 agent `.env`，不进程 env 明文）。**对齐 Change C 落地的 kb-serve 监听地址与共享 service-key 形状**（apply 时先核 C 的实现）。
- [ ] 2.2 [test] 集成：managed agent 检索请求携自身 principal 打中心 kb-serve、命中本租户 KB（可对 C 的多租户 kb-serve 或其 stub 验路由）。

## 3. 收尾门禁

- [ ] 3.1 边界护栏：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`；agent 运行时/long_term_ctx 无新增反向依赖。
- [ ] 3.2 `openspec validate agent-kb-http-provider --strict`
- [ ] 3.3 `uv run mypy src`
- [ ] 3.4 `make test-pr` + `make test-integration-ci`，判据"对照 main 基线无新增失败"。
- [ ] 3.5 手验：managed 场景 agent 经中心 kb-serve HTTP 命中 KB；standalone `agent run` 仍 local 可用。
- [ ] 3.6 tasks.md 全 `[x]`；功能分支 `openspec archive agent-kb-http-provider`（同步 agent-knowledge-config spec）；**不扫 openspec/changes/archive/ 历史产物**；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
