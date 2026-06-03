# Design — Chat Management (Playground + Session Admin Console)

## 范围与边界

本 change 只设计**管理面**。运行语义不在此实现，只交叉引用：

| 运行语义 | 归属域 | 本面如何用 |
|---|---|---|
| while tool-use 循环、模型路由、逐轮可观察事件 | agent-runtime（`agent_loop` / `model_router`） | 调用 `run_stream`，转发 SSE + 右栏事件；传 `origin` 与请求级 overrides |
| 工具调用前审批 | governance（`permission_gate`） | playground 受控旁路开关，仅 `origin=playground` 生效 |
| 会话并发锁 / 原子持久化 / TTL | session（`session_mgr`） | 接管 / 注入 / 强制结束 / 清空走 session 暴露的写钩子 |
| 把人工消息投递回原平台 | im-gateway | 注入 IM 会话时委托 im-gateway 投递 + 转人工标注 |
| 单会话 transcript 只读逐轮回放（含 trace 节点） | 「会话与 trace 浏览」 | 回放只读部分复用；本面在其上叠加写操作入口 |

**与「会话与 trace 浏览」的关键边界**：「会话与 trace 浏览」是事后只读审计入口；本面是**运营干预入口**，允许接管 / 注入 / 强制结束 / 清空 / 重置 / 导出等写操作。两者读层共享同一 transcript + trace 渲染，写层只在本面。

## 模块落点

- 新模块 `chat_admin_api.py`：FastAPI `APIRouter(prefix="/admin")`，两组路由 `/admin/chat/*`（playground）与 `/admin/sessions/*`（会话治理）。仿 `user_admin_api.py`：登录会话解析 → `auth.has_role` / `require_role` 守卫（写要求 admin，读放行 viewer）→ 操作 → `audit_log.write_audit`。
- `session_mgr` 扩展（MODIFIED `session-persistence`）：在既有 `load` / `save` / `session_lock` / `SESSIONS_DIR` 之上新增受控写钩子与会话级元数据，**不改**现有 load/save/锁/隔离语义。

## Playground 隔离模型

- **`origin=playground` 标记**：playground 起的会话写入 session 元数据 `origin=playground`。该标记贯穿全链路：
  - **不计对外用量**：agent-runtime 见 `origin=playground` 不把本次 token / 调用计入目标 Agent 的对外用量统计（与「用量与配额」域口径一致）。
  - **不绑真实用户 / channel**：playground 会话只关联发起 admin，不写 `user_agents` / `channel_agents` 绑定，不出现在「用户会话管理面」的真实会话列表。
  - **可丢弃 + 保留期清理**：未 `pinned` 的 playground 会话超过保留期由定时清理（复用 scheduling 域）按 `origin=playground AND pinned IS NULL AND updated_at < now - retention` 删除其 session 文件与元数据。
- **请求级参数覆盖**：playground 发消息时可临时覆盖 `task_type` / 模型 / `temperature` / 启停某些 Skill·KB，**仅作用当前会话**，作为请求级 overrides 透传给 `agent_loop.run_stream`（对齐 model-router 的请求级路由覆盖）。Agent 持久配置不变，其他会话不受影响——覆盖项只存在于本次请求 / 本 playground 会话上下文，不落 Agent 定义表。
- **受控审批旁路**：playground 会话默认仍走 permission_gate。admin 可对**自己的** playground 会话开启「自动批准 medium 风险」，该开关：
  - 仅对 `origin=playground` 会话生效（实现层把开关随请求传入 governance，governance 校验 `origin==playground` 才放行 medium）；
  - high 风险仍需显式确认；
  - **每次自动放行写审计**（`action=playground_bypass_medium`，记 actor / session / 工具 / 风险等级）；
  - 绝不波及真实用户会话——真实会话即便同时触发 medium，仍正常进入 permission_gate 等待审批。
- **留存与导出**：
  - 固定（pin）：把一段满意 / 有问题的 playground 会话 `pinned=1` + 备注，免于保留期清理。
  - 导出：JSON（完整结构化 transcript + 右栏可观察）/ Markdown（人读），供回归对照；导出写审计。

## 会话治理（session-admin-console）语义

