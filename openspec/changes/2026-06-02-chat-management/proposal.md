## Why

`platform.md`「聊天（试运行 + 会话管理）」一节定稿后，后台缺少两个互补的可操作入口，目前都还没有：

1. **没有 admin 试运行 playground**：admin 想验证某个 Agent 的 prompt / 工具 / 知识库召回，只能用真实 `/chat` 链路，会污染该 Agent 的对外用量统计、与真实用户会话混在一起、无法临时改模型 / 停 Skill、也没法快速跳过审批。市面成熟后台（Dify Debug & Preview、Coze Bot 调试、Bedrock Test）都把「调试台」做成一等公民，fleetent 缺这一块。
2. **没有可写的会话治理面**：现有「会话与 trace 浏览」只是**事后只读**回放。运营 / admin 无法接管一段异常的活跃会话、无法以人工身份注入消息兜底、无法强制结束 / 清空 / 重置异常会话、无法批量处置激增会话、也没有带审计的导出入口。
3. **运行语义已就位但缺管理面接缝**：`session_mgr`（并发锁 / 原子持久化 / TTL）、`agent_loop`（while tool-use）、`model_router`（请求级路由覆盖）、`permission_gate`（审批）、`im_gateway`（投递回原平台）都已存在，但没有把它们组织成一个**带角色 / 审计 / 二次确认**的管理面。

本 change 只补**管理面与操作面的可观察、可写行为**：聊天真正运行的 while tool-use 循环 / 模型路由 / 审批仍归 agent-runtime + governance；会话消息的并发锁 / 原子持久化 / TTL 仍归 session；单会话 transcript 的纯只读逐轮回放复用「会话与 trace 浏览」。本面在其上叠加**可交互试运行**与**可写治理干预**。

## What Changes

**ADDED**
- `chat-playground`：admin 选定任一启用中的 Agent 起一段**隔离试运行会话**（标记 `origin=playground`，不计对外用量、不绑真实用户 / channel、可随时丢弃）；SSE 流式回复（语义同 `/chat`）+ 右栏逐轮可观察（命中 Skill / 知识库召回片段、每次工具入参 / 出参、permission_gate 决策、模型路由与 fallback、token 与耗时）；**请求级参数覆盖**（task_type / 模型 / temperature / 启停某些 Skill·知识库，仅作用当前会话）；**受控审批旁路**（仅 `origin=playground` 会话可开「自动批准 medium 风险」，high 仍需显式确认，写审计，绝不波及真实会话）；试运行**留存 / 导出**（固定保存 + 备注、导出 JSON / Markdown，未固定超保留期自动清理）。
- `session-admin-console`：真实会话（web + IM）**列表检索**（按用户 / Agent / channel / 平台 / 时间 / 关键词 / 状态筛排，行显示发起用户、Agent、来源 channel、轮数、最近活跃、token 用量、是否含未决审批）；**逐轮回放**（只读部分复用「会话与 trace 浏览」）；**会话接管**（暂停 agent 自动回复 + 以人工身份注入消息，IM 经 im-gateway 投递回原平台，接管 / 释放写审计）；**强制结束 / 清空 / 重置**（清空委托 session 域 `/new` 语义，高危二次确认 + 写审计）；**批量处置与配额联动**；**导出与留痕**（单 / 批量导出 transcript 写审计，含个人数据按策略二次确认 / 脱敏）；**权限与审计**（写操作仅 admin，viewer 只读）。

**MODIFIED**
- `session-persistence`：`session_mgr` 暴露管理面所需的写钩子——`force_end(session_id)`（标记会话不再接受新轮）、`clear(session_id)`（等价 `/new`，清空上下文）、`inject_message(session_id, role, content)`（人工注入一条消息到 transcript，复用既有 per-session `asyncio.Lock` + 原子写）、以及会话级元数据读写（`origin`、`takeover` 接管态、`pinned` 留存标记）。现有 load/save/锁/隔离语义不变，仅新增受控写入口。

