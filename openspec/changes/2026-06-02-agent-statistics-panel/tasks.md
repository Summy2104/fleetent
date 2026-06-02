> **实施进度（opsx:apply，主体完成）**
> 已按 TDD 实现并通过（沙箱 3.10 + `.pth` UTC shim；不 import agent_loop）：
> - 决策落定：0.2 起步用**纯聚合 + 直接查询**，无物化表/无 Alembic。聚合逻辑放纯函数模块 `stats_store.py`（对 trace 记录列表运算，零 IO，单测覆盖），API 经可注入接缝 `fetch_traces`/`fetch_approvals`/`agent_allowed_tools`/`pricing_table`/`schedule_report` 拉数据。
> - 纯聚合：用量、性能(p50/p95)、Top 工具、allowed_tools 覆盖率(fnmatch)、审批通过/拒绝/超时率、多 agent 稳定排序、per-user 排行、成本(token×单价，未配=未配置，无单价表=待数据接入)、请求列表、按 request_id 事件流、缺 request_id 会话级退化、sub_agent 经 parent_session_id 展开。
> - 管理 API：`stats_admin_api.py`（`/admin/stats/*` 只读）——overview/compare/tools/per-user(viewer 脱敏)/users/{id}/requests/requests/{id}/sessions/{id}/trace 退化/export/reports。viewer+admin 只读，reports 仅 admin。
> - 接线：`server.py` mount。导出/周报写 `audit_log`。
> - 测试：新增 27 个（stats_store 单测 15 + api 12），覆盖场景 74–85；`ruff format/check` 通过。
> - **host follow-up**：`fetch_traces`/approvals/allowed_tools/pricing/schedule 接真实 observability·agent_store·model-provider·scheduling；⏳ trace 字段(终止码/错误分类/fallback/压缩/skill·memory 命中)与 request_id 贯穿由 agent-runtime·observability 发射。
> - **已核查（外部 verify）**：核心聚合(usage/perf/tools/approval/cost/请求列表/事件流/子agent展开)+只读REST+RBAC 实现并通过 27 测试。剩余 NOT-DONE：模型/task_type 分布+绑定事实(3.1/3.2)、维度下钻(3.5/3.6)、⏳字段探测点亮(4.3/4.4)、真 CSV/图片导出(8.1/8.2)、真定时报告接线(8.3/8.4)；fetch_*/pricing_table/schedule_report 均为占位接缝。

## 0. 前置（开放决策，实施前确认）

- [x] 0.1 新模块落点：聚合 API 走新 `stats_admin_api.py`（`/admin/stats/*`，仿 `user_admin_api.py`，复用 `auth.require_role` / `auth.has_role` + `audit_log.write_audit`，**不 import `agent_loop`** 以便 TestClient 隔离）；聚合查询走新 `stats_store.py`（只读聚合边界）还是直接复用 observability 既有读接口——确认边界划法
- [x] 0.2 聚合策略：直接打 `traces` 表（经 trace query API）vs 物化 / 缓存表预计算。起步用直接查询；若加物化表必须走 **Alembic**（不在 store `_init_db()` 建表）、named params（`:x`）、路径可 monkeypatch，并定义刷新 / 失效策略
- [x] 0.3 ⏳ 字段就绪策略：依赖字段（budget 成本 / 终止码 / 错误分类 / 工具失败·超时 / skill·memory 命中 / request_id 贯穿）就绪前以 feature-flag / 字段探测决定指标点亮 vs「待数据接入」占位；确认探测以「该字段是否出现在 trace payload」为准
- [x] 0.4 跨域依赖排期：request_id（ULID + contextvar + sub_agent 继承 + span_id trace 树 + HTTP 补 session_id，历史不回填）在 agent-runtime / observability 实现；⏳ trace 字段在 observability 补；模型单价表在 model-provider change——确认依赖排期与本面占位的衔接
- [x] 0.5 per-user 脱敏策略：viewer 是否对 per-user 明细脱敏由部署方配置项控制，确认脱敏点放序列化层

## 1. stats_store — 用量与性能聚合（① + ② 的 ✅ 部分）

- [x] 1.1 Write failing tests（trace fixture + 隔离 DB）：按 `agent_id` + 时间范围聚合调用次数、活跃 user / channel / session 数、token 用量（prompt / completion / total 总量与均值）、按天 / 周趋势；空范围归 0 不报错
- [x] 1.2 实现 `stats_store` 用量聚合（经 trace query API 读 `agent_run_completed`，named params）
- [x] 1.3 Write failing tests：时延 avg / P50 / P95、每会话平均轮数；缺 elapsed_s 按 0 容错
- [x] 1.4 实现性能聚合（含分位数计算）
- [x] 1.5 Write failing tests：多 agent 对比返回稳定排序（主指标降序、并列按 agent_id 升序）
- [x] 1.6 实现多 agent 对比聚合

## 2. stats_store — 工具与治理（③，🟡 messages 解析 + ✅ approvals）

