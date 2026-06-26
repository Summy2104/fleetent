# Observability and deployment roadmap

这份文档跟踪 Observability、Diagnostics、Deployment / Config 相关能力。它们是 Pilot Go / No-Go 的证据来源和运行基础，不承载 memory / KB / reflection 的详细能力规划。

## 当前结论

**Observability / Deployment 已达到能力簇 Go ✅。** 2026-06-04 已在本机 `local-as-server`
模式完成人工验证：Docker Compose 启动、health check、`validate-config`、SQLite backup / upgrade /
restore drill、trace / usage / performance 查询、diagnostics export / redaction 和 Pilot verification
report 均可用。

**Pilot 执行期（2026-06-25 现状）**：4 物理库拓扑（management.db + per-agent agent_state.db〔含 agent_memory_items〕 + per-tenant KB + vector backends）已全部落地，嵌入式前向迁移（Y）均已上线。managed 栈 live e2e 已验证（2026-06-22）。

**该结论不是全项目 Pilot Go。** 真实 LLM / embedding / rerank / Google Drive / Confluence smoke
归 Runtime / Model Router 与 Intelligence roadmap 继续验证；本 roadmap 只负责记录 smoke 状态和提供可观测、
诊断、部署与证据包基础。

**已知环境 note。** 本机 Docker Compose 服务可启动，但 app 容器内没有 Docker CLI / socket，sandbox
effective mode 为 `off`。这不是 Observability / Deployment blocker；是否允许容器内访问宿主 Docker、
是否 fail fast 或降级，归 Runtime / Sandbox roadmap 决策。

## 范围

| 能力域 | 文档 | 负责范围 |
| --- | --- | --- |
| Observability | [../observability.md](../observability.md) | logs、agent traces、source attribution、usage / performance summary |
| Deployment / Config | [../deployment.md](../deployment.md) | on-prem config、Docker Compose Pilot 入口、backup / upgrade、module runtime prerequisites |
| Pilot verification | [pilot-readiness-roadmap.md](pilot-readiness-roadmap.md) | 自动化证据包、真实 smoke 状态、Go / Conditional Go / No-Go 建议 |

人工验收入口：[Observability and Deployment Roadmap 人工测试手册](observability-deployment-roadmap-test-manual.md)。

## 当前能力地图

| 能力 | 当前状态 | 已有基础 | 当前缺口 | 后续增强 |
| --- | --- | --- | --- | --- |
| Observability foundation | 基础完成 | structured logs、SQLite traces、usage summary、performance summary、source attribution、runtime event coverage、admin query CLI、diagnostics export / manual retention、contract tests | platform UI / HTTP 查询入口 | OTel / Prometheus、dashboard UI、告警 |
| Deployment / config | 基础完成 | Platform root `.env` / `platform.yaml`、`agents/<agent-id>/agent.yaml` / `.env`、四个 canonical example、env secret reference、本地 SQLite upgrade / backup 脚本、Pilot install checklist、Docker Compose Pilot 入口 | 准生产部署演练和 config docs 对 intelligence runtime prerequisites 的持续收敛 | config center、Admin UI、hot reload |
| Pilot verification | 基础完成 | `scripts/generate_pilot_verification_report.py` 可输出 `pilot-capability-verification.md` 和 `pilot-capability-verification.json`；报告包含默认测试命令、真实 smoke skip/pass/fail 和问题分类 | 真实 LLM / embedding / rerank / SaaS smoke 仍需显式 opt-in 运行 | 后续可接 dashboard / CI artifact / platform UI |

## M1：可观测、可排查

目标：每次 agent 运行的关键行为都有可查询证据，工程师能定位问题。

完成标准：

- LLM call、tool call、fallback、permission、context compression、final reply 都有 trace event。
- 可以按 run / user / agent / session 查询关键耗时、token、错误、fallback 和工具调用摘要。

已完成 spec：

- `observability-runtime-event-coverage`：补齐 runtime event source，不做聚合 API。
- `observability-performance-summary`：基于 runtime events 提供 Python 聚合查询 API，不做 UI / rollup。

剩余缺口：

- platform UI / HTTP 查询入口、OTel / Prometheus 和告警不属于 M1，进入后续运维入口。

## Pilot 验收证据

Pilot 验收前先生成自动化证据包：

```bash
uv run python scripts/generate_pilot_verification_report.py
```

默认输出 `pilot-capability-verification.md` 和 `pilot-capability-verification.json`。真实 smoke 仍必须显式 opt-in，例如 `FLEETENT_REAL_LLM_SMOKE=1`、`FLEETENT_GOOGLE_DRIVE_SMOKE=1`；缺少 flag 或 credential ref 时报告为 skipped。报告中的问题分类固定使用 `Pilot blocker`、Docs gap、Enhancement、Out-of-scope，并给出 Go / `Conditional Go` / No-Go 建议，供人工验收复核。

## 后续 Backlog

### 真实环境验证

- `real-llm-smoke`：真实 LLM route smoke。
- `real-embedding-smoke`：真实 embedding provider smoke 和 retrieval quality check。
- `real-rerank-smoke`：真实 rerank provider smoke 和 KB hybrid rerank quality check。
- `google-drive-real-smoke`：真实 Google Drive credential_ref、connector check / sync smoke。
- `confluence-real-smoke`：真实 Confluence credential_ref、connector check / sync smoke。

### 管理和运维入口

- `observability-http-or-platform-query`：platform UI / HTTP 查询入口。
- `diagnostics-alerting`：诊断包之外的告警和 dashboard。
- `config-center`：配置中心和 hot reload。

## 维护规则

- Observability / diagnostics / deployment 相关 OpenSpec 完成后，同步更新本 roadmap。
- Pilot 验收报告如果暴露部署或可观测性问题，先按 `Pilot blocker`、Docs gap、Enhancement、Out-of-scope 分类，再决定是否进入 OpenSpec。
