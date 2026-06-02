## Why

平台已具备 [observability](../../../docs/capabilities/observability.md)（`traces` 表 + `record_trace_event` / `query_trace_events` / `get_usage_summary`）、permission_gate（approvals）与 [agent_store](../../../docs/capabilities/multi-agent.md)（绑定 / 来源）三套**原始数据源**，但缺一个以 **Agent 为主视角的统计分析面**，回答「每个 agent 用得多不多、快不快、稳不稳、贵不贵、被谁用」，对照 `platform.md` 的「统计面板（Agent 维度）」设计：

1. **没有跨 agent 的聚合分析层**：现有 `get_usage_summary` 只做单维度用量聚合，没有按 agent_id 的多指标面板（用量与成本 / 性能与可靠性 / 工具与治理 / 模型·Skill·绑定），也没有总览、筛选、多 agent 横向对比。
2. **下钻能力缺失**：无法把任一指标沿 用户 / channel / 模型 / 时间 切片；尤其缺 **per-user 视图**（在某 agent 下各用户的 token 用量、调用频率、最近活跃排行，以及反向「按用户」看其在所有 agent 上的汇总），无法识别重度用户、分配配额、定位异常激增。
3. **请求级链路无法纵深下钻**：单请求的对话与工具入出参已在 trace 的 `messages` 中，sub_agent 经 `parent_session_id` 可关联，但没有一个**从用户 → 请求列表 → 单请求完整事件流**（用户输入 / 每轮 LLM 调用 / 工具入出参 / 审批决策 / memory 命中 / 上下文压缩 / sub_agent 子链路 / 最终回复）的纵深视图。
4. **治理信号无处可见**：allowed_tools「已授权未使用」收窄提示、审批通过 / 拒绝 / 超时率、终止原因分布等治理与可靠性信号没有聚合面承载。
5. **导出与定时报告缺失**：面板视图无法导出 CSV / 图片，也无法按周 / 月把指定 agent 的统计摘要定时推送到管理员邮箱。

本 change **只叠加 platform 聚合视图**：读 `traces`（observability）、approvals（permission_gate）、agent_store（绑定 / 来源），按 agent_id 聚合与下钻；**不重定义任何采集语义**——trace / usage 的发射归 observability + agent-runtime，审批归 permission_gate，绑定归 agent_store，本面只交叉引用并消费其只读接口。纯只读分析（除导出与定时报告配置外无写操作）。

## What Changes

**ADDED**

- `agent-stats-aggregation`：按 agent_id 的多指标聚合面板与下钻——
  - **面板总览与筛选**：选单个 / 多个 agent、时间范围（日 / 周 / 月 / 自定义）、环境；多 agent 并排**对比视图**（同一指标横向比）；任一指标卡片可下钻成明细。
  - **① 用量与成本**：调用次数、活跃独立用户数 / channel 数 / 会话数、token 用量（prompt / completion / total 的总量与单次均值）、按天 / 周趋势 ✅；成本（`token × 模型单价`，单价来自 model-provider change）⏳。
  - **② 性能与可靠性**：响应时延（平均 / P50 / P95）、每会话平均轮数 ✅；错误率 / 失败率、**终止原因分布**（max_turns / budget_exceeded / cancelled / approval_rejected / loop_detected / consecutive_failures）、model fallback 触发率、上下文压缩触发次数 ⏳。
  - **③ 工具与治理**：Top 工具调用排行、每次运行平均工具数 🟡；工具失败率 / 超时率 ⏳；**allowed_tools 覆盖率**（列出该 agent 配了白名单却从未被调用的工具，驱动最小权限收窄）🟡；permission_gate 触发数与审批**通过 / 拒绝 / 超时率** ✅（approvals）。
  - **④ 模型 · Skill · 绑定**：按模型的调用 / token / 成本分布、task_type 分布 ✅；skill 命中 Top、memory 命中率、sub_agent 调用数与子任务成功率 ⏳；绑定用户数 / channel 数、是否默认 agent、受管 / 临管来源分布 ✅。
  - **下钻维度**：任一指标可沿 用户 / channel / 模型 / 时间 切片；**per-user 视图**（选定 agent 下各用户 token 用量、调用频率、最近活跃排行）与反向「按用户」汇总 ✅。
  - **导出与定时报告**：任意视图导出 CSV / 图片；按周 / 月把指定 agent 的统计摘要定时推送到管理员邮箱（复用 scheduling 域）。
  - **权限**：viewer 与 admin 均可只读浏览；per-user 等含个人用量明细按部署方策略可对 viewer 脱敏。
- `request-trace-view`：⑥请求级全链路追踪——
  - 从 per-user 排行一路下钻：**用户 → 该用户的请求列表（按时间 / agent / channel 筛选）→ 单个请求的完整链路**。
  - 单请求按时间序展开**事件流**：用户输入 → 每轮 LLM 调用（模型 / token / 耗时 / 是否 fallback）→ 每次工具调用入参 / 出参 / 耗时 / 成功失败 → permission_gate 审批决策 → memory 命中 → 上下文压缩事件 → **sub_agent 派生（经 `parent_session_id` 就地展开子链路，与父链路同构）** → 最终回复；每个节点可展开 / 折叠、可复制原始 JSON。
  - 依赖 `request_id` 贯穿渲染；**缺 request_id 的运行按会话退化**（退化到 session_id / ts + user_id 尽力聚合并提示链路可能不完整，不报错）。platform 仅按 request_id 渲染，不负责发射。

