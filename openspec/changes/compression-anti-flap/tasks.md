## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 AR12 入口：`context_mgr.maybe_compress(messages, config, *, force)` 自动路径在 `estimate_tokens > max_tokens * Tmax` 时调 `_compress`，`force=True` 无条件压缩；`compress_for_context_overflow` 无条件压缩。确认反抖动门控只加在自动路径、不改 `_compress` 分层逻辑
- [ ] 1.2 核实配置惯例：`Settings` 的 `context_tmax_ratio`/`context_tretained_ratio`/`context_keep_recent` env 字段与 `context_mgr._default_config()` 注入键；本能力向其追加 `context_flap_window`/`context_min_savings_ratio`/`context_min_interval_turns`，缺省回退默认，不破坏既有 `test_context_mgr.py`
- [ ] 1.3 核实「无全局可变状态」与测试隔离惯例：反抖动状态须按次传入、不落模块级可变全局；LLM 摘要调用经 `patch("fleetent.context_mgr.get_client_and_config")` mock，状态由测试直接构造注入
- [ ] 1.4 核实 `session-metadata-index` 在 `users.db` 的 per-session sqlite 家：`sessions` 表结构、`_conn()` 连接惯例、`DB_PATH` 从 `user_store` re-export 可 monkeypatch；确认本 change 仅加列或建以 `session_id` 为键的姊妹表，不新建 db 文件、不改其既有元数据语义
- [ ] 1.5 核实 `agent_loop.run()` / `run_stream()` 主循环每 turn 调一次 `maybe_compress` 的位置与 `session_id` 可得性；确认可在 run 边界按 `session_id` load/save `AntiFlapState`，不破坏 `session_mgr` 裸消息数组契约

## 2. 反抖动状态数据结构与默认配置（context_mgr.py / config.py）

- [ ] 2.1 Write failing tests：`AntiFlapState` 默认字段为空滑窗、`turns_since_last_compress=0`、`auto_disabled=False`；`Settings` 含 `context_flap_window=3`/`context_min_savings_ratio=0.10`/`context_min_interval_turns=1`，且 `_default_config()` 注入这三键。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `AntiFlapState`（dataclass）与三个 `Settings` env 字段 + `_default_config()` 注入键，看到绿

## 3. 节省率统计与连续低节省熔断（context_mgr.py）

- [ ] 3.1 Write failing tests：节省率 `(before-after)/before`（`before<=0` 记 0）正确写入滑窗；滑窗仅保留最近 `flap_window` 次。看到红
- [ ] 3.2 Implement 节省率计算与定长滑窗追加（纯函数式更新，不改传入对象），看到绿
- [ ] 3.3 Write failing tests：连续 3 次节省率 < 0.10 → `auto_disabled=True` 且记录 `compression_auto_flap_disabled` 告警（用 capsys / 捕获 structlog）；中途一次达标则不熔断。看到红
- [ ] 3.4 Implement 熔断判定（滑窗满且 `all(< min_savings_ratio)`）+ 结构化告警（log 不抛异常、不静默），看到绿
- [ ] 3.5 Write failing test：`auto_disabled=True` 后自动路径越过 `Tmax` 仍原样返回、不调用 LLM（断言 `get_client_and_config` 未被调）。看到红
- [ ] 3.6 Implement 熔断后自动路径短路返回，看到绿

## 4. 最小间隔滞后窗口（context_mgr.py）

- [ ] 4.1 Write failing tests：`turns_since_last_compress < min_interval_turns` 且越过 `Tmax` 时跳过自动压缩、原样返回、不调用 LLM；窗口满足后正常压缩并将计数归零。看到红
- [ ] 4.2 Implement 最小间隔窗口判定（窗口未满短路返回；执行压缩后计数归零），看到绿

## 5. 入口豁免与状态返回（context_mgr.py）

- [ ] 5.1 Write failing tests：`maybe_compress(force=True)` 不受熔断与窗口约束、无条件压缩，且本次节省率不计入滑窗；`compress_for_context_overflow` 同样不受熔断与窗口约束。看到红
- [ ] 5.2 Implement 手动与 overflow 入口豁免门控、不计入统计，看到绿
- [ ] 5.3 Write failing tests：传入 `state` 时 `maybe_compress` 返回更新后的状态（不就地改写传入对象）；`state=None` 时行为与 AR12 现状完全一致（既有用例不回归）。看到红/绿确认兼容

## 6. 阈值注入（context_mgr.py）

- [ ] 6.1 Write failing tests：经 `ContextConfig` 注入自定义 `flap_window`/`min_savings_ratio`/`min_interval_turns` 时，熔断与间隔判定按注入值生效，而非默认值。看到红
- [ ] 6.2 Implement 阈值从注入 config 读取（缺省回退默认），看到绿

## 7. AntiFlapState 在 users.db 的 session 级持久化（context_mgr.py / users.db）

- [ ] 7.1 Write failing tests：建列或建以 `session_id` 为键的姊妹表幂等（`CREATE TABLE/INDEX IF NOT EXISTS`，重复建不报错、不丢数据）；按 `session_id` 写入 `AntiFlapState`（节省率滑窗、`turns_since_last_compress`、`auto_disabled`）后重开连接原样读回；不存在的 `session_id` 读取返回默认空状态；`monkeypatch DB_PATH` 到 tmp_path。看到红
- [ ] 7.2 Implement 在 `users.db` 加列或建姊妹表 + 按 `session_id` load/save `AntiFlapState` 的函数（标准库 `sqlite3`，复用 `_conn`，`DB_PATH` 可 monkeypatch，不新建 db 文件、不落 `session_mgr` 裸消息数组），看到绿
- [ ] 7.3 Write failing test：写回再读回的 `AntiFlapState` 与写入时逐字段一致，且对应 session 的裸消息数组文件不因持久化承载任何附加状态（断言 session JSON 不含反抖动字段）。看到红/绿

## 8. agent_loop 在 run 边界 load/save 与跨 run 累计（agent_loop.py）

- [ ] 8.1 Write failing tests：`run()` / `run_stream()` 开 run 时按 `session_id` 从 `users.db` load `AntiFlapState`、逐 turn 传入 `maybe_compress` 并接住返回值、run 结束/压缩后 save 回 `users.db`（mock `maybe_compress` 或 LLM、`DB_PATH` 隔离 tmp_path）。看到红
- [ ] 8.2 Implement agent_loop run 边界 load/save `AntiFlapState`、逐 turn 透传与回收，看到绿
- [ ] 8.3 Write failing test：**跨多次 run（多条用户消息）累计连续低节省触发熔断**——同一 `session_id` 跨多次 `run()` 各发生一次低节省自动压缩、状态经 `users.db` 持久化还原，累计满 `flap_window` 次 `< min_savings_ratio` 后 `auto_disabled=True` 并告警；证明计数不因单次 run 结束而重置。看到红
- [ ] 8.4 Implement 确保 turns 计数与节省率滑窗跨 run 累计（仅真正压缩时归零 turns），看到绿

## 9. 收尾

- [ ] 9.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 9.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 9.3 `uv run mypy src` 无新增错误
