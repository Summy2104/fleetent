## Why

现行定时任务的投递模型是：**每次触发都跑一整圈 agent loop，然后把 agent 的"最终对话回复"原样广播到目标频道**（`cron_scheduler._fire → _deliver`，`[SILENT]` 哨兵可抑制）。2026-06-11 在 dev-intern 上的实测暴露了这个模型的三个结构性缺陷（均有现场证据）：

1. **"对话回复"被当成"通知"广播——内容无契约**。agent 的回复是写给"对话者"的（含推理、报错、反问），而 cron 触发时刻**没有对话者**。实测中 agent 的故障诊断长文（含"需要我帮您换个方式吗？"的反问）被原样贴进公开频道。自由对话文本直通公开广播，中间没有任何内容契约。
2. **任务状态谎报**。`_record_run` 只看"投递动作"成败（`cron_scheduler.py:138`）：实测中任务意图（发送指定文案）失败、实际发出的是故障报告，但因"故障报告投递成功"而记录 `ok`。系统没有"任务意图是否达成"的语义，失败不可观测。
3. **纯通知任务被迫让 LLM 上关键路径**。"每天 9 点发『开晨会』"这类**内容固定**的任务，也要每次唤醒大模型跑完整 agent loop——引入成本、延迟和概率性失败（模型可能改写文案、自行尝试发送工具、把回复写成别的东西），而它本质是确定性机械活。

围绕"该谁发"的四个设计极端（全由闹钟发 / 全由 agent 发 / 闹钟代发回复 / agent+保底）逐一推演后结论是：**单一投递模型无法同时满足三类任务**。正解是任务分型 + 投递契约。

另一条原则随分型确立：**智能工作做在创建时，触发时只执行确定性动作**。用户口述的糙文案由创建对话中的 agent 优化定稿、经用户确认后冻结入库（创建时刻有对话者、有纠错回路）；触发时刻原样发送（无人在场，不做解释性工作）。

## What Changes

- **`scheduled_tasks` 表新增分型字段**（`AGENT_STATE_MIGRATIONS` 追加一版，forward-only）：
  - `task_type`：`notify` | `generate` | `action`，默认 `generate`（兼容既有语义最近似值）；
  - `notify_text`：notify 型的**定稿通知正文**（创建时优化+确认后冻结）。
- **按型触发语义**（`cron_scheduler._fire` 分流）：
  - `notify`：**不跑 agent**。调度器把 `notify_text` 经 fire 时解析的连接器直发目标。状态 = 投递成败。零 LLM、零成本、确定性。
  - `generate`：跑 agent 产出内容，运行上下文注入**定时任务声明**（"你的最终回复将被原样发布到 <目标>；回复只应是通知正文；无需发布回复 `[SILENT]`；你没有对话对象，不要提问"）；调度器按契约投递回复正文。
  - `action`：跑 agent 执行动作（连接器在手，可中途私信/审批/多目标发送——依赖已落地的 fire 时连接器注入）；**调度器不广播其回复**，最终回复仅记录为运行报告（trace + 任务运行态），不进公共目标。
- **投递契约**（核心不变式）：调度器只投递**被明确指定为通知的内容**——用户定稿的 `notify_text`，或 generate 型按声明产出的回复正文；**永不广播自由对话回复**。
- **状态语义修正**：`last_status` 反映**任务意图**成败（notify：投递成败；generate：运行+投递成败；action：运行成败），不再以"投递动作成功"冒充任务成功。
- **`schedule` 工具扩展**：`create` 增加 `task_type` / `notify_text` 参数与校验（notify 必须有 notify_text + 投递目标；generate/action 必须有 message）；工具描述内置分型判定问题（"内容需要发送当刻才知道的信息吗？"）与创建时定稿流程指引（优化→向用户确认→冻结）。

## Capabilities

### New Capabilities
<!-- 无新增 capability；对 cron-scheduled-tasks 的任务模型与投递语义做结构性修订 -->

### Modified Capabilities

- `cron-scheduled-tasks`：任务模型增加分型（notify/generate/action）与定稿正文；触发语义按型分流（notify 不跑 agent）；新增投递契约（只发显式指定内容，永不广播自由回复）；运行状态改记意图级成败；`schedule` 工具承载分型创建与创建时定稿。

## Impact

- **owning package**：agent 运行时调度域——平铺 `cron_scheduler.py`、`schedule_store.py` + `tools/builtin_tools.py`（schedule 工具）+ `runtime/agent_state_migrations.py`（表迁移）。capability owner：`cron-scheduled-tasks`。
- **public API surface**：`schedule_store.create(...)` 增 `task_type`/`notify_text` 形参；`schedule` 工具 `create` 增同名参数。`CronScheduler` 公共方法签名不变（分流是 `_fire` 内部行为）。无新增跨包 public API。
- **owned tables**：`scheduled_tasks` 新增 `task_type`、`notify_text` 两列（嵌入式 forward-only 迁移追加一版；既有行 `task_type` 默认 `generate` 保持旧语义）。
- **config namespace**：无（沿用 `agent.yaml` `scheduling`）。
- **cross-module dependencies**：不变——`cron_scheduler → im_gateway.connector_registry`（fire 时快照，已有）、`→ runtime.loop`、`→ outbound`。零 platform 触碰（守住 "Scheduled tasks are agent-owned with no platform dependency"）。
- **migration / shim plan**：列级 forward-only 迁移；按项目「上线前不迁移数据」约定不做数据回填（pilot 前无真实持久 cron 数据），默认值兜底。无 import shim。
- **依赖与排序**：依赖热修 change `fix-cron-fire-outbound-connectors`（向 fired run 注入 `outbound_connectors`，修 Jira **AAA-8039**）先行落地；本 change 在其上建立分型语义。本 change 同时收敛 2026-06-11 实测事故（诊断长文广播 + 状态谎报，关联 **AAA-8050** 的可观测性面）。原 Stage-1 设想中的「发过即静默」启发式由 action 型"永不广播"规则取代，不再单独实现（避免一次性检测管线成为弃件）。
