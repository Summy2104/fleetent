## Why

常乐负责或强依赖的能力模块已经完成 MVP Foundation 和多轮 Pilot MVP 基础能力建设：

- observability / diagnostics
- memory / long-term context / reflection
- vector store / reindex / embedding provider
- knowledge base local / Google Drive / Confluence connector baseline
- deployment config / backup / upgrade checklist

下一步如果继续只做增强 spec，容易延迟进入真实测试环境，无法尽早暴露部署、配置、凭据、真实数据、排障和验收流程问题。

本 change 产出 Pilot 手工验收指南，让团队可以在测试环境按同一套步骤部署、配置、运行 smoke、记录问题和判断是否可小范围试用。

## What Changes

- 新增 `docs/deployment/pilot-acceptance-guide.md`。
- 指南覆盖：
  - 环境和前置条件。
  - 配置文件和 secret 检查。
  - SQLite backup / upgrade / restore drill。
  - 服务启动与 health check。
  - observability traces / usage / performance / diagnostics export。
  - memory extraction / search / retention / reflection maintenance proposal。
  - long-term context 注入验证。
  - knowledge base local / Google Drive / Confluence connector check / sync / status / search。
  - vector store reindex 和 embedding / rerank provider smoke。
  - reflection report smoke。
  - 失败记录模板和 Go / No-Go 判定。
- 更新 `docs/capabilities/deployment.md` 和 `docs/capabilities/owner-capability-roadmap.md`，把 Pilot 验收指南作为 Pilot MVP 验收入口。

## Out of Scope

- 不新增产品功能。
- 不修改 Python 代码。
- 不修改 CI。
- 不要求默认测试连接真实 LLM、embedding 或 SaaS。
- 不实现 Admin UI / HTTP 查询入口。
- 不实现 scheduler / worker。
- 不实现 credential store。
- 不要求通过本 change 完成真实环境验收；本 change 只提供验收指南。

## Module Boundary Impact

- **Owning package**：none，文档型 change。
- **Public API surface**：无代码 API 变化。
- **Owned tables**：无。
- **Config namespace**：无新增配置；文档会引用现有 `settings.yaml`、`mcp.servers.yaml`、credential_ref 和环境变量。
- **Cross-module dependencies**：文档描述 pilot acceptance 时跨 deployment、observability、memory、long-term context、reflection、vector store 和 knowledge base 的验收顺序。
- **Migration / shim plan**：无。
