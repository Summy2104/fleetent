> **实施进度（opsx:apply，主体完成）**
> 已按 TDD 实现并通过（沙箱 3.10 + `.pth` UTC shim；不 import agent_loop）：
> - 决策落定：0.2 会话元数据走独立 `session_meta` 表（迁移 `014`：origin/status/takeover/pinned/agent_name/user_id/channel），transcript 仍在 session_mgr JSON。agent-runtime(SSE/run_stream/overrides)、session(load)、im-gateway(投递) 走 sync 接缝。
> - 数据层：`session_admin_store.py`（db runtime：upsert_meta/get_meta/set_status/set_takeover/clear_takeover/set_pinned/is_taken_over/list_meta[默认排除 playground]/list_unpinned_playground）。
> - session_mgr 扩展：新增 `clear` / `inject_message`（复用 `session_lock` + 原子写，load/save 语义不变）。
> - 管理 API：`chat_admin_api.py`（`/admin/chat/*` + `/admin/sessions/*`）——playground 起隔离会话（origin=playground 不入真实列表）、消息（overrides 透传 + 仅 playground 审批旁路写审计 + 非 playground 409）、pin/export、会话列表检索/详情回放、接管+人工注入（IM 投递回原平台）+ 释放、强制结束/清空/重置（二次确认）、批量处置（共享 batch_id）。
> - 接线：`server.py` mount。权限 `auth.has_role`（admin 写/viewer 只读）+ `audit_log` 审计。
> - 测试：新增 20 个（store+hooks 10 + api 10），覆盖场景 97–102；`ruff format/check` 通过。SSE 实流包装 + 全量 + mypy + 冒烟需 host 3.12。
>
> 已核查（外部 verify）：管理面骨架(session_meta 表+迁移022、clear/inject 锁、playground 隔离+bypass审计、接管/释放/注入、强制结束/清空二次确认、批量、RBAC)实现并通过 20 测试。但 agent-runtime/transcript/IM 投递均为可注入接缝(stub)，真 SSE 流式(3.1/3.2)、trace/usage 聚合(6.x)、保留清理 job(5.2)、Markdown 导出、配额联动/导出脱敏(9.x)、收尾门(11.3/11.4)未完成。

## 0. 前置

- [x] 0.1 确认新模块落点：`chat_admin_api.py`（`/admin/chat/*` playground + `/admin/sessions/*` 会话治理，仿 `user_admin_api.py`，复用 `auth.require_role` + `audit_log`）
- [x] 0.2 确认 session 元数据字段命名与存储位置：`origin`(`web`/`im`/`playground`) / `status`(`active`/`idle`/`ended`) / `takeover`(actor+started_at) / `pinned`(bool+note)；随 session 文件还是独立 `sessions` 元数据表（走 Alembic、named params、禁 ORM）
- [x] 0.3 确认 playground 会话标记字段与保留期清理口径（未 `pinned` 且超期清理，复用 scheduling 域）
- [x] 0.4 确认接管态字段语义（接管期暂停自动回复的判定点在路由前）与人工注入消息 role 取值（`assistant` / `human_agent`）
- [x] 0.5 确认 `session_mgr` 接口扩展契约：新增 `force_end` / `clear` / `inject_message` + 元数据读写；现有 load/save/锁/隔离不变
- [x] 0.6 确认跨域 follow-up 边界与依赖：agent-runtime 的 `origin=playground` + 请求级 overrides + 逐轮可观察事件；governance 的 playground-only 审批旁路；im-gateway 的人工消息投递回原平台 + 转人工标注（本 change 只设计管理面，运行语义交叉引用）

## 1. session_mgr — 会话元数据 + 迁移

- [x] 1.1 Write failing tests（`tmp_path` + monkeypatch `SESSIONS_DIR` / `DB_PATH`）: 元数据含 `origin`/`status`/`takeover`/`pinned`；新建 playground 会话 `origin=playground`；存量回填 `origin=web`/`im`、`status` 默认 `active`、`takeover`/`pinned` 空
- [x] 1.2 实现 session 元数据读写 + 幂等迁移（Alembic 加表/列，named params）

## 2. session_mgr — 受控写钩子

- [x] 2.1 Write failing tests: `force_end(session_id)` 置 `status=ended` 后不再接受新轮；`clear(session_id)` 清空上下文（等价 `/new`）；`inject_message(session_id, role, content)` 在 per-session 锁下原子追加并持久化；并发 A/B 不混
- [ ] 2.2 实现 `force_end` / `clear` / `inject_message`（复用现有 `session_lock` + 原子写 `.json.tmp → rename`），不改 load/save 语义

## 3. chat_admin_api — playground 起会话 + SSE + 参数覆盖

