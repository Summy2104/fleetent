# Design — Resource Monitoring & Alerting (Admin)

## 范围与边界

本 change 设计**基础设施与进程资源的监控 + 平台内置轻量告警**管理面。明确的域边界：

- **本模块负责**：基础设施与进程资源的采集、时序存储、实时仪表盘 + 历史曲线、告警规则评估、降噪 / 抑制 / 分组、告警状态机与升级、维护窗、多通道通知、告警中心与审计。
- **observability 域负责**：agent 运行的 trace / 日志 / 业务统计（request 级全链路、token / 耗时 / 模型使用、审批决策）。本模块**不**采集或重定义 agent 运行 trace；二者无重叠。
- **系统健康仪表盘（应用层指标）**：API 错误率 / 延迟 / permission_gate 待审批积压 / 活跃 session / 定时任务执行——由健康仪表盘提供数据，本模块**复用其只读接口**接入同一套 `alert-rules`，不重复采集。
- **告警通知归属变更**：通知此前划给外部系统，v1.0 起平台内置轻量告警；仍可经 **Webhook 外发**对接外部值班 / 告警系统。

借鉴 Grafana / Netdata / Datadog 的"指标面板 + 告警规则 + 告警中心"三件套，但**全自托管、零云依赖、数据不出内网**（采集与存储均在内网，遵守数据主权原则）。

## 四层监控目标采集方式

所有采集源都是本地 / 内网读取，**禁引入云托管 APM agent**：

| 层 | 指标 | 采集方式（内网、零云依赖） |
|----|------|---------------------------|
| 主机资源 | CPU、内存、磁盘用量 + inode、负载、网络 IO | 读 `/proc`、`/sys`、`os` / `shutil.disk_usage` 等标准库；可选 `psutil`（纯本地、无外联）由 0.x 决策 |
| 进程 + sandbox 容器 | fleetent 进程 CPU / 内存 / 文件句柄；活跃 sandbox 容器数；容器 OOM / 超时被杀计数 | 进程自身经标准库 / `/proc/self`；容器经现有 `sandbox_client` 的 Docker CLI 封装读 `docker stats` / `docker inspect`（OOMKilled、退出码）；超时被杀计数来自 sandbox 域已有的超时处置记录 |
| 依赖基础设施 | PG / Redis / Qdrant / RabbitMQ 的存活、连接数、内存 / 磁盘占用、队列积压 | 经各组件内网协议的 stats / admin 接口探活（PG `pg_stat_*`、Redis `INFO`、Qdrant `/metrics` 或 telemetry、RabbitMQ management API）；全部内网连接 |
| 应用层 | API 错误率 / 延迟、待审批积压、活跃 session、定时任务执行 | **复用系统健康仪表盘只读接口**，不重复采集 |

- **采集器自身故障可见**：某层采集失败（如 Docker 不可达、PG 连不上），不静默丢数——该目标标记为"采集中断"，并触发内置告警（"采集中断"是一类内建规则 / 状态）。
- **采集间隔与留存期可配**：通过 `config/settings.yaml` 或监控配置可调；路径 / 配置可 monkeypatch 注入以便测试隔离。

## 采集器形态（0.x 决策）

两种形态，均不引 AI 框架、可测试隔离：

- (a) **进程内周期任务复用 scheduling**：复用 `cron_scheduler`（APScheduler）注册周期采集 / 评估任务，server lifespan 启动；优点是零额外进程、与现有定时机制一致。
- (b) **独立采集回路**：`monitoring.py` 自带 asyncio 周期循环，与 scheduling 解耦。

倾向 (a)（复用既有 scheduling，符合"复用而非新造"）；最终由 0.x 决策。无论哪种，采集器入口可注入 / mock，单测不真实读系统。

## 时序存储载体决策（自托管、留存期可配）

二选一，均须可自托管、不出内网，schema 走 Alembic：

- (a) **轻量本地表（默认倾向）**：SQLite-first 时序表 `metric_samples`（`metric` / `target` / `ts` / `value` / `labels` JSON），写入走 store 边界（named params `:x`，手写 SQL，不 ORM）；后台周期**下采样 + 过期清理**实现可配留存期（如原始保留 N 天、按小时聚合保留更久）。零额外组件，最契合 on-prem 零依赖目标。
- (b) **自托管时序库**：VictoriaMetrics / Prometheus / TimescaleDB 等有官方 Docker 镜像、可内网部署的组件。引入需在 PR 说明必要性与自托管方案（对齐基础设施服务可引入原则）。
- **禁用**：Datadog / 云监控 / 任何云托管时序 SaaS（违反数据主权）。

仪表盘历史曲线查询统一走时序读边界接口，便于在两种载体间切换而不动上层。

## 告警规则评估引擎（阈值 × 持续时间）

- 规则模型：`metric` + `target` 选择器 + `op`（>, <, >= 等离散枚举，不用自由字符串）+ `threshold` + `for_duration`（持续 N 分钟）+ `severity`（warning / critical 离散枚举）+ `active_window`（生效时段）+ 通道引用列表 + `enabled`。
- **阈值 × 持续时间**：评估引擎在每轮采集后对每条启用规则取该指标在 `[now - for_duration, now]` 窗口的样本，**仅当窗口内持续满足阈值**才进入 firing；瞬时尖峰不持续则不触发（场景 89）。
- **可选同比 / 环比突增规则**：除静态阈值外，可配"较上一周期 / 上周同时段突增 X%"规则，复用同一窗口取样接口。
- 评估结果落 `alerts` 状态对象，交给降噪 / 状态机层处理。规则与样本读取均可注入构造 fixture。

## 降噪 / 抑制 / 分组算法

