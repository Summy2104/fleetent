## Why

平台已有 [observability](../../../docs/capabilities/observability.md)（agent 运行的 trace / 日志 / 业务统计）与「系统健康仪表盘」（应用层 API 错误率 / 延迟 / 队列积压 / 活跃 session），但**缺一个面向运维的基础设施与进程资源监控 + 阈值告警**管理面：admin 无法在后台看主机 / 进程 / sandbox 容器 / 依赖基础设施的实时水位与历史曲线，也无法配阈值规则、命中后走多通道告警与生命周期闭环。

1. **基础设施 / 进程资源不可观测**：宿主机 CPU / 内存 / 磁盘（用量 + inode）/ 负载 / 网络 IO、fleetent 进程级 CPU / 内存 / 文件句柄、活跃 sandbox 容器数、容器 OOM / 超时被杀次数、自托管 PostgreSQL / Redis / Qdrant / RabbitMQ 的存活 / 连接数 / 内存磁盘 / 队列积压——目前无任何后台视图。
2. **没有内置告警**：告警通知此前由 observability 划给外部系统；v1.0 起平台需**内置轻量告警**（仍可经 Webhook 外发对接外部值班系统），全自托管、零云依赖、数据不出内网。
3. **告警缺生命周期与降噪**：没有 firing → notified → ack → resolved 状态机、未 ack 自动升级、去重 / 聚合 / 分组、抑制规则、维护窗静默、告警中心检索与审计。

本 change **叠加基础设施与进程资源的监控 + 内置轻量告警**，与 observability 域边界清晰：observability 负责 agent 运行的 trace / 日志 / 业务统计；本模块负责**基础设施与进程资源**。应用层指标（API 错误率 / 延迟 / 队列积压 / 活跃 session）复用「系统健康仪表盘」数据并接入同一套告警规则，本模块不重复采集。

## What Changes

**ADDED**
- `resource-metrics-collection`：内置轻量采集器周期读取四层监控目标——(1) **主机资源**（CPU / 内存 / 磁盘用量 + inode / 负载 / 网络 IO）；(2) **fleetent 进程 + sandbox 容器**（进程级 CPU / 内存 / 文件句柄、活跃 sandbox 容器数、容器 OOM / 超时被杀计数）；(3) **依赖基础设施**（自托管 PostgreSQL / Redis / Qdrant / RabbitMQ 的存活 / 连接数 / 内存磁盘占用 / 队列积压）；(4) **应用层指标**（复用「系统健康仪表盘」数据，不重复采集）。采集**全部在内网、零外部依赖**；采集间隔与指标留存期可配；采集器自身故障在 UI 标"采集中断"并告警，不静默丢数。实时仪表盘 + 可选时间范围（小时 / 天 / 周）历史曲线，支持多指标叠加对比、按宿主机 / 容器 / 服务实例筛选。
- `alert-rules`：admin 对任一指标设规则——阈值（如 CPU > 85%）、**持续时间**（持续 N 分钟才触发，避抖动）、级别（warning / critical）、生效时段；规则可启用 / 禁用 / 复制；支持静态阈值，可选同比 / 环比突增规则。规则增删改写审计。
- `alert-notification-channels`：每条规则可选一个或多个通道——**邮件**、**IM 推送**（复用 im-gateway 向 Slack / Telegram / WhatsApp 的 admin 推送）、**Webhook**（POST 到外部告警 / 值班系统）、**站内告警中心 + 健康仪表盘顶部横幅**；通道发送失败有重试与失败记录。
- `alert-lifecycle`：每条告警状态机 `firing → notified → ack → resolved`，critical 未 ack 自动升级（escalation）；降噪（去重 / 聚合 / 分组）+ 抑制规则（主机宕机抑制其上容器次生告警）+ 维护窗静默；告警中心检索历史（按目标 / 级别 / 状态 / 时间筛选），每条告警关联触发时指标快照与处理记录；ack / 静默 / 标注处理人写审计。

**MODIFIED**
- 无核心运行模块语义变更。仅新增监控 / 告警模块、管理面读写与时序 / 告警相关表（见 Impact）。

## Capabilities

### New Capabilities

- `resource-metrics-collection`
- `alert-rules`
- `alert-notification-channels`
- `alert-lifecycle`

### Modified Capabilities

- 无（im-gateway / cron-scheduled-tasks / observability 运行语义复用，本 change 不修改其 spec）

## Impact

