## Context

当前 roadmap 已经把常乐负责模块分成 MVP Foundation、Pilot MVP 和 Pilot 后增强。

目前的主要风险不是某个单点 foundation 缺失，而是还缺少一套真实测试环境验收流程：

- operator 不知道先配什么、再跑什么。
- smoke 命令散落在 capability docs 和 admin CLI 里。
- Google Drive / Confluence / embedding 等真实外部依赖需要显式 opt-in，但缺统一步骤。
- 验收问题没有统一记录格式，后续无法判断应该补功能、补文档还是补运维能力。

## Target Document

新增：

```text
docs/deployment/pilot-acceptance-guide.md
```

定位：

- 面向常乐或测试环境 operator。
- 用于第一次 Pilot 部署后人工验收。
- 是 `pilot-install-checklist.md` 的后续步骤：
  - install checklist 负责“装起来”。
  - acceptance guide 负责“验证能不能小范围试用”。

## Guide Structure

建议文档结构：

1. 验收目标和 Go / No-Go 标准。
2. 环境前置条件。
3. 配置与 secret 检查。
4. 数据库 upgrade / backup / restore drill。
5. 服务启动和基础 health check。
6. Observability / diagnostics 验收。
7. Memory 验收。
8. Long-term context 验收。
9. Reflection 验收。
10. Knowledge Base 验收。
11. Vector store / embedding / rerank smoke。
12. 真实 SaaS connector smoke。
13. 故障记录模板。
14. 验收报告模板。

## Acceptance Scope

### 必须覆盖

- `fleetent-admin` 可用。
- 配置文件不包含 secret。
- SQLite backup / upgrade / backup-only / dry-run 流程可跑。
- diagnostics export 脱敏。
- traces / usage / performance 可查询。
- memory 能写入、检索、维护 dry-run。
- long-term context 能注入 memory / KB source attribution。
- reflection 能生成报告，并能生成 User Memory maintenance proposals。
- KB local source 能 sync 和 search。
- Google Drive / Confluence connector 至少能跑 check；真实 sync smoke 需要显式凭据。
- vector reindex dry-run 和 rebuild 可跑。

### 显式 opt-in

这些步骤只在环境变量和凭据完整时执行：

- 真实 LLM route smoke。
- 真实 embedding provider smoke。
- Google Drive connector smoke。
- Confluence connector smoke。

如果没有配置，应记录为 `skipped: credentials not configured`，不是验收失败。

## Go / No-Go

建议标准：

- Go：核心本地链路、diagnostics、observability、memory、KB local、reindex、backup / upgrade 全部通过；真实外部 smoke 至少 check 通过或明确 skipped。
- Conditional Go：核心链路通过，但真实 SaaS 或 embedding smoke 因凭据、网络或数据问题失败；需要记录 workaround 和 owner。
- No-Go：服务启动、配置加载、数据库 migration、diagnostics、memory / KB 基础链路或 observability 查询不可用。

## Follow-up Loop

验收指南不直接决定增强 spec。

验收后应把问题分成：

- 必须修复的 Pilot blocker。
- 文档 / 操作说明缺口。
- Pilot 后增强。
- 非当前 owner 范围。

这样可以让增强 track 和验收反馈互相校准。
