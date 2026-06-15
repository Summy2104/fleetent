## Why

用户用自然语言（如"北京时间 18:00"）反复创建定时任务，模型连续把触发时间设错 8 小时、`task_type` 也选错，任务到点不触发或卡审批超时。根因不是模型能力，而是 `schedule` 工具的使用契约**没有通过工具 schema 交付给模型**：工具描述只剩 docstring 首行（其余 23 行指引被 `schema_builder` 丢弃），15 个参数全是无描述、无枚举的裸类型，且 `timezone` 默认硬编码 `"UTC"`，短路了 `cron-scheduled-tasks` 既有 spec 已要求的部署默认时区回退。模型因此对"cron 字段按哪个时区解释""`task_type` 怎么选""时区怎么填"一无所知，只能猜——而它的猜法（把本地时间预转 UTC、又标本地时区）必然差 8 小时。

## What Changes

- **schedule 工具参数契约对模型可见**：`action`/`schedule_kind`/`task_type`/`notify_target_type` 改用 `Literal` 暴露合法枚举值；全部参数补 `Annotated` 描述（沿用 `builtin-web-tools`/`builtin-file-tools`/`builtin-shell-tool` 既有约定，`tool-schema-builder` 已支持 `Annotated[Literal[...], "desc"]` → enum + description）。模型从此能看到 `task_type` 的三个值与选择判据、`schedule_kind` 的合法值。
- **时区契约明确、模型零算术**：`timezone` 描述写明 `cron_expr` 按该时区的**本地钟面时间**填写、**绝不预转 UTC**；留空则用部署默认时区，仅当用户点名其它时区时才填。模型只照抄用户说的钟面时间 + 写时区名。
- **去掉 timezone 硬编码默认**：工具 `timezone` 默认 `"UTC"` → `""`（未指定）；`create` 把空值下传为 `None`，使 `cron_scheduler._register` 既有的 `task.get("timezone") or default_timezone` 回退真正生效。解析优先级：**显式 per-task 时区 > `agent.scheduling.default_timezone` > UTC 兜底**。
- **本地存储、DST 安全**：cron 表达式 + 时区原样存储，**不在创建时转 UTC**——周期任务由 APScheduler 按时区每次触发、自动跟随夏令时（避免 UTC 归一化在跨时区 DST 地区漂移）。
- **创建回执反馈**：`schedule(action="create")` 成功后回显下次触发时间（任务时区 + UTC 双显），并回填 `next_run_at`，让模型与用户当场发现转错。`once`/`run_at` 一次性任务同理。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cron-scheduled-tasks`: 为 `schedule` 工具新增 model-facing 参数契约（`Literal` 枚举 + `Annotated` 描述）；明确时区解析契约（本地钟面填写、不预转 UTC、空值走部署默认、优先级链、本地+时区存储 DST 安全）；`create` 返回下次触发时间（任务时区 + UTC）并回填 `next_run_at`。

## Impact

- **代码**：
  - `src/fleetent/tools/builtin_tools.py` — `schedule` 签名改 `Annotated`/`Literal`；`create` 分支把 `timezone or None` 下传，并在成功回执中加入下次触发时间。
  - `src/fleetent/cron_scheduler.py` — `create` 路径计算并返回 APScheduler job 的 `next_run_time`；`timezone` 空值回退到 `default_timezone`（`_register` 既有逻辑，确认空值能落到它）。
  - `next_run_at` 回填复用既有 `schedule_store.update_run_state`，**无 DB schema 变更**。
- **依赖**：复用既有 `tool-schema-builder` 的 `Annotated`/`Literal` 支持，**不改 schema_builder**。
- **无 platform 改动、无 Alembic/embedded 迁移、无新依赖**；调度器内核、store schema、delivery 语义均不动。
- **部署**：on-prem 部署可在 `agent.yaml` 配 `scheduling.default_timezone`（如 `Asia/Shanghai`）一次性设定本地默认。
- **行为变更（非破坏性）**：模型创建任务时未指定时区的默认从"硬编码 UTC"变为"部署默认时区"；未配置 `default_timezone` 的部署仍是 UTC，既有显式带 `timezone` 的任务不受影响。

## Out of Scope

- `schema_builder` 只取 docstring 首行的系统性截断（18/23 工具受影响）——风险面大，另案处理；本 change 仅让 `schedule` 改用 `Annotated`/`Literal` 这一既有可达通道。
- per-user 时区映射存储（用户档案加 tz 字段）——经确认 per-task 指定即可，不做。
- 用 `hour`/`minute`/`weekday` 结构化入参替代手搓 cron 表达式。
