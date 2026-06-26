## Context

记忆进入 agent 只有一条路径：每轮回复前 `long_term_ctx.build_context()` 用 `memory.search_facts`（语义向量检索，top-N，limit=10）把**相关**记忆自动注入 prompt。agent 自身没有主动读取记忆的工具。

当用户问"我的所有记忆"时，这个 query 与具体事实（`张洋|works_at=Northstar`）语义不相关，向量召回排不上，再叠加 limit 截断 → agent 看到的"所有"只是被注入的 top-N，实测漏掉整个第三方实体。"列出全部"是**全量列举**需求，与"语义检索相关项"是两种不同操作。

约束：`tools` / `memory` 是 agent 运行时模块，MUST NOT import platform.*；不改 `build_context` 的语义注入；facts 表只读。

## Goals / Non-Goals

**Goals:**
- agent 能在用户要求时**完整、准确**列出某 user_id 名下的记忆（全部 subject，或指定某人）。
- 全量列举不走向量检索、不截断——直接查库返回全部 active facts。
- 与现有 top-N 自动注入并存，互不影响。

**Non-Goals:**
- 不改 build_context 的日常语义注入（相关记忆仍走它）。
- 不引入分页（单用户记忆量级小，全量返回）。
- 不暴露 retracted/archived/superseded（只列 active，即"当前有效记忆"）。

## Decisions

### 决策 1：全量列举是独立查询，不复用 search_facts

`search_facts` 的契约是"语义相关 top-N + access 计数 + 升级"——这些对"列出全部"都是错的（不该按相关性排、不该截断、列举不该刷新 access/触发升级）。因此新增 `list_active_facts(user_id, subject=None)`：纯 SQL 查 `status='active'`，无向量、无 access 副作用，可选 subject 过滤。

### 决策 2：以 agent 工具而非 build_context 意图检测来触发

给 agent 一个 `recall_memory` 工具，由模型判断"用户在要求查看记忆"时调用。替代方案（build_context 检测"列出全部"关键词自动全量注入）被否决：意图靠关键词/启发式判断不稳，且会把全量记忆塞进每一个疑似 query 的 prompt，污染上下文预算。工具让 agent 显式、按需取，且天然支持"查某个人"（subject 参数）。

### 决策 3：user_id 来自 ToolContext.principal，不由模型传

工具按**当前会话的执行身份**取记忆，user_id 取自 `tool_context.principal.user_id`（已是工具记录归属的既定通道），而非让模型把 user_id 当参数传——避免模型臆造/串户。模型只控制可选的 `subject`（"全部"留空，"张三的"传 subject）。principal 缺失（CLI/无身份）时工具返回友好提示，不抛。

### 决策 4：返回结构化文本，subject 分组

工具返回按 subject 分组的可读文本（user 本人 / agent / 各第三方），每条用 fact 的 `statement`（无则回退 `subject relation: object`）。这是给模型读的，分组让它能据此组织回答。空记忆返回明确的"暂无记忆"。

## Risks / Trade-offs

- **[模型不调或滥调工具]** 模型可能该调时不调、或无关时乱调 → 工具描述明确触发场景（"用户要求查看/列出记忆时"）；滥调代价低（只读、无副作用）。
- **[全量返回过大]** 理论上单用户记忆可能很多 → 当前量级小可接受；真出现海量再加上限/分页（Non-Goal，留后续）。
- **[与 top-N 注入重复]** 同一记忆既被 build_context 注入又被工具列出 → 无害，工具是用户显式索取时才调，重复只是信息冗余。
