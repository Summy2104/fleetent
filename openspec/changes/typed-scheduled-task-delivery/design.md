## Context

现行触发链（`cron_scheduler.py`）：

```python
reply = await _agent_run(messages=[{"role":"user","content": task["message"]}], ...)
delivery_error = await _deliver(task, reply, connectors)      # 回复原样投递到 origin/deliver
_record_run(task, now, "error" if delivery_error else "ok")   # 只看投递动作成败
```

2026-06-11 dev-intern 实测事故链：任务"到点发送指定文案" → fired run 内发送工具不可用（连接器未注入，另案热修）→ agent 把回复写成故障诊断长文（含对频道的反问）→ `_deliver` 把诊断长文**成功**贴进公开频道 → `_record_run` 记 `ok`。每一层"成功"，任务意图失败且不可观测。

设计讨论穷举了四个极端并逐一否决/吸收：

| 极端 | 判定 | 理由 |
|---|---|---|
| A. 全由闹钟发（不跑 agent） | 仅对内容固定的任务成立 | 中途交互（审批 DM 等回应）、非文本（文件）、发后视结果行动，时序上只能发生在运行中——结束后投递替代不了 |
| B. 全由 agent 发（闹钟不发） | 否决 | 投递取决于模型自觉 → **静默丢失**（"发送'X'"任务模型常直接把 X 当回复文本而不调工具）；漏发不可见，恰是调度系统最致命失败模式 |
| C. 闹钟代发"最终回复"（现状） | 否决 | 对话回复 ≠ 通知：无内容契约（事故实证）、无对话者却会反问、状态谎报 |
| D. agent 产出结构化投递清单、闹钟执行 | 否决 | 等于用更脆的自定格式重造工具调用；清单要覆盖文件/表情/条件发送会膨胀成第二套工具协议 |

A 的成立域 + B 的成立域 + C 的保底直觉 = 三类任务，强行共用一个模型即是病根。

## Goals / Non-Goals

**Goals**
- 任务分型：`notify` / `generate` / `action`，各自有明确的投递责任人与失败语义。
- 投递契约：调度器只投递显式指定为通知的内容，永不广播自由对话回复。
- 纯通知任务移出 LLM 关键路径（确定性、零成本、零概率失败）。
- 创建时定稿：糙文案在创建对话中由 agent 优化、用户确认、冻结入库；触发时只执行。
- 状态语义反映任务意图成败。

**Non-Goals**
- 不改 APScheduler 接线、schedule_kind（cron/once/interval）、missed-run 语义。
- 不引入新投递通道（仍走 fire 时 `connector_registry` 快照 + `outbound.send_to`）。
- 不做存量任务数据迁移（上线前不迁移数据约定；默认值兜底）。
- fired run 的连接器注入本身属先行热修 `fix-cron-fire-outbound-connectors`，不在本 change 重复。

## Decisions

### D1. 三型语义

| | notify | generate | action |
|---|---|---|---|
| 触发时跑 agent | **否** | 是 | 是 |
| 投递内容 | `notify_text` 原样 | agent 回复正文（按声明产出） | **不广播**；agent 用工具自行发送 |
| 投递责任人 | 调度器 | 调度器 | agent |
| `[SILENT]` | 不适用 | 适用（跳过投递） | 不适用（本就不广播） |
| `last_status` 含义 | 投递成败 | 运行+投递成败 | 运行成败 |
| 典型 | 固定文案提醒 | 周报汇总发频道 | 巡检→条件私信→审批升级 |

### D2. 创建时定稿（compile-time vs runtime）

判定问题（内置进 `schedule` 工具描述，由创建对话中的 agent 执行）：**"这条消息的内容，需要发送当刻才知道的信息吗？"** 否 → notify：agent 在创建对话里把用户糙话优化成正文、回显确认（"将于每天 9:00 发送：『…』"）、定稿存 `notify_text`。是 → generate/action。

原则依据：创建时刻**有对话者**（用户在场，写歪当场纠正）；触发时刻**无对话者**（解释性/生成性工作的任何偏差都无人拦截）。同一原则同时解释了为什么 generate 型要注入"你没有对话对象，不要提问"的声明。

### D3. generate 型的运行声明（内容契约的运行时载体）

fired run 的消息序列前注入固定声明（实现为 system 注记或用户消息前缀，与 im-message-context 的注入机制同段位）：

> [定时任务上下文] 你的最终回复将被原样发布到 <platform>:<target>。回复只应包含要发布的通知正文；无需发布时仅回复 `[SILENT]`。本次运行没有对话对象，不要提问、不要输出面向操作者的说明。

### D4. action 型不广播 + 运行报告去向

action 型最终回复只落 trace 与任务运行态（`last_error` 携带摘要），不进公共目标——公开频道里出现"运行报告"正是事故形态。后续如需"报告私发任务属主"，在 `deliver` JSON 加 `report_to_owner` 扩展位，本 change 不做。

「发过即静默」启发式（检测 run 内成功 outbound 后抑制广播）被本分型**结构性取代**：action 永不广播、generate 按契约只广播正文、notify 无 run——不再需要发送检测管线。

### D5. schema

`AGENT_STATE_MIGRATIONS` 追加一版：

```sql
ALTER TABLE scheduled_tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'generate';
ALTER TABLE scheduled_tasks ADD COLUMN notify_text TEXT;
```

`message` 语义维持"给 agent 的提示词"（generate/action）；notify 型 `message` 可存用户原话（审计），`origin` 仍记创建上下文。store 层校验：notify 必有 `notify_text` 且可解析投递目标；generate/action 必有 `message`。

## Risks / Trade-offs

- **分型判定错误**（agent 把该 generate 的建成 notify）：创建时定稿回显给了用户当场纠错的机会；`schedule(action="list")` 可见类型，可改建。
- **generate 型仍依赖模型遵守声明**：契约从"无"提升到"显式声明 + 单一输出通道"，但非硬隔离；硬化（如回复结构化校验）留待后续评估，不阻塞本步。
- **行为变更面**：默认 `generate` 与现状最接近，但"广播任意回复"收紧为"按声明产出的正文"——属修复事故面的有意收紧，在 PR 描述中显式标注。
- 兼容：`run_now`、pause/resume、missed-run、fire-time revalidation 与三型正交，路径不变。

## Test strategy（TDD，红→绿）

- **migration（integration）**：新版打开旧库 → 两列存在、默认值正确；`schedule_store.create` 携带/校验新字段。
- **notify 直发（unit）**：fake connector + notify 任务 fire → `outbound.send_to` 收到 `notify_text` 原样；**`agent_loop.run` 未被调用**（monkeypatch 断言）；投递失败 → `last_status="error"`。
- **generate 契约（unit）**：fire → `loop.run` 收到的消息序列含定时任务声明；回复经 `_deliver` 投递；`[SILENT]` 跳过。
- **action 不广播（unit）**：fire → `_deliver` 不被调用（或被调用但按型短路）；回复落 `_record_run`/trace。
- **schedule 工具（unit）**：`create(task_type="notify")` 无 `notify_text` → 校验错误字符串；带 → 入库；默认 `generate` 兼容旧调用。
- **状态语义（integration）**：三型各一条意图失败路径 → `last_status` 如实为 `error`。
- 收尾：`make test-pr` + `tests/integration` 对照 main 基线无新增失败。
