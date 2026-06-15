## Context

`schedule` 是 agent 运行时的内置工具，经 `cron_scheduler` + `schedule_store`（agent 侧 `agent_state.db`）管理定时任务，与 platform 无耦合。现场反复出现：用户用自然语言（"北京时间 18:00"）建任务，模型把触发时间设错 8 小时、`task_type` 选错。

端到端排查确认根因在**工具契约的交付**，而非调度内核：

- `tool_schema_builder.build_schema()` 以 `__doc__.splitlines()[0]` 作工具描述——`schedule` 24 行 docstring 只有首行到达模型，其余 23 行（`task_type` 判据、`schedule_kind` 警告等）被丢弃。
- 参数描述的唯一通道是 `Annotated[T, "..."]`；`schedule` 的 15 个参数全是裸类型，模型收到的每个参数都是无描述、无枚举的 `{"type": "string"}`。
- `timezone` 参数默认硬编码 `"UTC"`，使 `cron_scheduler._register` 第 485 行 `tz = task.get("timezone") or self._settings.default_timezone` 的部署默认回退永不触发（成为死代码）。
- 时区数据全程字面透传，`_parse_cron` 仅 `split()`，APScheduler 按 `timezone` 字段解释 cron 字段；模型自行预转 UTC 又标本地时区，双重转换差 8 小时。

约束：纯 agent 侧改动；不碰 platform；无 DB schema 迁移；遵循既有工具声明约定与 TDD/分层测试规范。

## Goals / Non-Goals

**Goals:**
- 把 `schedule` 的使用契约（参数枚举 + 描述 + 时区语义）真正交付给模型，消除"盲填"。
- 时区解析改为优先级链（显式 > 部署默认 > UTC），去掉工具硬编码 `"UTC"`，复活既有部署默认回退。
- 让模型对时区零算术：只填用户说的本地钟面时间 + （可选）时区名。
- 创建即反馈下次触发时间（任务时区 + UTC），让转错当场可见。

**Non-Goals:**
- 不修 `schema_builder` 的首行截断本身（18/23 工具受影响，风险面大，另案）。
- 不做 per-user 时区映射（per-task 指定即可）。
- 不引入结构化时间入参（hour/minute/weekday）替代 cron。
- 不动调度内核、store schema、delivery 语义。

## Decisions

**D1：用既有 `Annotated`/`Literal` 通道交付契约，而非修 schema_builder。**
`schema_builder` 已支持 `Annotated[Literal[...], "desc"]` → enum + description（`builtin-web-tools`/`builtin-file-tools`/`builtin-shell-tool` 已这么用，且已实测验证）。把 `schedule` 改用同一约定即可让契约到达模型。
- 备选：让 schema_builder 发送完整 docstring。否决——影响全部 18 个被截断工具，回归风险大，超出本 change。

**D2：存"本地 cron + 时区"，不在创建时归一化为 UTC。**
周期任务若在创建时转成固定 UTC 偏移，会在跨 DST 地区漂移（如纽约 9am 在夏令时切换后变 10am）。存本地钟面 + IANA 时区，由 APScheduler 每次触发按时区解释，自动跟随夏令时，且**无需任何转换代码**。
- 备选：创建时转 UTC 存储。否决——对周期任务 DST 不正确，且更复杂。

**D3：模型零时区算术。**
失败的本质是 LLM 做时区减法。契约（D1）明确要求模型只照抄钟面时间到 cron 字段、写时区名，转换交给系统。这与 D2 互为表里。

**D4：去硬编码 `"UTC"` → 复活既有回退。**
工具 `timezone` 默认改 `""`；`create` 把空值下传为 `None`，让 `_register` 既有的 `or default_timezone` 真正生效。优先级：显式 per-task > `agent.scheduling.default_timezone` > UTC。
- 备选：新增独立的时区解析函数。否决——`_register` 已有正确回退，只是被短路，不重复造。

**D5：下次触发回执取自 APScheduler job 的 `next_run_time`。**
注册后读 job 的 `next_run_time`（注册后的权威计算值，能反映任何 cron×时区错配），按任务时区与 UTC 双格式化回执，并经既有 `schedule_store.update_run_state(next_run_at=...)` 回填——复用既有列，无 schema 变更。
- 备选：工具自行独立计算下次触发。否决——可能与实际注册的 job 不一致，失去"暴露真实触发时刻"的意义。

**D6：`schedule_kind` 设为 `Literal`，模型无法再emit `run_at`。**
既有"`run_at` → `once`"的宽容归一化保留在 facade `create_task`（服务非模型调用方），但模型层从枚举上就排除了非法值，从源头杜绝早期出现过的 `schedule_kind=run_at` 脏数据。

## Risks / Trade-offs

- **[`Literal` 化 `schedule_kind` 是否破坏既有 run_at 别名场景]** → 该场景（`cron-scheduled-tasks` 既有 "run_at is aliased to once"）针对的是 facade 归一化，不是工具 schema；facade 归一化保留，模型只是不再emit run_at。实施时跑既有 schedule 相关测试确认无回归。
- **[`next_run_time` 可能为 None]**（无运行中调度器、once 已完成、paused） → 仅在拿到 job/`next_run_time` 时回执触发时间；无调度器时退回既有"服务运行后生效"的诚实文案。
- **[无效 IANA 时区字符串]** → APScheduler 注册时会抛错；boot 路径既有 bulkhead 会禁用坏任务，工具 create 路径应捕获并返回干净错误（沿用 create 的 `ValueError → "error: ..."` 模式）。
- **[Annotated 描述增加每次 schedule 调用的 token]** → 增量很小，正确性收益压倒成本。
- **[默认时区从 UTC 变为部署默认]** → 非破坏：`default_timezone` 本身默认 UTC，未配置的部署行为不变；既有显式带 `timezone` 的任务不受影响。

## Migration Plan

- 无 DB 迁移、无新依赖。
- 部署：重装 agent 包 + 重启进程后生效（运行态读 site-packages，不读仓库源码）。on-prem 部署在 `agent.yaml` 配 `scheduling.default_timezone`（如 `Asia/Shanghai`）一次设定本地默认。
- 回滚：还原 `schedule` 签名与 create 分支即可，无状态需回滚。

## Open Questions

无（方案已在 brainstorm 锁定）。`list`/`run_now` 是否也回显下次触发时间留作后续增强，不在本 change。