- [x] 2.1 Write failing tests：从 trace `messages` 解析 Top 工具调用排行、每次运行平均工具数；缺 / 不完整 messages 按无工具调用容错
- [x] 2.2 实现工具调用解析与排行
- [x] 2.3 Write failing tests：allowed_tools 覆盖率——白名单内、周期内实际调用集合外的工具标「已授权未使用」；空白名单 / 无运行不误报
- [x] 2.4 实现 allowed_tools 覆盖率（读 agent_store 白名单 ∩ 解析调用集）
- [x] 2.5 Write failing tests：审批触发数 + 通过 / 拒绝 / 超时率（读 approvals）
- [x] 2.6 实现审批统计聚合

## 3. stats_store — 模型·Skill·绑定 + 下钻 + per-user（④ + ⑤）

- [ ] 3.1 Write failing tests：按模型 / task_type 的调用 / token 分布；绑定数 / 默认 agent / 受管·临管来源分布（读 agent_store）
- [ ] 3.2 实现模型分布 + 绑定事实聚合
- [x] 3.3 Write failing tests：per-user 排行（token / 频率[次数·活跃天数] / 最近活跃，可排序）；反向「按用户」跨 agent 汇总
- [x] 3.4 实现 per-user 与反向汇总聚合
- [ ] 3.5 Write failing tests：任一指标按 用户 / channel / 模型 / 时间 切片，组合筛选数据收敛
- [ ] 3.6 实现按维度下钻聚合

## 4. stats_store — 成本聚合 + 单价缺失语义（① 成本 ⏳）

- [x] 4.1 Write failing tests（mock 单价表）：已配单价按 `token × 单价` 计算；未配单价模型显示「未配置」而非 0；单价表整体未上线走「待数据接入」占位
- [x] 4.2 实现成本聚合（消费 model-provider 单价表 + 未配置 / 未上线分支）
- [ ] 4.3 Write failing tests：⏳ 依赖字段（终止码 / 错误分类 / fallback / 压缩 / 工具失败·超时 / skill·memory 命中 / sub_agent 成功）缺失时对应指标「待数据接入」占位；字段出现后自动点亮
- [ ] 4.4 实现 ⏳ 字段探测 + 占位 / 点亮逻辑（feature-flag / 字段探测，0.3）

## 5. request_trace — 请求列表 + 单请求事件流（⑥ 主链路 + 退化）

- [x] 5.1 Write failing tests（trace fixture）：从 per-user 下钻到用户请求列表（按时间 / agent / channel 筛选），每条含时间 / 入参摘要 / token / 耗时 / 结果状态
- [x] 5.2 实现请求列表聚合
- [x] 5.3 Write failing tests：按 `request_id` 分组、ts 升序组装事件流（用户输入 / 每轮 LLM / 工具入出参 / 审批 / memory / 压缩 / 最终回复）；节点原始 JSON 为已脱敏 payload；本面不发射任何事件
- [x] 5.4 实现单请求事件流渲染聚合（只读，不发射）
- [x] 5.5 Write failing tests：缺 request_id 时退化到 session_id / ts+user_id，提示「链路可能不完整」且不报错（场景 85）
- [x] 5.6 实现会话级退化分支

## 6. request_trace — sub_agent 子链路（⑥ trace 树）

- [x] 6.1 Write failing tests（带 parent_session_id + span_id 的子 trace）：sub_agent 节点就地展开为同构子链路（场景 84）
- [x] 6.2 实现 sub_agent 子链路展开（经 parent_session_id 关联）
- [ ] 6.3 Write failing tests：退化模式下若 parent_session_id 可关联则展开，否则降级为「无法关联子链路」提示而非报错
- [ ] 6.4 实现退化模式下的子链路降级

## 7. stats_admin_api — 只读 REST + 守卫 + 脱敏

- [x] 7.1 Write failing tests（FastAPI TestClient）：无 session 401；viewer 与 admin 均可读总览 / 对比 / 下钻 / 请求级链路；无写端点（除 8.x）
- [x] 7.2 实现 `stats_admin_api`（`/admin/stats/*` 只读路由，复用 `auth.require_role` / `auth.has_role`，不 import `agent_loop`）
- [x] 7.3 Write failing tests：per-user 明细按部署方策略对 viewer 脱敏（隐去 user 标识、保留聚合分布）
- [x] 7.4 实现序列化层脱敏开关
- [x] 7.5 改 `server.py`：mount `stats_admin_api.router`

## 8. 导出 + 定时邮件报告（复用 scheduling）

- [ ] 8.1 Write failing tests：当前视图导出 CSV / 图片
- [ ] 8.2 实现导出（导出动作写审计）
- [ ] 8.3 Write failing tests：配置每周 / 月邮件报告，落 scheduling（`scheduled_tasks`），按周期推送摘要，配置动作写审计；邮件发送器 mock 不发真实邮件
- [ ] 8.4 实现定时报告配置（复用 `cron_scheduler` / `schedule_store`）

## 9. 收尾

- [ ] 9.1 全量 `uv run pytest -x -q` 绿
- [ ] 9.2 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过
- [ ] 9.3 手动冒烟：选 agent 出 ✅ 指标 → 多 agent 对比 → per-user 排行 → 按 channel/时间 下钻 → 成本未配单价显示「未配置」→ ⏳ 字段占位 → 从用户下钻请求列表 → 单请求事件流 → sub_agent 子链路展开 → 缺 request_id 退化 → 导出 + 配置周报 → viewer 只读 + 脱敏
