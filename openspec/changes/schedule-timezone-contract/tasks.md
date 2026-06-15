## 1. 工具契约可见性 — 枚举（Literal）

- [x] 1.1 写失败测试（unit, `tests/unit/test_builtin_tools_schedule_schema.py`）：从 `get_schemas()` 取 `schedule` schema，断言 `task_type` 暴露 enum `["notify","generate","action"]`、`schedule_kind` 暴露 enum `["cron","once","interval"]`、`action` 与 `notify_target_type` 暴露各自枚举。运行最窄命令见红。
- [x] 1.2 实现：把 `schedule` 签名的 `action`/`schedule_kind`/`task_type`/`notify_target_type` 改为 `Annotated[Literal[...], "desc"]`。运行同一命令见绿。

## 2. 工具契约可见性 — 参数描述（Annotated）

- [x] 2.1 写失败测试（unit, 同上文件）：断言 `timezone` 与 `cron_expr` 参数的 `description` 含"按时区本地钟面时间填、勿预转 UTC"语义，且 `timezone` 描述含"留空用部署默认"；`task_type` 描述含 notify/generate/action 选择判据。见红。
- [x] 2.2 实现：给 `timezone`/`cron_expr`/`run_at`/`interval_seconds`/`message`/`notify_text`/`notify_platform`/`notify_target`/`name`/`task_id` 补 `Annotated` 中文描述（`timezone` 写明 no-pre-convert + 留空用部署默认；`cron_expr` 给"每天本地 20:34 → '34 20 * * *'"范例；`task_type` 写明三类判据与默认 generate）。见绿。

## 3. 时区解析链 — 去硬编码 UTC

- [ ] 3.1 写失败测试（integration, `tests/integration/test_cron_timezone_resolution.py`）：(a) `create` 不带 `timezone` 且 `scheduling.default_timezone="Asia/Shanghai"` → 注册的 APScheduler job 在 `Asia/Shanghai` 时区、`next_run_time` 落当地；(b) `cron_expr="0 18 * * *"` + `timezone="Asia/Shanghai"` → 触发时刻为当地 18:00（非 18:00 UTC、非 10:00 当地）；(c) 显式 `timezone="America/New_York"` 覆盖部署默认。当前因工具硬编码 `"UTC"`，(a) 见红。
- [ ] 3.2 实现：工具 `timezone` 默认 `"UTC"` → `""`；`create` 分支以 `timezone=timezone or None` 下传，使 `cron_scheduler._register` 既有 `task.get("timezone") or self._settings.default_timezone` 回退生效（优先级：显式 > 部署默认 > UTC）。见绿。

## 4. 创建回执 — 下次触发时间 + next_run_at 回填

- [ ] 4.1 写失败测试（integration, `tests/integration/test_schedule_tool_next_fire_echo.py`）：运行中调度器下 `schedule(action="create", ...)` 一个 cron 任务 → 工具返回串包含下次触发时间（任务时区 + UTC 双显）；该任务 `next_run_at` 被回填为非空。见红。
- [ ] 4.2 实现：`create` 分支在注册成功后读 APScheduler job 的 `next_run_time`，按任务时区与 UTC 双格式化并加入回执串；经既有 `schedule_store.update_run_state(next_run_at=...)` 回填。见绿。
- [ ] 4.3 写失败测试（integration, 同上文件）：`cron_scheduler.current() is None`（无运行中调度器）时 `create` 退回既有"服务运行后生效"文案，不计算 `next_run_time`、不报错、不谎报触发时间。见红/见绿（回归保护）。
- [ ] 4.4 实现：确保无调度器分支不触碰 `next_run_time`，文案与既有行为一致。见绿。

## 5. 部署配置文档

- [ ] 5.1 在 `agents/default/agent.yaml.example` 的 `scheduling` 段补注 `default_timezone`（示例与注释：留空时任务用此时区，如 `Asia/Shanghai`）。

## 6. 收尾验证

- [ ] 6.1 跑受影响层：`uv run pytest tests/unit/test_builtin_tools_schedule_schema.py -q` 与 `uv run pytest tests/integration/test_cron_timezone_resolution.py tests/integration/test_schedule_tool_next_fire_echo.py -q`，并跑既有 schedule/cron 相关测试确认无回归。
- [ ] 6.2 `uv run python scripts/check_test_layers.py` 确认新增 unit/integration 测试归位正确。
- [ ] 6.3 改动文件 `uv run ruff format` + `uv run ruff check` + `uv run mypy src`（改动范围）通过。
- [ ] 6.4 `make test-pr` 全绿；`uv run pytest tests/integration -q` 对照 main 基线确认无新增失败。
