# Platform and channel roadmap

这份文档跟踪 fleetent 的控制面、治理、接入和自动化能力簇：Platform、Governance、User Center、Connectors、IM Gateway、Scheduling 和 Webhook。它用于汇总这些 capability 的当前完成度、Pilot 风险和后续 OpenSpec 优先级。

## 当前结论

**基础控制面和接入面已部分完成。** 当前已有 platform CLI（`fleetent platform`）、REST API、bearer token 认证、API key / user 管理、agent 管理、node 注册与编排、IM gateway、channel / user binding、scheduler 和 webhook 基础能力。

**Pilot 执行期（2026-06-25 现状）**：node supervisor / desired-state / reconcile 已落地；directed-reach（`notify_user`）已落地；Admin Web UI 尚未实现，管理入口为 CLI + HTTP API。Webhook 入口已从 platform server 移除，待以 agent runtime API 形式回归。

**Pilot 阶段更依赖”可操作”和”可排查”而非完整 UI。** 缺 review UI、policy UI、connector credential 管理、sync history 和 dashboard 不一定阻塞第一次 Pilot，但需要通过 CLI、API、runbook 和 diagnostics 提供可验证替代路径。

**主要风险在真实接入和权限边界。** Slack / Telegram / scheduler / user-scoped connectors 会穿过用户、agent、channel、tenant、审批和审计边界，Pilot 前需要用真实或准真实环境复核。

## 范围

| 能力域 | 文档 | 负责范围 |
| --- | --- | --- |
| Platform | [../platform.md](../platform.md) | admin API、admin CLI、console、agent/user/provider/connector/resource management |
| Governance | [../governance.md](../governance.md) | approval、quota、audit、agent policy、blocklist、role / permission boundary |
| User Center | [../platform.md](../platform.md)（user-center 规划已归档至 `docs/archive/user-center.md`） | user、tenant、team、API key、identity mapping |
| Connectors | [../connectors.md](../connectors.md) | 用户级外部工具授权连接器；区别于 KB 数据源 connector |
| IM Gateway | [../im-gateway.md](../im-gateway.md) | Slack / Telegram / WhatsApp 接入、user / channel 映射、allowlist |
| Scheduling | [../scheduling.md](../scheduling.md) | Cron scheduled tasks、Webhook triggers、session binding、automation entrypoints |

## 当前能力地图

| 能力 | 当前状态 | 已有基础 | 当前缺口 | 后续增强 |
| --- | --- | --- | --- | --- |
| Platform / Admin | 部分完成 | admin CLI、多个 admin API、agent / user / provider / connector / monitoring / stats 管理基础 | platform UI、review workflow、批量操作和权限细化 | Dashboard、workflow UI、operator cockpit |
| Governance | 部分完成 | permission gate、quota、audit log、blocklist、agent policy、approval lifecycle | policy UI、二次确认策略统一、复杂 RBAC / tenant 权限 | Governance dashboard、审批队列、策略模拟 |
| User Center | 部分完成 | users、API keys、roles、invite、IM user mapping、tenant/team 基础 | 统一身份视图、企业 IdP、租户管理 UI | SSO / IdP、组织结构同步 |
| User Connectors | 未开始 / 部分完成 | connector config store、user-scoped IM connector 基础、credential_ref 设计方向 | OAuth credential store、用户授权流、connector health / revocation | Connector marketplace、per-user audit |
| IM Gateway | 部分完成 | Slack / Telegram adapters、normalizer、allowlist、image attachment extraction、channel-agent binding | WhatsApp 入站实现、真实 IM smoke、用户级 connector 生产默认策略 | Multi-workspace、channel management UI |
| Scheduling / Webhook | 部分完成 | APScheduler、scheduled task store、webhook signature、session binding、internal maintenance | scheduler / worker 生产默认、full sync history、webhook source management UI | Automation builder、trigger dashboard |

## Pilot 验收关注点

- operator 能创建用户、API key、agent，并把 agent 绑定到合适用户 / channel / KB。
- Slack / Telegram 入站消息能正确映射 internal user，并遵守 allowlist / channel binding。
- 审批、审计、配额和 blocklist 在 risky tool / admin action 场景下可查询。
- scheduled task 和 webhook trigger 能复用 agent runtime，并保留 session / trace / audit 证据。
- connector credential 不以明文出现在日志、trace、diagnostics、UI 或导出文件。

## Backlog 骨架

### Pilot blocker 候选

- 用户或 API key 管理不可用，导致无法创建 Pilot 用户。
- IM 入站身份映射错误，导致跨用户或跨 channel 数据混淆。
- 审批 / 审计 / token 权限边界失效。
- Webhook / scheduled task 绕过认证、allowlist 或 trace。
- connector credential 泄漏。

### Docs gap 候选

- Slack / Telegram / Webhook / scheduler 配置步骤不清楚。
- operator 不知道如何查询审批、审计、用户映射或 connector 状态。
- 真实 IM smoke 的跳过条件和凭证要求不清晰。

### Enhancement 候选

- Review UI / approval queue。
- Policy admin UI。
- Connector OAuth flow 和 credential store。
- Channel management UI。
- Scheduler / webhook dashboard。

## 维护规则

- Platform / governance / channel / automation 的跨能力改动完成后，同步更新本 roadmap。
- 单 capability 的可观察行为和验收标准仍写在对应 capability 文档；本文件只维护能力簇状态、依赖和 Pilot 风险。
- 一次性执行日志和 review 记录放在 `docs/records/`，不要放入本 roadmap。
