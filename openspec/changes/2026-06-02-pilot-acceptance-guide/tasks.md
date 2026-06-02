## 0. 前置确认

- [x] 0.1 确认本 change 只写文档，不改 Python 代码
- [x] 0.2 确认验收指南面向测试环境人工验收，不替代自动化测试
- [x] 0.3 确认真实 LLM / embedding / SaaS connector smoke 均为显式 opt-in

## 1. Pilot acceptance guide

- [x] 1.1 新增 `docs/deployment/pilot-acceptance-guide.md`
- [x] 1.2 写清验收目标、环境前置条件和 Go / No-Go 标准
- [x] 1.3 写清配置、secret、MCP server file 和 credential_ref 检查
- [x] 1.4 写清 SQLite backup / upgrade / restore drill
- [x] 1.5 写清服务启动、health check 和 CLI 可用性检查

## 2. Capability acceptance sections

- [x] 2.1 写 observability / diagnostics 验收步骤
- [x] 2.2 写 memory / long-term context / reflection 验收步骤
- [x] 2.3 写 knowledge base local / Google Drive / Confluence 验收步骤
- [x] 2.4 写 vector store reindex / embedding / rerank smoke 验收步骤
- [x] 2.5 写真实外部依赖 skipped / failed / passed 记录规则

## 3. Reporting templates

- [x] 3.1 增加故障记录模板
- [x] 3.2 增加验收报告模板
- [x] 3.3 增加 Pilot blocker / docs gap / enhancement / out-of-scope 分类规则

## 4. Docs cross-links

- [x] 4.1 更新 `docs/capabilities/deployment.md`，链接 Pilot acceptance guide
- [x] 4.2 更新 `docs/capabilities/owner-capability-roadmap.md`，把 Pilot acceptance guide 标记为 Pilot MVP 验收入口
- [x] 4.3 如需要，更新 `docs/README.md` 的 deployment 文档索引

## 5. Verification

- [x] 5.1 运行 `openspec validate 2026-06-02-pilot-acceptance-guide --strict`
- [x] 5.2 运行 `git diff --check`