**MODIFIED**

- 无核心运行模块语义变更。trace / usage / approvals / 绑定的采集与发射语义复用 observability / permission_gate / agent_store，本 change 不修改其状态机；仅新增聚合查询边界与 `/admin/stats/*` 管理面。⏳ 字段（budget 成本、终止码、错误分类、工具失败 / 超时、skill 命中、memory 命中、request_id 贯穿）的发射列为**跨域 follow-up**（见 Impact），由各域实现，本面只消费。

## Capabilities

### New Capabilities

- `agent-stats-aggregation`
- `request-trace-view`

### Modified Capabilities

- 无（采集语义复用 `observability` / `permission_gate` / `agent_store`，本 change 不修改其 spec；⏳ 字段发射与 request_id 贯穿列为跨域 follow-up）

## Impact

- **代码**：
  - 新增：`stats_admin_api.py`（`/admin/stats/*` 路由，仿 `user_admin_api.py`，复用 `auth.require_role` / `auth.has_role` + `audit_log.write_audit`；**不 import `agent_loop`** 以便 TestClient 隔离测试）。
  - 新增：聚合查询边界（按 0.x 决策落在 observability 既有 store 之上的只读聚合层 vs 新 `stats_store.py`），按 agent_id 聚合 `traces` / approvals / agent_store；走 store 边界 named params（`:agent_id` / `:start_ts` 等），不直接散落 `sqlite3.connect`。
  - 修改：`server.py`（mount `stats_admin_api.router`）；定时报告复用 `cron_scheduler` / `schedule_store`，导出 / 报告配置是本面唯二的写操作。
- **本面边界**：纯聚合 + 渲染。**不写 traces / approvals，不发射任何采集事件**；request_id / span_id 也不由本面生成。
- **跨域 follow-up（运行语义在各域，本面只消费其只读接口 + 渲染）**：
  - **agent-runtime 域**需：(1) 在 `run() / run_stream() / run_sync()` **入口生成 ULID request_id**（时间可排序），用 **contextvar** 贯穿主循环，所有子事件（工具调用、审批、模型路由、memory、压缩、sub_agent）携带该 request_id；(2) **sub_agent 继承父 request_id + 自带 span_id** 形成 trace 树（OTel-lite）；(3) HTTP 路径补 `session_id`；(4) **历史 trace 不回填**（退化见场景 85）。对齐「待决问题」已定结论，本面仅按 request_id 渲染。
  - **observability 域**需：traces 补 ⏳ 字段——budget 成本 / 终止码（max_turns / budget_exceeded / cancelled / approval_rejected / loop_detected / consecutive_failures）/ 错误分类 / 工具失败·超时 / skill 命中 / memory 命中等；并暴露按 request_id / span_id 查询的 trace 树读取接口。本面以这些字段是否就绪决定 ⏳ 指标点亮。
  - **model-provider 域**提供**模型单价表**（input / output 每 1k token，已定放 model_router 配置）；本面成本聚合按 `token × 单价` 计算，**未配置单价的模型成本显示「未配置」而非 0**。
- **数据**：按 0.x 决策——若加物化 / 缓存表（聚合加速）则走 **Alembic**（不在 store `_init_db()` 建表 / 补列），named params，路径可 monkeypatch；若直接打 `traces` 表则不新建表，仅新增只读聚合查询。定时报告配置复用既有 `scheduled_tasks` 表，无新增写表。
- **安全 / 破坏性**：纯增量只读分析面，无破坏性变更。per-user 明细按部署方策略可对 viewer 脱敏；trace payload 已由 observability payload safety 脱敏，本面不放大泄露面（复制原始 JSON 复用已脱敏 payload）。导出 / 报告配置两类写操作写审计。

## Commit 切分建议

每个 commit 自包含、内部 TDD（测试先红 → 实现 → 绿）：

1. `feat(stats_store): agent-id aggregation queries over traces/approvals/bindings`（聚合查询边界，① 用量 + ② 性能 ✅ 部分）（1.x）
2. `feat(stats_store): tool/governance + allowed_tools coverage + approval rates`（③，含 🟡 messages 解析与 ✅ approvals）（2.x）
3. `feat(stats_store): model/skill/binding distribution + per-user/by-dimension drilldown`（④ + 下钻 + per-user）（3.x）
4. `feat(stats_store): cost aggregation with model pricing + "未配置" fallback`（成本 ⏳ + 单价缺失语义）（4.x）
5. `feat(request_trace): request-list + single-request event stream over request_id`（⑥ 主链路 + 退化）（5.x）
6. `feat(request_trace): sub_agent subtree expansion via parent_session_id`（⑥ trace 树）（6.x）
7. `feat(stats_admin_api): /admin/stats/* read-only routes + viewer/admin guard + redaction`（7.x）
8. `feat(stats_admin_api): export CSV/image + scheduled email report config`（导出 + 定时报告，复用 scheduling）（8.x）