- **列表与检索**：从 session 元数据 + trace（`eval_logger`）聚合真实会话（`origin in {web, im}`，排除 playground）。按用户 / Agent / channel / 平台 / 时间 / 关键词 / 状态（active / idle / ended）筛排，行展示发起用户、Agent、来源 channel、轮数、最近活跃、token 用量、是否含未决审批。
- **逐轮回放**：只读部分复用「会话与 trace 浏览」（transcript + 工具调用 + permission_gate 决策 + 模型路由 + memory/KB 命中）；本页在其上叠加写操作入口。
- **会话接管（人工干预）**：
  - 接管：写 session 元数据 `takeover={actor, started_at}`，**暂停 agent 自动回复**——后续该会话新轮在路由前检查 `takeover` 非空则不触发 `agent_loop`，等待人工。
  - 人工注入：admin 以人工身份调用 `session_mgr.inject_message(session_id, role="assistant"|"human_agent", content)`，把消息写入 transcript（复用 per-session 锁 + 原子写）。IM 会话经 im-gateway 投递回 Alice 所在平台。
  - 释放：清空 `takeover`，恢复 agent 自动回复。
  - 接管与释放均写审计；对终端用户标注「已转人工 / 已恢复自动」（提示语载体由 im-gateway 域决定）。
- **强制结束 / 清空 / 重置**：
  - 强制结束：`session_mgr.force_end(session_id)` 置 `status=ended`，不再接受新轮。
  - 清空：`session_mgr.clear(session_id)` **等价 im-gateway 的 `/new`**，由 session 域执行实际清空，会话后续从空上下文开始。
  - 重置到某一轮之前：截断 transcript 到指定轮（session 域执行原子写）。
  - 均为高危动作，**二次确认 + 写审计**。
- **批量与配额联动**：可按筛选结果批量结束 / 清空异常会话（逐条审计 + 关联批次 ID）；列表展示各会话 token 用量并与「用量与配额」联动，便于定位异常激增会话。
- **导出与留痕**：单 / 批量导出 transcript（JSON / Markdown），导出写审计；含个人数据的导出按部署方策略可要求二次确认 / 脱敏。

## 权限与审计

- 守卫复用 `auth`：`/admin/chat/*`、所有 `/admin/sessions/*` 写操作要求 `role in {admin, built_in_admin}`；viewer 仅可 GET 会话列表 / 回放（写端点对 viewer 返回 403、UI 隐藏入口）。
- 高危动作（接管 / 注入 / 强制结束 / 清空 / 重置 / 含个人数据导出）要求二次确认（沿用 user-management 的 2FA / 二次确认机制）。
- 所有写操作落 `audit_log`：谁 / 何时 / 对哪个会话 / 做了什么（`action ∈ {playground_bypass_medium, session_takeover, session_release, session_inject, session_force_end, session_clear, session_reset, session_export, session_batch_*}`）。

## 数据模型

session 元数据（随 session 文件或 `sessions` 元数据表，走 Alembic、named params、禁 ORM）：

- `origin`：`web` / `im` / `playground`（存量按来源回填）。
- `status`：`active` / `idle` / `ended`（默认 `active`）。
- `takeover`：接管态（actor_user_id + started_at；空表示自动回复中）。
- `pinned`：留存标记（bool + 备注，仅 playground 用）。

清空 / 重置 / 强制结束的实际 transcript 写入仍由 session 域原子完成，本面只调钩子 + 写审计。

## 测试隔离（遵循 CLAUDE.md）

- **路径隔离**：`monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")`；session 元数据库 monkeypatch `DB_PATH` 到 `tmp_path`（迁移前 legacy 模式）或用统一 DB fixture。绝不触碰 `data/`。
- **LLM / SSE mock**：playground 流式测试 mock `model_router.get_async_client_and_config` 或 patch `agent_loop.run_stream` 产出固定事件序列，断言 SSE 帧 + 右栏可观察字段；不发真实模型调用。
- **审批旁路**：注入 governance 桩，断言 `origin=playground` + 旁路开关时 medium 自动放行并写审计；构造并行的真实会话桩，断言其仍进 permission_gate（旁路不波及）。
- **接管 / 注入 / im-gateway**：mock im-gateway 投递器，断言被以正确平台 / 收件人调用；不发真实 IM。
- **HTTP 守卫**：FastAPI `TestClient`，覆盖无 session 401 / viewer 写 403 / admin 放行；分层归 `tests/integration/`（多模块 + FastAPI），纯 store 钩子单测归 `tests/unit/`。
- **审计断言**：每个写操作后断言 `audit_log` 落一条且字段（actor / action / target / detail）正确。