- **代码**：
  - 新增：`monitoring.py`（四层指标采集器 + 时序读写边界）、`alerting.py`（规则评估引擎、降噪 / 抑制 / 分组、状态机、升级、维护窗、多通道发送 + 重试）、`monitor_admin_api.py`（`/admin/monitoring/*` + `/admin/alerts/*` 路由，仿 `user_admin_api.py`，复用 `auth.require_role` / `auth.has_role` + `audit_log.write_audit`，不 import `agent_loop` 以便 TestClient 隔离测试）。新模块 / 采集器形态 / 时序存储载体 / 告警相关表由 0.x 决策。
  - 修改：`server.py`（mount `monitor_admin_api.router`；采集器若为进程内周期任务则在 lifespan 启动）。
- **全自托管采集与时序存储载体选型（须可自托管、不出内网）**：
  - 采集源全部为本地 / 内网读取：主机指标读 `/proc`、`/sys`、`os` / 标准库（不引云托管 APM agent）；sandbox 容器经现有 `sandbox_client` 的 Docker CLI 封装读 `docker stats` / inspect；依赖基础设施经其自带协议探活（PG / Redis / Qdrant / RabbitMQ 的内网连接与 admin/stats 接口）。
  - 时序存储二选一，均须可自托管、数据不出内网，留存期可配，schema 走 Alembic：(a) **轻量本地表**（SQLite-first 时序表 + 定期下采样 / 过期清理，零额外组件，对齐 SQLite-first 与禁 ORM）；(b) **自托管时序库**（如 VictoriaMetrics / Prometheus / TimescaleDB 等有官方镜像、可内网部署的组件，需在 PR 说明必要性与自托管方案）。**禁用云托管 APM / 时序 SaaS**（Datadog / 云监控等违反数据主权）。载体由 0.x 决策。
- **复用既有域（本面只消费其接口 / 触发动作，不重定义语义）**：
  - **im-gateway 域**：IM 推送通道复用 im-gateway 向 admin 的 Slack / Telegram / WhatsApp 推送；本面只构造告警消息体并触发发送。
  - **cron-scheduled-tasks（scheduling）域**：若采集器 / 规则评估采用进程内周期任务，可复用 scheduling 的定时机制（APScheduler）；具体复用方式由 0.x 决策。
  - **系统健康仪表盘（应用层指标）**：应用层指标（API 错误率 / 延迟 / 队列积压 / 活跃 session）直接复用其数据并接入同一套 `alert-rules`，本面不重复采集。
- **跨域 follow-up**：
  - 系统健康仪表盘需暴露应用层指标的只读读取接口供 `alert-rules` 评估引擎消费。
  - im-gateway 需暴露面向 admin 的推送触发接口（若尚未提供 admin 定向推送）。
- **数据**：新增时序指标表（按载体决策；若为本地表含 `metric` / `target` / `ts` / `value` / 维度标签 JSON，带留存期清理）、`alert_rules`（阈值 / 持续时间 / 级别 / 生效时段 / 启用 / 通道引用）、`alert_channels`（通道类型 + 配置，敏感值脱敏 / 走 env）、`alerts`（活跃 / 历史告警 + 状态 + 指标快照 + 处理记录）、`maintenance_windows`（目标 / 时间范围）、`silence_rules`（抑制规则）。新表走 Alembic（named params `:x`，不在 store `_init_db()` 建表，路径可 monkeypatch）。写审计落既有 `audit_log` 表。
- **安全 / 破坏性**：任何视图与审计 `detail` 不明文回显通道凭证（SMTP 密码 / Webhook 密钥 / IM token），脱敏在序列化层统一处理。采集全程内网，仅当 admin 显式配置 Webhook / 邮件外发时才产生出网流量。无破坏性变更；纯增量。

## Commit 切分建议

每个 commit 自包含、内部 TDD（测试先红 → 实现 → 绿）：

1. `feat(monitoring): time-series store + retention (Alembic, self-hosted)`（按 0.x 决策，1.x）
2. `feat(monitoring): four-layer collectors + collection-interrupted self-alert`（2.x）
3. `feat(monitor_admin_api): /admin/monitoring dashboard + history curves (RBAC)`（3.x）
4. `feat(alerting): alert_rules store + threshold×duration evaluation engine`（4.x）
5. `feat(alerting): notification channels (email/IM/Webhook/in-app) + retry`（5.x）
6. `feat(alerting): lifecycle state machine + escalation`（6.x）
7. `feat(alerting): dedup/grouping/inhibition + maintenance-window silencing`（7.x）
8. `feat(monitor_admin_api): alert center search + ack/silence + audit`（8.x）
9. `feat(server): mount monitor_admin_api router + start collector`（9.x）
