## Context

`cron_scheduler.start()`（agent boot 调用）从 store 载入 `enabled=1` 任务并逐条 `_register`；`once` 任务经 `_parse_run_at(task["run_at"])` → `datetime.fromisoformat`。`schedule` 工具创建任务时把模型给的 `run_at` 字符串原样存库（`builtin_tools.schedule` → `schedule_store.create(run_at=run_at or None)`）。模型曾给出 `'2026-06-14 08:07:19 UTC'`，`fromisoformat` 不认 ` UTC` 后缀 → `ValueError` → 整个 `start()` 抛出 → boot 崩溃。约束：异步资源生命周期与舱壁化原则（AGENTS.md）——关停/启动链每一步独立隔离，单组件失败只记日志不波及全局。

## Goals / Non-Goals

**Goals:**
- 单条坏任务**永远不能**让 agent 启动崩溃（启动韧性，核心）。
- `_parse_run_at` 容忍常见非严格 ISO（` UTC`/`Z`/tz-name 后缀、空格分隔），归一化后解析。
- 写入端规范化，使新建 `once` 任务永远落库为 canonical ISO，杜绝复发。

**Non-Goals:**
- 不改 `scheduled_tasks` schema、不做数据迁移（存量坏行靠启动韧性自动 disable）。
- 不改 misfire/coalesce 等既有重启行为。
- 不写一次性批量修复脚本（YAGNI；韧性已兜底）。

## Decisions

### D1：启动韧性 = 每任务舱壁化 + 自动 disable
`start()` 的 `for task in db_jobs: self._register(task)` 改为每条独立 try/except：捕获注册异常 → `logger.warning("cron_register_failed task=… error=…")` + `_store.set_enabled(task_id, False)`（坏任务下次不再加载）+ 跳过，继续注册其余。`scheduler.start()` 照常。
- **为何**：符合舱壁化原则；一条坏数据是数据问题，不该是可用性问题。自动 disable 让坏行不再每次重启重复 warn，并把它从活跃集移除（保留行供排查，不删）。
- **备选**：仅 try/except 跳过不 disable（每次重启都重试坏行、重复告警）——劣，故加 disable。删除坏行——丢数据，劣。

### D2：`_parse_run_at` 归一化后解析
解析顺序不变（相对时长优先），`fromisoformat` 前对 spec 归一化：
- 去尾部时区名：`re.sub(r"\s+(UTC|GMT)$", "+00:00", spec)`（` UTC`/` GMT` → `+00:00`）；保留已有 `Z` 由 fromisoformat（3.11+ 支持 `Z`）或显式替换 `Z`→`+00:00`。
- 其余交给 `fromisoformat`（其已支持空格分隔的 `YYYY-MM-DD HH:MM:SS`）。
- 仍无法解析 → 抛 `ValueError`（由 D1 兜底，不再崩 boot）。
- **为何**：最小、可预测；只针对实际出现的模型输出形态做白名单归一化，不引入宽松 dateutil 依赖（避免误解析）。

### D3：写入端复用同一解析器规范化
`schedule` 工具创建 `once` 时：`parsed = _parse_run_at(run_at)`（失败 → 返回明确错误文本，不落库）；落库存 `parsed.isoformat()`（canonical，带 `+00:00`）。
- **为何**：单一可信解析器，写读一致；新任务永远干净，存量靠 D1+D2 兜底。
- 仅规范化 `once`（cron/interval 不用 run_at）。

## Risks / Trade-offs

- [自动 disable 坏任务可能让用户以为"任务消失了"] → warning 日志显式记录 task id + 原因；行保留（enabled=0）可查；属合理降级（坏任务本就无法运行）。
- [归一化白名单不全，仍有模型造出的怪异格式] → D1 韧性兜底：无论 D2 是否覆盖，boot 不崩；最坏是该任务被 disable + 记日志。
- [写入端规范化改变落库值格式] → 仅 `once`、仅 canonical ISO，语义等价；读路径 D2 兼容新旧。
