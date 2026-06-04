# Pilot readiness roadmap

这份文档是 fleetent Pilot Go / Conditional Go / No-Go 的横向总览。它只做全项目薄看板和验收入口索引；各能力簇的详细状态放在同目录下的专项 roadmap。

## 当前结论

**Pilot MVP 工程前置已基础完成。** 当前已有 admin query CLI、agent KB binding、connector operations、diagnostics / retention、Docker Compose Pilot 入口、Pilot install checklist、Pilot acceptance guide 和自动化验证报告入口。

**当前还不能仅凭本文件直接宣称全项目 Pilot Go。** Intelligence 和 Observability / Deployment
专项 roadmap 已达到 Go；全项目 Pilot Go 仍需按 [Pilot acceptance guide](../../deployment/pilot-acceptance-guide.md)
汇总 Runtime / Tooling、Platform / Governance / Channels 的剩余接入风险后输出最终 Go / Conditional Go / No-Go 判定。

Pilot 验收前先生成自动化证据包：

```bash
uv run python scripts/generate_pilot_verification_report.py
```

默认输出 `pilot-capability-verification.md` 和 `pilot-capability-verification.json`，覆盖默认测试命令、能力域证据、真实 smoke skip/pass/fail 和问题分类。真实 smoke 必须显式 opt-in，例如 `FLEETENT_REAL_LLM_SMOKE=1`、`FLEETENT_GOOGLE_DRIVE_SMOKE=1`；缺少 flag 或 env credential reference 时报告为 skipped。报告中的问题分类固定使用 `Pilot blocker`、Docs gap、Enhancement、Out-of-scope，并给出 Go / `Conditional Go` / No-Go 建议，供人工验收复核。

## Roadmap 索引

| Roadmap | 覆盖能力 | 用途 |
| --- | --- | --- |
| [runtime-tooling-roadmap.md](runtime-tooling-roadmap.md) | Agent Runtime、Model Router、Tools、MCP、Sandbox、Skill、Session | 执行引擎与工具链路状态、端到端稳定性风险、v1.0 执行计划入口 |
| [intelligence-roadmap.md](intelligence-roadmap.md) | Memory、Long-term Context、Reflection、Vector Store、Knowledge Base | 智能层能力深度状态、质量增强批次、真实 provider / SaaS 验证缺口 |
| [observability-deployment-roadmap.md](observability-deployment-roadmap.md) | Observability、Diagnostics、Deployment / Config | 可观测证据、诊断包、安装升级备份、Pilot 验收运行基础 |
| [platform-channel-roadmap.md](platform-channel-roadmap.md) | Platform、Governance、User Center、Connectors、IM Gateway、Scheduling / Webhook | 控制面、治理、接入和自动化状态，真实接入和权限边界风险 |
| [../../records/roadmaps/v1.0-roadmap.md](../../records/roadmaps/v1.0-roadmap.md) | Agent runtime、model-router、tools、MCP、sandbox、skill、session | v1.0 执行引擎开发排期记录 |

专项人工验收手册：

- [Intelligence Roadmap 人工测试手册](../../deployment/intelligence-roadmap-test-manual.md)
- [Observability and Deployment Roadmap 人工测试手册](../../deployment/observability-deployment-roadmap-test-manual.md)

## 全项目 readiness 看板

| 能力簇 | 当前状态 | 详情 | Pilot 风险 |
| --- | --- | --- | --- |
| Agent runtime / tooling | 部分完成 | [runtime-tooling-roadmap.md](runtime-tooling-roadmap.md) | Medium：核心执行链路已可用，但运行治理和工具/沙箱增强仍需分批收敛 |
| Intelligence | Go | [intelligence-roadmap.md](intelligence-roadmap.md) | Low：真实 LLM、embedding、rerank、Google Drive、Confluence、KB retrieval E2E 和全量 provider reindex 已本机准生产验证；生产运维入口作为 post-Go backlog |
| Observability / Deployment | Go（local-as-server validated） | [observability-deployment-roadmap.md](observability-deployment-roadmap.md) | Low：部署、备份恢复、可观测和 diagnostics 已本机验证；sandbox 容器内 Docker 不可用交由 Runtime / Sandbox 验证 |
| Platform / Governance / Channels | 部分完成 | [platform-channel-roadmap.md](platform-channel-roadmap.md) | Medium：Slack / Telegram / Webhook / scheduler / connector 可用性和权限边界需要结合真实部署复核 |

## 状态定义

