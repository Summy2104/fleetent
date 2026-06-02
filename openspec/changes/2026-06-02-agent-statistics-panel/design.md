# Design — Agent Statistics Panel（统计面板）

## 聚合层定位

本面是 platform 的**聚合视图**，处于已有原始数据源之上的只读分析层：

```
traces (observability)  ──┐
approvals (permission_gate)├──> stats 聚合（按 agent_id） ──> /admin/stats/* ──> 面板 / 对比 / 下钻 / 请求级链路
agent_store (绑定/来源)  ──┘
```

- **只读消费，不采集**：本面读 `traces` / approvals / 绑定，**不写任何采集事件、不发射 request_id / span_id、不改任一域的状态机**。trace / usage 的发射归 observability + agent-runtime，审批归 permission_gate，绑定归 agent_store。
- **读路径**：用量类聚合优先复用 observability 既有只读接口（`query_trace_events` / `get_usage_summary`，见 observability spec），不绕过 trace query API 直接打 SQLite `traces` 表（与 observability「Usage summary reads through trace API」一致）；本面特有的多指标 / 多维度聚合在 0.x 决策的聚合边界内实现，仍走 store 边界 named params（`:agent_id` / `:start_ts` / `:end_ts` …），禁止 ORM、禁止散落 `sqlite3.connect`。
- **唯二写操作**：导出（CSV / 图片，导出动作本身不落库）与定时报告配置（复用 scheduling 域 `scheduled_tasks`），均写审计。其余全只读。

## 字段就绪度分级（✅ / 🟡 / ⏳）

面板每个指标按数据就绪度分级；⏳ 指标在依赖字段就绪前 UI 以「待数据接入」占位（不报错），字段上线后自动点亮：

| 级别 | 含义 | 示例指标 | 数据来源 |
| --- | --- | --- | --- |
| ✅ | 现有 trace / approvals / 绑定字段直接可出 | 调用次数、活跃用户 / channel / 会话数、token 用量与趋势、时延（avg / P50 / P95）、每会话轮数、按模型 / task_type 分布、审批通过 / 拒绝 / 超时率、绑定数 / 默认 / 来源、per-user token 与频率排行 | `traces`（tokens / elapsed_s / model_used / user_id / agent_name / session_id）、approvals、agent_store |
| 🟡 | 需从 trace 的 `messages` 解析 | Top 工具调用排行、每次运行平均工具数、allowed_tools 覆盖率（已授权未使用） | `traces.messages`（工具调用名从消息解析） |
| ⏳ | 依赖 v1.0 新字段（未就绪 UI 占位） | 成本（`token × 单价`）、终止原因分布、model fallback 触发率、上下文压缩次数、工具失败 / 超时率、skill 命中 Top、memory 命中率、sub_agent 成功率 | observability 补 budget 成本 / 终止码 / 错误分类 / 工具失败·超时 / skill·memory 命中字段；单价来自 model-provider |

- **占位语义**：⏳ 指标卡片显示「待数据接入」，并标注其依赖的字段 / 域；不返回 0、不报错。就绪判定以「该字段是否在 trace payload 中出现」为准（feature-flag / 字段探测，见 0.x）。
- **🟡 解析容错**：从 `messages` 解析工具调用名时，旧 / 不完整 trace 缺字段按「无工具调用」处理，不抛异常（与 observability「Usage payload tolerance」同精神）。

### allowed_tools 覆盖率（🟡，场景 78）

`agent_store` 持有该 agent 的 `allowed_tools` 白名单；本面统计所选周期内从 `messages` 解析到的实际被调用工具集合；**白名单内、实际调用集合外**的工具标为「已授权未使用」，提示可从白名单移除以收窄最小权限。空白名单或周期内无运行时不误报。

## request_id 关联模型（对齐「待决问题」已定结论）

请求级链路依赖 agent-runtime / observability 发射的关联键，本面**只渲染、不发射**：

- **request_id**：agent-runtime 在 `run() / run_stream() / run_sync()` 入口生成 **ULID**（时间可排序），用 **contextvar** 贯穿主循环；所有子事件（工具调用、审批、模型路由、memory、压缩、sub_agent）携带同一 request_id。
- **span_id + trace 树**：sub_agent 继承父 request_id + 自带 span_id，形成 OTel-lite trace 树；本面据此把 sub_agent 子链路就地展开（场景 84），经 `parent_session_id` 关联到父请求节点，子链路与父链路同构。
- **HTTP 路径**：补 `session_id`，使 HTTP 发起的运行也能聚合到会话。
- **历史不回填**：旧 trace 不补 request_id；本面对其走会话级退化。

本面渲染契约：给定 request_id，按 ts 升序拉取该 request_id（及其 span 子树）的全部 trace events，组装事件流；节点原始 JSON 即已脱敏的 trace payload，可一键复制。

### 缺 request_id 的会话级退化（场景 85）

