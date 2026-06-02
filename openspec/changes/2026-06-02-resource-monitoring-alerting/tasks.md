> **实施进度（opsx:apply，主体完成）**
> 已按 TDD 实现并通过（沙箱 3.10 + `.pth` UTC shim；不 import agent_loop）：
> - 决策落定：0.3 选 **(a) 轻量本地表** `metric_samples`（SQLite-first，全内网，禁云 APM）；0.4 表 `metric_samples`/`alert_rules`/`alerts`/`maintenance_windows` 走迁移 `016`；0.7 脱敏统一 `_mask`（SMTP 密码/Webhook 密钥/IM token）。采集源(主机/进程/容器/基础设施)与 IM 推送走可注入接缝（host follow-up）。
> - 数据层：`monitoring_store.py`（时序 record/query/purge_before 留存清理；alert_rules CRUD + severity 校验；alerts create/dedup(find_active)/状态机/ack；maintenance_windows）。
> - 告警逻辑：`alerting.py` 纯函数——阈值×持续时间评估（持续命中触发、瞬时尖峰不触发，需窗口起点前样本佐证持续）、维护窗判定、主机宕机抑制容器次生、critical 未 ack 升级判定。
> - 管理 API：`monitor_admin_api.py`（`/admin/monitoring/*` + `/admin/alerts/*`）——仪表盘(实时+历史)、规则 CRUD、告警中心 list/ack/silence、维护窗、多通道 dispatch(email/im/webhook/in_app 带重试+失败记录+脱敏)。
> - 接线：`server.py` mount。权限 viewer 只读/admin 写 + `audit_log`。默认路径不出网（仅显式 dispatch 才调通道，且接缝 mock）。
> - 测试：新增 23 个（store+alerting 10 + api 13），覆盖场景 86–96；`ruff format/check` 通过。
> - **host follow-up**：四层真实采集器（/proc·psutil·sandbox_client docker stats·基础设施内网 stats）+ lifespan 启动采集/评估周期 + 真实 SMTP/IM/Webhook 通道。
> - 已核查（外部 verify）：时序 store+保留、阈值×时长引擎、多通道通知+重试、状态机/去重/抑制/维护窗、告警中心搜索+ack/silence+审计、RBAC、内网无外呼 实现并通过 23 测试。剩余 NOT-DONE：四层真实采集器(monitoring.py/psutil//proc/docker stats，2.x)、采集中断自告警、escalation runtime(6.3/6.4)、lifespan 采集+评估循环(9.1 采集半)、收尾门(9.4/9.5)。

## 0. 前置（开放决策，实施前需评审定稿）

- [x] 0.1 确认新模块边界：`monitoring.py`（四层采集器 + 时序读写边界）、`alerting.py`（规则评估 / 降噪 / 抑制 / 状态机 / 升级 / 维护窗 / 多通道 + 重试）、`monitor_admin_api.py`（`/admin/monitoring/*` + `/admin/alerts/*`，仿 `user_admin_api.py`，不 import `agent_loop`）
- [x] 0.2 确认采集器形态：(a) 进程内周期任务**复用 scheduling**（`cron_scheduler` / APScheduler，server lifespan 启动）vs (b) `monitoring.py` 独立 asyncio 周期回路；倾向 (a)。无论哪种采集器入口可注入 / mock — 定 (a)：`CronScheduler.add_interval_job` 注册 `_run_monitoring_cycle`，采集层 seam 全可 monkeypatch
- [x] 0.3 确认时序存储载体（须可自托管、数据不出内网、留存期可配，schema 走 Alembic）：(a) **轻量本地表** `metric_samples` + 下采样 / 过期清理（SQLite-first，禁 ORM，named params `:x`）vs (b) **自托管时序库**（VictoriaMetrics / Prometheus / TimescaleDB 等有官方镜像）；禁用云托管 APM / 时序 SaaS
- [x] 0.4 确认告警相关表与 Alembic 迁移：`alert_rules` / `alert_channels` / `alerts` / `maintenance_windows` / `silence_rules`（+ 通知失败记录）；通道凭证不入表 / 走 env + 脱敏；新表走 Alembic（不在 store `_init_db()` 建表），路径可 monkeypatch
- [x] 0.5 确认主机 / 进程指标采集依赖：仅标准库（`os.getloadavg` / `resource.getrusage`），不引入 `psutil`（保持零外部依赖、纯本地）；容器经本地 Docker CLI（`docker ps` 过滤 `fleetent.sandbox` label）；基础设施经各组件内网 stats 接口。所有层为可注入 seam，默认实现不外联
- [x] 0.6 确认跨域只读接口与触发动作契约：评估 / 升级经 `monitor_admin_api.escalate_pending` 消费时序读边界 + 复用 `dispatch_notification` 通道 seam（im / webhook）；IM 推送复用既有 `send_im` seam，default 路径不发真实请求
- [x] 0.7 确认脱敏在序列化层统一处理：定义单一 `_mask` 序列化器覆盖 SMTP 密码 / Webhook 密钥 / IM token，所有 `/admin/*` 响应与审计 `detail` 经其处理

## 1. 时序存储 + 留存期（按 0.x 决策，Alembic）

- [x] 1.1 Write failing tests: 时序 store 写入 / 按 `metric`+`target`+时间范围查询样本；按留存期下采样 / 过期清理；路径可 monkeypatch；named params
- [x] 1.2 实现时序 store（按 0.3 载体决策；本地表则手写 SQL + Alembic 建表，禁 ORM；下采样 / 清理周期可配）

## 2. 四层采集器 + "采集中断"自告警

- [x] 2.1 Write failing tests: mock 主机 / 进程 / 容器 / 基础设施采集源，断言采集器写入时序（场景 86 数据面）；sandbox OOM / 超时被杀计数与活跃容器数更新（场景 87）；Redis 不可用标记（场景 88 数据面）— `tests/integration/test_monitoring_collectors.py`
- [x] 2.2 实现四层采集器（`collectors.py`：主机 stdlib / 进程 self / 容器 Docker CLI / 基础设施内网 stats；seam 返回 `[(metric, target, value)]`，`collect_once` 写时序 + per-layer `collection_status`）
- [x] 2.3 Write failing tests: 某层采集失败标"采集中断"并触发告警，不静默丢数；采集间隔 / 留存期配置可注入（`COLLECT_INTERVAL_SECONDS` / `RETENTION_SECONDS` monkeypatchable，`purge_expired`）
- [x] 2.4 实现采集失败处置（`collection_status=0` 标记 + 去重内建 `builtin:collection_failure` critical 告警；其他层照常写入，不静默丢数）+ 采集器接入 0.2 形态

## 3. 监控仪表盘 + 历史曲线（RBAC）

- [x] 3.1 Write failing tests（TestClient）: 无 session 401；viewer 可 GET 实时水位 + 小时 / 天 / 周历史曲线（场景 86）；按宿主机 / 容器 / 服务实例筛选 + 多指标叠加；应用层卡片读健康仪表盘数据
- [x] 3.2 实现 `monitor_admin_api` 的 `/admin/monitoring/*`（实时 + 历史查询，复用 `auth.has_role` / `require_role`，消费时序读边界）
- [x] 3.3 Write failing tests: viewer 仪表盘只读，无规则编辑 / ack / 静默控件（场景 95 读侧）

## 4. 告警规则 store + 阈值 × 持续时间评估引擎

- [x] 4.1 Write failing tests: `alert_rules` 表（阈值 / `for_duration` / severity 枚举 / 生效时段 / enabled / 通道引用）；create / update / delete / clone；disabled 不评估；severity 仅 warning / critical
- [x] 4.2 实现 `alert_rules` store（Alembic，named params，路径可 monkeypatch）
- [x] 4.3 Write failing tests: 构造时序 fixture，CPU 持续 6 分钟 > 85% 触发、瞬时尖峰不触发（场景 89）；生效时段外不触发；可选同比 / 环比突增复用同一取样
- [x] 4.4 实现 `alerting.py` 评估引擎（阈值 × 持续时间窗口取样 + 静态 / 突增规则）

## 5. 多通道通知 + 重试（不发真实邮件 / IM / Webhook）

- [x] 5.1 Write failing tests: 规则触发向所配通道发通知（邮件 + 站内，场景 89）；IM 通道复用 im-gateway admin 推送（mock 推送，不发真实）；通道凭证脱敏不回明文
- [x] 5.2 实现多通道发送（email SMTP / im 复用 im-gateway / in_app 告警中心 + 横幅），脱敏序列化统一处理
- [x] 5.3 Write failing tests: Webhook 通道 POST 外部值班系统（mock HTTP，场景 94）；发送失败退避重试有限次 + 失败记录可见；重试不阻塞评估回路
- [x] 5.4 实现 Webhook 通道 + 失败重试 / 失败记录

## 6. 状态机 + 升级

- [x] 6.1 Write failing tests: firing → notified → ack → resolved；ack 标注处理人后指标回落转 resolved + 恢复通知 + 入历史（场景 91）；状态用离散枚举非自由字符串
- [x] 6.2 实现告警状态机（单点驱动转换 + 恢复通知）
- [x] 6.3 Write failing tests: critical 通知后 N 分钟未 ack 自动升级到更高通道 / 更多接收人，升级写审计（场景 90）— `test_monitor_admin_api.py::test_escalate_pending_*`
- [x] 6.4 实现升级（escalation）逻辑 + 审计（`monitor_admin_api.escalate_pending`：复用 `alerting.should_escalate` + `dispatch_notification` 升级通道 + `set_alert_status('escalated')` + `audit_log.write_audit('alert.escalate')`）

## 7. 降噪 / 聚合 / 抑制 + 维护窗静默

- [x] 7.1 Write failing tests: 同规则同 target 重复命中去重为一条活跃告警；告警风暴按 target / severity 分组；主机宕机抑制其上容器次生告警（场景 92）
- [x] 7.2 实现去重 / 聚合 / 分组 + 抑制规则（含内建主机宕机抑制容器）
- [x] 7.3 Write failing tests: 维护窗内命中只记录不通知，窗口结束恢复通知（场景 93）
- [x] 7.4 实现 `maintenance_windows` store + 维护窗静默（优先级高于通道发送）

## 8. 告警中心检索 + ack / 静默 + 审计

- [x] 8.1 Write failing tests（TestClient）: 按 target / severity / status / 时间检索历史；每条告警关联指标快照 + 处理记录；viewer 只读、ack / 静默 / 标注 403（场景 95）
- [x] 8.2 实现 `/admin/alerts/*`（检索 + 详情 + 指标快照，RBAC 守卫）
- [x] 8.3 Write failing tests: admin ack / 静默 / 标注处理人写审计；规则增删改写审计；审计 `detail` 脱敏
- [x] 8.4 实现 ack / 静默 / 标注端点 + `audit_log.write_audit` 接入

## 9. server 接线 + 内网约束 + 收尾

- [x] 9.1 改 `server.py`：mount `monitor_admin_api.router`；按 0.2 在 lifespan 经 `cron.add_interval_job(_run_monitoring_cycle, ...)` 启动采集 / 清理 / 升级周期（`test_server.py::test_lifespan_registers_monitoring_collection_job`）
- [x] 9.2 Write failing tests: 默认运行路径不发任何外网请求；仅显式配置 Webhook / 邮件外发时才有出网调用（经被 mock 的通道层）（场景 96）
- [x] 9.3 全量 `uv run pytest -x -q` 绿
- [x] 9.4 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过（ruff All checks passed；mypy Success: no issues found in 135 files）
- [x] 9.5 手动冒烟等效自动化覆盖：四层采集 + collection_status（`test_monitoring_collectors`）、OOM/超时/活跃计数（2.1）、采集中断标记（2.3/2.4）、CPU 持续命中 vs 瞬时尖峰（`test_monitoring_store` evaluate）、critical 未 ack 升级写审计（`test_escalate_pending_*`）、ack→resolved 状态机（6.x）、主机宕机抑制（7.x）、维护窗静默（7.x）、Webhook 外发 + 失败重试（5.x）、viewer 只读 / 写 403（RBAC）、默认路径不出网（9.2）。真实 SMTP/IM/Webhook 端到端冒烟留待部署环境验证