## Capabilities

### New Capabilities

- `chat-playground`
- `session-admin-console`

### Modified Capabilities

- `session-persistence`

## Impact

- **代码**：
  - 新增：`chat_admin_api.py`（FastAPI router，`/admin/chat/*` playground + `/admin/sessions/*` 会话治理，仿 `user_admin_api.py`：`require_role` 守卫 + `audit_log` 写）。
  - 修改：`session_mgr.py`（新增 `force_end` / `clear` / `inject_message` + 会话级元数据 `origin` / `takeover` / `pinned` 读写，复用现有锁与原子写，路径仍可 monkeypatch `SESSIONS_DIR`）；`server.py`（mount `chat_admin_api.router`）。
  - 复用：`auth.require_role` / `has_role`（admin 写 / viewer 只读）、`audit_log.write_audit` / `search_audit`（接管 / 清空 / 强制结束 / 导出均落审计）、`session_mgr` 锁与原子持久化、`eval_logger` trace 供右栏与回放。
- **数据**：`sessions` 元数据新增 `origin`（`web` / `im` / `playground`）、`takeover`（接管态 + 接管 actor + 起止时间）、`pinned`（留存标记 + 备注）、`status`（active / idle / ended）；playground 会话保留期清理标记。新表 / 新列走 Alembic，named params，禁 ORM。
- **跨域 follow-up（本 change 只设计管理面，运行语义交叉引用，依赖以下域配合）**：
  - **session 域**：`session_mgr` 需暴露接管 / 注入 / 强制结束 / 清空钩子与会话级元数据（本 change MODIFIED `session-persistence` 给出契约，实现归 session 域）。清空实际由 session 域执行 `/new` 语义。
  - **agent-runtime 域**：`agent_loop.run` / `run_stream` 需支持 `origin=playground` 标记（不计对外用量）与**请求级参数覆盖**（task_type / 模型 / temperature / Skill·KB 启停，对齐 model-router 的请求级路由覆盖）；并需暴露逐轮可观察事件（Skill / KB 命中、工具入出参、路由 fallback、token / 耗时）供右栏，token 精确用量待 usage 事件就绪。
  - **governance 域**：playground 审批旁路（自动批准 medium）需 permission_gate 支持「仅对 `origin=playground` 会话生效」的受控开关，high 风险仍走显式确认。
  - **im-gateway 域**：人工注入消息需 im-gateway 把消息投递回用户原平台，并对终端用户标注「已转人工 / 已恢复自动」（提示语载体由 im-gateway 域决定）。
- **破坏性**：无。新增管理面路由与 session 元数据列，向后兼容（存量会话 `origin` 默认按来源回填 `web` / `im`，`status` 默认 `active`，`takeover` / `pinned` 为空）。

## Commit 切分建议

每个 commit 自包含、内部 TDD（测试先红 → 实现 → 绿）：

1. `feat(session_mgr): session metadata (origin/status/takeover/pinned) + migration`（1.x）
2. `feat(session_mgr): force_end / clear / inject_message write hooks`（2.x）
3. `feat(chat_admin_api): playground start + SSE + per-request overrides`（3.x）
4. `feat(chat_admin_api): playground approval bypass (playground-only) + audit`（4.x）
5. `feat(chat_admin_api): playground pin / export / retention cleanup`（5.x）
6. `feat(chat_admin_api): session list/search + replay (read reuse)`（6.x）
7. `feat(chat_admin_api): session takeover + human inject`（7.x）
8. `feat(chat_admin_api): force-end / clear / reset + high-risk confirm`（8.x）
9. `feat(chat_admin_api): batch disposal + quota linkage + export audit`（9.x）
10. `feat(chat_admin_api): role guard (admin write / viewer read) + audit search`（10.x）
11. `feat(server): mount /admin/chat + /admin/sessions router`（11.x）