当某次运行未带 request_id（如旧 HTTP trace）：

- 退化到可用关联键 `session_id`，或 `ts + user_id` 时间窗，尽力聚合为一条「请求」。
- 视图顶部提示「该请求缺少完整关联键，链路可能不完整」，**不报错**。
- sub_agent 子链路在退化模式下若 `parent_session_id` 仍可关联则展开，否则降级为「无法关联子链路」提示。

## 成本聚合（⏳，未配单价显示「未配置」）

- 成本 = `token × 模型单价`，单价来自 **model-provider change** 的模型单价表（input / output 每 1k token，已定放 model_router 配置）。
- 某模型**未配置单价**时（自托管 / 自定义模型常无公开价），该模型成本显示「未配置」而非 0；面板对未配置项高亮提醒。
- 单价表整体未上线时，成本指标整体走 ⏳「待数据接入」占位。

## per-user 与下钻（✅）

- **per-user 视图**（场景 76）：选定 agent 下按 `user_id` 聚合各用户 token 用量、调用频率（次数 / 活跃天数）、最近活跃，可排序。
- **反向「按用户」**：选定用户看其在所有 agent 上的用量与频率汇总。
- **下钻维度**（场景 77）：任一指标可沿 用户 / channel / 模型 / 时间 切片；叠加时间范围筛选时数据收敛。
- **请求列表**（场景 82）：从 per-user 下钻到某用户在该 agent（或全部 agent）的请求列表，按时间 / channel 筛选，每条显示时间、入参摘要、token、耗时、结果状态。

## 多 agent 对比（✅，场景 75）

选中多个 agent 切对比视图：同一指标（token 用量、P95 时延等）按 agent 并排展示。聚合查询按 agent_id 分组返回稳定排序（与 observability `by_model` 稳定排序同精神：主指标降序、并列按 agent_id 升序）。

## 权限与脱敏

- `/admin/stats/*` 全部路由复用 `auth.require_role`；**viewer 与 admin 均可只读浏览**（含对比、下钻、请求级链路）。
- per-user 等含个人用量明细按部署方策略可对 viewer **脱敏**（如隐去具体 user 标识、只给聚合分布）；脱敏在序列化层统一处理，不在查询层硬编码。
- 无写操作，唯二例外是导出与定时报告配置；这两类动作写审计（`audit_log.write_audit`）。

## 聚合策略（直接打 traces vs 物化视图，0.x 决策）

- **直接查询**：聚合查询按 agent_id + 时间范围实时打 `traces`（经 trace query API）。实现简单、无额外表、无新鲜度问题；大数据量时延迟可能高。
- **物化 / 缓存表**：把高频聚合（如每日按 agent 的用量 / 时延汇总）预计算落表加速。需走 **Alembic** 建表（不在 store `_init_db()`），named params，路径可 monkeypatch，并定义刷新与失效策略。
- 0.x 先按直接查询起步，物化作为性能优化的可选后续；选型在 0.x 决策。

## 定时报告（复用 scheduling）

按周 / 月把指定 agent 的统计摘要推送到管理员邮箱：复用 `cron_scheduler` / `schedule_store`，报告配置落既有 `scheduled_tasks`，不新建调度机制；邮件发送复用平台既有发送器。报告内容是面板视图的快照摘要。

## 测试隔离（遵循 CLAUDE.md）

- **trace fixture**：构造 `agent_run_completed` / 工具 / 审批 / injected_context / sub_agent 等 trace events 写入隔离 DB，断言聚合数值与 per-user / 下钻 / 对比结果；不发真实 LLM 调用。
- **数据库隔离**：聚合 store 走统一 DB fixture 或 `tmp_path`；若加物化表则 Alembic 迁移后在 `tmp_path` DB 上测。trace 读取经 observability trace query API，遵循其既有隔离。
- **request_id 链路**：构造带 / 不带 request_id 的 trace fixture，断言带 request_id 走 trace 树渲染、缺 request_id 走会话级退化（场景 85）且不报错。
- **sub_agent 子链路**：构造带 `parent_session_id` + span_id 的子 trace，断言就地展开为同构子链路（场景 84）。
- **成本 / 单价**：mock 单价表，断言已配单价按 `token × 单价` 计算、未配显示「未配置」、整体未上线走占位（场景 79）。
- **⏳ 占位**：构造缺 ⏳ 字段的 trace，断言对应指标显示「待数据接入」而非报错或 0（场景 79）。
- **API 层**：用 FastAPI TestClient 测 `/admin/stats/*`——viewer / admin 均可读、无 session 401、per-user 脱敏开关、导出与报告配置写审计；`stats_admin_api` 不 import `agent_loop`，测试可在沙箱 Python 隔离运行。
- 单元测试默认放 `tests/unit/`；涉及 SQLite / Alembic / FastAPI TestClient / trace 聚合契约的放 `tests/integration/`；不向 `tests/` 根目录新增 `test_*.py`。
