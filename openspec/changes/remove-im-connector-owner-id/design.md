## Context

agent IM 链路里的 `owner_id` 从两个 supervisor 线程化下来：

```
SlackSupervisor/_run → runner(agent_name, owner_id, config)
  → slack.run(agent_name, owner_id, config) → create_app(agent_name, owner_id, config)
    → NormalizedMessage(owner_id=owner_id) → normalizer.route
      → session_id = f"{owner_id}:{session_id}"   # 372 / 446，全链路唯一消费点
```

`owner_id` 的值来自 `supervisor._owner_id_provider()`，默认 `user_store.admin_owner_id` →
`SELECT … FROM users …`。standalone 无 `users` 表 → 启动即崩。

两个事实定调全量移除：

1. **owner 前缀无活的生产者**：注释称前缀防「同一 channel 跨两 owner 串会话」，但 platform 已不启动
   IM 连接器（`server.py` 注释 + `ConnectorManager(factories={})` 空工厂），全仓唯一造 `NormalizedMessage`
   的是 `slack.py`/`telegram.py`（standalone 单 owner）。multi-owner 命名空间是死语义。
2. **owner_id 对 agent 无其它用途**：access gate / Principal / 审批 / 记忆全走 `msg.user_id`；owner_id
   不落库、不被解析回。

## Goals / Non-Goals

**Goals**
- standalone 启动 Slack/Telegram 连接器在「无 `users` 表」下成功，零 platform 表读取。
- 去掉 session_id 的 owner 前缀。
- 从链路彻底移除 owner_id（supervisor / adapter / NormalizedMessage），删除 `im_gateway → user_store`
  反向 import。

**Non-Goals**
- 不动 `user_store.admin_owner_id`（platform 域保留）。
- 不动 platform `im_gateway_management` 的 owner_id（`im_connectors`/`im_users` 多 owner 键，独立概念）。
- 不引入新的 session 命名空间机制（若将来需多 owner 隔离，另行设计）。

## Decision

把 `owner_id` 从 agent IM 连接器链路整条删除：

- `Runner` 签名 `(agent_name, owner_id, config)` → `(agent_name, config)`；`_run()` →
  `await runner(agent_name, config)`；删 `owner_id_provider` 参数 / `_owner_id_provider` / `user_store` import。
- `slack.run/create_app`、`telegram.run/create_app` 去 `owner_id` 形参；`NormalizedMessage(...)` 去 `owner_id=`。
- `NormalizedMessage` 删 `owner_id` 字段；372/446 → `session_id = msg.session_id`。

session_id 由 `f"{owner}:{sid}"` 变为 `sid`。standalone 单 owner 下不影响会话区分度（`_derive_session_id`
已含 channel_type/channel_id/user_id/thread_root）。

## Alternatives considered

- **A：默认 owner_id_provider 改 `SYSTEM_OWNER_ID` 哨兵（不删前缀）。** 修了崩溃但留一个谁都不用的
  owner_id 继续线程化、session_id 仍带常量前缀 `__system__:`。否决：留死值与死语义，且未达成「去前缀」目标。
- **B（采纳）：整条移除 owner_id + 去前缀。** 既修崩溃又清死代码，`im_gateway` 默认零 platform 依赖。
- **C：让 `admin_owner_id`/`get_builtin_admin` 容忍缺表。** 否决：把越界藏进 user_store 异常处理，
  不解决「agent 运行时读 platform 表」根本问题，且改共享 user_store 行为面更大。

## Risks / Trade-offs

- **未来需要多 owner 会话隔离**：当前无此路径；真要时按届时需求重做命名空间（不复活 admin_owner_id 这条）。
- **旧会话格式变更**：带 `owner:` 前缀的旧 IM 会话文件失配 → 作孤儿。standalone Slack 此前持续崩、
  无有效历史；按「上线前不迁移数据」约定可接受。
- **public 形参/字段变更**：`Runner`/`run`/`create_app`/`NormalizedMessage` 均 im_gateway 内部协作面，
  platform 不引用该形参/字段（已 grep 确认）；测试同步更新即可。

## Test strategy（TDD）

- **unit（红→绿）**：
  - `SlackSupervisor()` / `TelegramSupervisor()` 注入 fake runner，`await start(agent)` 后断言 runner 以
    `(agent_name, config)` 两参被调；构造/调用全程不触 `user_store`（monkeypatch `user_store.admin_owner_id`
    抛错断言不被触发）。当前 3 参签名 + 默认 admin_owner_id → 见红。
  - `slack._handle` / assistant 路径产出的 `NormalizedMessage` 无 `owner_id` 字段；`normalizer` 路由后
    `session_id == msg.session_id`（无 owner 前缀）。当前带前缀 → 见红。
- **回归**：改写 `test_im_adapter_owner.py` 为只断言 `agent_name`/`user_id`（owner 线程化已移除）。
- **门禁**：`make test-pr` + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）。
