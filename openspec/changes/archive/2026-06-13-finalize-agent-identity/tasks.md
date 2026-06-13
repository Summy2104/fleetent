# finalize-agent-identity Tasks

> Provisional · confidence 最低（阶段 5 收尾，排在 2/3/4 全落地后）。finalize-time 校准：traces 最终列名、observability 全部相关 requirement（含 agent-observability-view "aggregated by agent_id" 措辞）、消费方实际改名点。TDD：测试先于实现。

## 1. traces 列正名（嵌入式 Y）

- [x] 1.1 [测试] integration：最新 Y 版本下 `traces` 含 `agent_name` 列、不含 `agent_id`；索引由 `idx_traces_agent_ts` 覆盖 `agent_name`；升级路径——旧库列改名、内容（slug）保留（先红）
- [x] 1.2 [实现] `agent_state_migrations.py` 追加新版本（append after 当前 Y 最大、勿硬编码）：`ALTER TABLE traces RENAME COLUMN agent_id TO agent_name` + 索引随动；`TraceEvent`/`TraceQuery` 字段、`query_trace_events()` 参数、消费方（agent_observability / agent_statistics）改名 → 1.1 转绿
- [x] 1.3 [校准] finalize-time：扫 observability / agent-observability-view spec 与代码，把残留 `agent_id`（trace 维度）措辞/字段同步为 `agent_name`

## 2. 读翻译边界固化

- [x] 2.1 [测试] integration：platform 按 `agents.id` 投影某 agent 的 agent 侧 trace/session 时，经 agents 解析 name 正确关联（先红或现态确认）
- [x] 2.2 [实现] read-projection / observability 读路径的 name→id 解析收口；确认无第二处翻译 → 2.1 转绿

## 3. 写翻译边界确认

- [x] 3.1 [测试] integration：materialize 落 agent 产物（目录/agent.yaml/agent 侧 traces 上下文）盖的是 `agents.name`，平台 id 不进 agent 侧（先确认现态/补断言）
- [x] 3.2 [实现] 如有 id 泄漏到 agent 侧的点则收口（多数已如此）

## 4. 守护规则

- [x] 4.1 [测试] unit/integration：守护——① 平台关系表（除 agents）无 agent name 引用列、agent 引用皆 agent_id；② agent 侧无 agent id 标识（含列名）；③ name↔id 翻译只在 materialize / read-projection（先红，逼出残留）
- [x] 4.2 [实现] 清掉守护暴露的残留 → 4.1 转绿

## 5. 文档

- [x] 5.1 `docs/architecture/data-model.md`：§3.3 traces 列名 `agent_id`→`agent_name`；§2/§6 补"两翻译边界 + 身份键守护"；**§3.2 退役 `agents` 条目的"`name` 为不可变标识…创建后不可改"框架**——改为 hybrid 表述（`agents.id` = 不可变身份/关系键、`agents.name` = 可变可读标签，rename 仅改 agents 一行 + re-materialize 重刷产物，零关系级联，见 identity-model §1.2/§2.3），并更新 key-list（admin_state/session_meta 已于阶段 3 改 agent_id 键，name 仅余物理目录/agent.yaml/traces 等 agent 侧产物）
- [x] 5.2 `docs/architecture/agent-identity-model.md`：标阶段 5 收尾完成，全模型落地

## 6. 收尾

- [x] 6.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [x] 6.2 全仓 grep：agent 侧 `agent_id` 标识残留、平台侧（除 agents）agent name 引用残留 清零（迁移历史/归档除外）
- [x] 6.3 `openspec validate finalize-agent-identity` 通过；checkbox 全 `[x]`