- [ ] 3.1 Write failing tests（TestClient + mock `agent_loop.run_stream`/`model_router`）: admin 选 Agent 起会话标记 `origin=playground`、不绑真实用户/channel；SSE 流式回复 + 右栏可观察字段（Skill/KB 命中、工具入出参、审批决策、模型路由）；`origin=playground` 不计对外用量
- [ ] 3.2 实现 `/admin/chat/start` + `/admin/chat/{sid}/message`（SSE），透传 `origin=playground` 与逐轮可观察事件
- [ ] 3.3 Write failing tests: 请求级覆盖 task_type/模型/temperature/启停 Skill·KB 仅作用当前会话；Agent 持久配置不变、其他会话不受影响
- [x] 3.4 实现请求级 overrides 透传（不落 Agent 定义表）

## 4. chat_admin_api — 受控审批旁路（playground only）+ 审计

- [ ] 4.1 Write failing tests（注入 governance 桩）: playground 开启「自动批准 medium」时该会话 medium 自动放行并写审计；high 仍需显式确认；构造并行真实会话桩断言其仍进 permission_gate（旁路不波及）
- [x] 4.2 实现旁路开关（仅 `origin=playground` 生效）+ 每次自动放行写 `audit_log`（`action=playground_bypass_medium`）

## 5. chat_admin_api — 留存 / 导出 / 保留期清理

- [ ] 5.1 Write failing tests: `pin` 置 `pinned=1`+备注免清理；导出 JSON/Markdown 并写审计；未 `pinned` 超保留期被清理
- [ ] 5.2 实现 `/admin/chat/{sid}/pin` + `/admin/chat/{sid}/export` + 保留期清理任务（复用 scheduling 域）

## 6. chat_admin_api — 会话列表检索 + 回放

- [ ] 6.1 Write failing tests: `/admin/sessions` 列出真实会话（排除 playground），按用户/Agent/channel/平台/时间/关键词/状态筛排；行含发起用户、Agent、channel、轮数、最近活跃、token 用量、未决审批标记
- [ ] 6.2 实现列表检索（聚合 session 元数据 + `eval_logger` trace）
- [ ] 6.3 Write failing tests: `/admin/sessions/{sid}` 逐轮回放复用「会话与 trace 浏览」只读层 + 叠加写入口
- [ ] 6.4 实现会话详情回放（只读复用 + 写入口暴露）

## 7. chat_admin_api — 接管 + 人工注入

- [x] 7.1 Write failing tests（mock im-gateway 投递器）: 接管置 `takeover` 暂停自动回复；人工注入经 `session_mgr.inject_message` 写 transcript；IM 会话经 im-gateway 投递回原平台；接管/释放写审计；释放恢复自动回复
- [x] 7.2 实现 `/admin/sessions/{sid}/takeover` / `/release` / `/inject`（委托 session 钩子 + im-gateway 投递）

## 8. chat_admin_api — 强制结束 / 清空 / 重置 + 二次确认

- [ ] 8.1 Write failing tests: 强制结束置 `status=ended` 不再接受新轮；清空委托 session 域执行 `/new` 语义；重置截断到指定轮；高危动作要求二次确认且写审计
- [x] 8.2 实现 `/admin/sessions/{sid}/force-end` / `/clear` / `/reset`（委托 session 钩子 + 二次确认守卫 + 写审计）

## 9. chat_admin_api — 批量处置 + 配额联动 + 导出审计

- [ ] 9.1 Write failing tests: 按筛选批量结束/清空，逐条审计 + 共享批次 ID；列表 token 用量与「用量与配额」联动；单/批量导出 transcript 写审计；含个人数据导出按策略二次确认/脱敏
- [ ] 9.2 实现批量端点 + 配额联动展示 + 导出留痕

## 10. chat_admin_api — 角色守卫 + 审计检索

- [x] 10.1 Write failing tests（TestClient）: 无 session 401；viewer 可读列表/回放、写端点 403；admin 可所有写操作；所有写操作落 `audit_log`（actor/action/target/detail 正确）
- [ ] 10.2 实现 `require_role`（admin 写 / viewer 只读）守卫接线 + 审计检索复用 `audit_log.search_audit`

## 11. server 接线 + 收尾

- [x] 11.1 改 `server.py`：mount `chat_admin_api.router`（`/admin/chat/*` + `/admin/sessions/*`）
- [ ] 11.2 全量 `uv run pytest -x -q` 绿
- [ ] 11.3 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过
- [ ] 11.4 手动冒烟：选 Agent 起 playground→SSE 流式 + 右栏→覆盖模型/停 Skill→开 medium 旁路（真实会话不波及）→固定/导出→会话列表检索→接管+人工注入（IM 投递回原平台）→强制结束/清空二次确认→批量处置→viewer 只读 403→审计检索