- **去重 / 聚合**：同一规则 + 同一 target 连续命中，聚合为**一条活跃告警**（更新 `last_seen` / 命中次数），不为每轮采集刷新一条（场景 92）。
- **分组**：告警风暴时按 target / severity 分组呈现与通知（一条聚合通知代替 N 条）。
- **抑制规则（inhibition）**：声明"源条件命中时抑制目标告警"。内建一条：**主机宕机 / 不可达时，抑制其上所有 sandbox 容器 / 进程的次生告警**（场景 92）。抑制只阻止次生告警的通知，仍记录其存在。
- **维护窗静默**：`maintenance_windows`（目标或全局 + 时间范围），窗口内命中的告警**只记录不通知**，窗口结束恢复通知（场景 93）。静默优先级高于通道发送。

## 状态机与升级

告警状态机（对齐 platform.md mermaid）：

```
firing → notified → ack → resolved
notified → escalated → ack           (critical 未 ack 超时)
notified → resolved                  (指标回落)
firing/notified → silenced → resolved (维护窗 / 手动静默)
```

- `firing`：阈值持续命中进入。
- `notified`：经降噪后向规则配置的所有通道发出通知。
- `escalated`：**critical** 告警在 `escalation_after`（N 分钟）内无人 ack，按升级策略发到更高优先级通道 / 更多接收人，升级动作**写审计**（场景 90）。
- `ack`：admin 在告警中心确认并可标注处理人（写审计）。
- `resolved`：指标回落到阈值内自动转 resolved 并发恢复通知；全过程入告警历史（场景 91）。
- `silenced`：维护窗或手动静默命中，只记录不通知，回落后转 resolved。
- 升级等待时间、升级目标通道可配。状态转换由 `alerting.py` 单点驱动，避免散落判断。

## 多通道通知与重试

- 每条规则可绑定一个或多个通道，通道类型离散枚举：
  - **email**：经自托管 SMTP 发送（不依赖云邮件 SaaS；SMTP 配置走 env / 脱敏）。
  - **im**：复用 **im-gateway** 向 admin 的 Slack / Telegram / WhatsApp 推送；本面构造消息体 + 触发，不重实现推送。
  - **webhook**：POST 告警内容到外部值班 / 告警系统的 URL（场景 94）；这是唯一会主动出网的通道，且仅在 admin 显式配置时存在。
  - **in_app**：站内告警中心 + 健康仪表盘顶部横幅（纯内部，无外联）。
- **失败重试与失败记录**：每次发送记录结果；失败按退避重试有限次，最终失败落 `notification_failures` / 告警处理记录，UI 可见（场景 94）。重试不阻塞评估回路。

## 与 observability 的清晰边界（再次明确，避免双源）

- observability：**agent 运行**的 request 级 trace、token / 耗时 / 模型、审批决策、业务统计——本模块不碰。
- 本模块：**基础设施与进程资源** + 应用层指标的告警接入。
- 二者唯一交叉：应用层指标由系统健康仪表盘提供，本模块只读消费做告警评估，不重复采集、不写 observability 的表。

## 权限与审计

- 路由 `/admin/monitoring/*`、`/admin/alerts/*`，仿 `user_admin_api.py`：登录会话解析 → `auth.has_role` / `auth.require_role` 守卫。
  - **viewer**：只读——浏览资源监控仪表盘、历史曲线、告警中心历史与详情。
  - **admin / built_in_admin**：写——新建 / 改 / 删 / 复制告警规则、ack / 静默 / 标注处理人、配置维护窗、配置通道。
- 写操作一律 `audit_log.write_audit(actor, action, target_type, target_id, detail)`：规则增删改、ack、静默、维护窗 / 通道配置、升级动作。
- 通道凭证（SMTP 密码 / Webhook 密钥 / IM token）**脱敏在序列化层统一处理**；审计 `detail` JSON 同样脱敏后再落库。

## 测试隔离（遵循 CLAUDE.md）

- `monitor_admin_api.py` 不 import `agent_loop`，用 FastAPI **TestClient** 单测路由（与 `user_admin_api.py` 同款，规避 PEP 695 的 3.12 依赖）。
- **mock 采集源 / 系统指标**：测试 patch 主机 / 进程 / 容器 / 基础设施采集函数返回构造的指标值，不真实读 `/proc`、不真实调 `docker` / PG / Redis；断言采集器把值写入时序、采集失败标"采集中断"并触发告警。
- **构造时序 fixture**：评估引擎测试注入构造的样本序列（如"CPU 持续 6 分钟 > 85%"与"瞬时尖峰"），断言持续时间逻辑（触发 vs 不触发）、同比 / 环比突增。
- **mock 通道发送（不发真实邮件 / IM / Webhook）**：patch SMTP / im-gateway 推送 / Webhook HTTP（`respx` 或 `unittest.mock`），断言消息体、重试与失败记录；绝不外发。
- **状态机 / 降噪 / 抑制 / 维护窗**：纯逻辑单测，构造命中序列断言 firing → notified → ack → resolved、未 ack 升级、去重聚合、主机宕机抑制容器次生告警、维护窗只记录不通知。
- 数据库 / 路径隔离：时序与告警 store 复用统一 DB fixture 或 `monkeypatch` `DB_PATH` 到 `tmp_path`；named params（`:x`），不新增 `?`；schema 走 Alembic，不在 store `_init_db()` 建表；采集间隔 / 留存期配置路径可 monkeypatch。
- 权限守卫：构造 viewer / admin / 无 session 会话，断言读放行、写 403、无 session 401（场景 95）。
- **内网约束断言**（场景 96）：断言默认运行路径不发任何外网请求；仅在显式配置 Webhook / 邮件外发时才有出网调用，且该调用经被 mock 的通道层。