| 状态 | 含义 |
| --- | --- |
| 已实现 | 关键用户路径已经完成，默认测试覆盖，短期只需维护 |
| 基础完成 | public API / store / 配置边界已建立，但效果验证、运维或生产化仍有缺口 |
| 部分完成 | 已有可用能力，但关键链路或边界仍明显缺失 |
| 仅设计 | 文档和 spec 已有方向，但没有可依赖实现 |
| 未开始 | 尚未进入设计或实现 |

## Pilot MVP 工程前置

| spec | 完成状态 |
| --- | --- |
| `observability-admin-query-api` | 已完成 admin CLI，可查询 run trace / usage / performance，避免排障必须手写 SQL |
| `knowledge-base-agent-kb-binding` | 已完成 agent / tenant 到一个或多个 KB 的绑定策略和默认可见范围 |
| `knowledge-base-connector-operations` | 已完成 connector list / check / status / sync、dry-run、失败摘要和真实 SaaS smoke 操作说明 |
| `deployment-pilot-install-checklist` | 已完成安装、升级、备份、恢复、健康检查和回滚清单 |
| `data-retention-and-diagnostics-policy` | 已完成 logs / traces / connector state 的 retention、导出、脱敏和备份边界 |
| `deployment-docker-compose-foundation` | 已完成 Docker Compose Pilot 默认入口、配置初始化和 flat `secrets/` 目录说明 |
| `pilot-acceptance-guide` | 已完成人工验收指南和报告模板 |

## Pilot MVP 仍需横向验收

- Intelligence 真实 LLM / embedding / rerank / Google Drive / Confluence smoke 已完成，详见
  [intelligence-roadmap.md](intelligence-roadmap.md)。
- Observability / Deployment local-as-server 验证已完成，详见
  [observability-deployment-roadmap.md](observability-deployment-roadmap.md)。
- 复核 Runtime / Tooling 的执行链路、工具、MCP、sandbox 降级和端到端稳定性风险。
- 复核 Platform / Governance / Channels 的 Slack / Telegram / Webhook / scheduler / connector 可用性和权限边界。
- 按 [pilot-install-checklist.md](../../deployment/pilot-install-checklist.md) 完成一次准生产安装、升级、备份、恢复和诊断包导出演练。
- 按 [pilot-acceptance-guide.md](../../deployment/pilot-acceptance-guide.md) 完成 Go / Conditional Go / No-Go 判定。

## 合理内测平衡点

以下 OpenSpec changes 用于把当前 Pilot 能力推进到“可控内测 / Pilot 交付”标准，同时避免一开始引入完整
dashboard、scheduler / worker 或复杂权限系统：

| Change | 目的 |
| --- | --- |
| `production-config-validation` | 启动 / 验收前校验配置、env credential reference、目录权限、明文 secret 和 profile 规则。 |
| `diagnostics-redaction-export-hardening` | 强化诊断包 manifest、redaction 和 forbidden artifact 边界。 |
| `pilot-verification-gate` | 固化内测前验证门禁、报告格式和 Go / Conditional Go / No-Go 规则。 |
| `kb-connector-smoke-status` | 固化 KB connector check / dry-run / execute sync / latest status 证据和真实 smoke opt-in 规则。 |
| `manual-maintenance-entrypoints` | 在不做 scheduler / UI 的前提下提供 dry-run first、可审计的手动维护入口。 |

## Pilot 问题分类

| 分类 | 含义 | 处理 |
| --- | --- | --- |
| Pilot blocker | 阻止小范围真实用户试用，例如服务无法启动、DB migration 不可用、diagnostics 不脱敏、memory / KB local 基础链路不可用、secret 泄漏 | 必须修复并复测后才能 Go |
| Docs gap | 功能可用，但操作说明、错误解释、记录模板或排障路径不清晰 | 可 Conditional Go，但要补 owner 和完成时间 |
| Enhancement | Pilot 可用性不被阻塞的增强，例如 UI、scheduler、credential store、真实 rerank 质量评估、graph / rerank 默认检索策略产品化 | 不阻塞第一次 Pilot 验收，进入后续 spec 评估 |
| Out-of-scope | 非当前能力簇范围或本 change 明确不处理的事项，例如客户网络策略、企业 IdP、生产 secret manager 选型 | 记录依赖 owner，不作为本次验收失败原因 |

## 维护规则

- 每个专项 roadmap 只维护相关能力簇的深度状态和后续批次。
- 本文件只维护横向 readiness、验收入口和跨能力风险。
- Pilot 验收报告中的问题必须先分类，再决定进入 docs gap、后续 OpenSpec 或 out-of-scope 跟进。
