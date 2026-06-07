## Context

`im_gateway/normalizer.route()` 在 `session_lock` 内包住 `load→run→save`（整 run 持锁），调 `agent_loop.run()` 不传 `cancel_token`。`run()`/`run_stream()` 主循环每轮在压缩后、sanitize 前是注入用户消息的安全检查点（已有 loop-warning 注入同位置）。全仓无 per-session 活跃 run 登记表。

## Goals / Non-Goals

**Goals:** IM 路径运行中转向（steer 默认 / interrupt / queue）；loop 轮间被动消费注入；配置进 agent.yaml。

**Non-Goals（暂缓）:** TUI `METHOD_STEER`；`run_stream` 流式落库（TUI steer 持久化）；collect 合并 / 去抖（仅做 cap）。

## Decisions

### D1：登记由输入源做，loop 只被动 drain
`register_run(session_id, token)` 由 normalizer 在启动 run 时调用，把 `RunHandle{token, pending Queue}` 放进 module-level 登记表；`run()`/`run_stream()` 仅在轮间 `steering.drain(session_id)` 取出注入。这样 normalizer 能在调用 run 之前 `is_running` 判定 steer vs 新 turn，而 loop 保持对 steering 无感（无 handle 即 no-op）——契合 agent-loop 不反向依赖输入源。

### D2：注入点 = 压缩后、sanitize 前
与既有 `_maybe_inject_loop_warning` 同位置：晚于压缩（不被同轮压缩吞掉），早于 sanitize（注入后的序列经卫生校验合法）。只在轮间（不在 tool_call↔result 之间）注入，避免破坏序列契约。仅当 run 仍有下一个 turn 时生效——正是"agent 还在干活"的目标场景；已出最终答案则 run 结束、消息走新 turn。

### D3：normalizer 抢锁前分派
`is_running` 在抢 `session_lock` **之前**判定（否则会卡锁退化成 queue）。`steer` 投递成功即回执 return；投递失败（run 刚结束的竞态 / 邮箱满）回退到正常持锁新 turn 路径。`register_run` 在锁内包裹 run（保证一 session 一活跃 run），其 `finally` 必移除 handle 防泄漏。

### D4：默认 steer + 安全
默认 `steering_mode="steer"`（用户拍板，IM 体验最佳）。`steering_max_pending` cap 提供背压（满则拒、回退新 turn），不无界堆积。`reset()` 测试钩子清登记表。

## Risks / Trade-offs

- **[Risk] 末轮竞态丢 steer**：steer 在 run 最后一次 drain 之后、run 结束之前入队 → handle 随 run 结束移除、该条丢失。低频边缘；用户未见效果会重发（成新 turn）。v1 接受并记录。
- **[Risk] interrupt 半途语义**：CancelToken 在轮间/工具 await 检查点才生效，非硬中断；UI 表达"停止中"。
- **[Trade-off] 登记表是 module-level 可变状态**：遵守红线——可 `reset()`、可 monkeypatch 注入，per-session key 隔离。
