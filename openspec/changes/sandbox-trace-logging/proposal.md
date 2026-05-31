## Why

`run_code`（`tools.py` 行 49-69）在沙箱执行代码后，只把 stdout/stderr/exit_code 拼成文本返回给 AI，**不写任何运行日志**。`docs/capabilities/sandbox.md` 现状条目明确：「执行过程可观测：返回 stdout / stderr / exit_code，但未写入运行日志（trace）」，且规划项要求「执行结果写入 trace：记录执行时长、退出码、输出大小、使用的沙箱类型」。

没有 trace 就无法回答运营问题：哪些 agent 在跑代码、跑了多久、失败率多少、输出多大。`eval_logger.py` 是项目唯一的 append-only JSONL trace 出口（`log_run` 记 agent 整轮、`log` 记 IM 消息），但都不适合记录「一次 `run_code` 工具调用内的沙箱执行」这一更细粒度事件。本 change 在 `eval_logger` 增加一个沙箱执行专用的 trace 出口，让 `run_code` 把执行结果落盘。沙箱后端保留 Docker，trace 字段（执行时长/退出码/输出大小/沙箱 scope 类型）均来自既有执行路径已有的信息。

## What Changes

- 在 `eval_logger.py` 新增**沙箱执行 trace 出口** `log_sandbox_exec(...)`：append 一条 JSONL 记录，字段含执行时长（秒）、退出码、stdout/stderr 字节大小、使用的沙箱 scope 类型（`session`/`agent`，由 SB2 提供；SB2 未落地前可记 `None`/默认）、可选 agent / user 标识。
- 改造 `run_code` 工具：执行前后测量耗时，执行后调用 `log_sandbox_exec` 写入 trace；trace 写入失败 MUST NOT 影响代码执行结果返回（trace 是旁路观测，不阻断主流程）。
- trace **不记录代码原文与完整输出内容**（避免日志膨胀与敏感信息落盘），只记录大小与元数据；与 `eval_logger` 既有「不写 base64 图片原文」的克制原则一致。

## Capabilities

### New Capabilities
- `sandbox-trace-logging`: 沙箱代码执行结果写入 trace——每次 `run_code` 执行后向运行日志 append 一条记录，含执行时长、退出码、stdout/stderr 字节大小、沙箱 scope 类型与可选 agent/user 标识；只记元数据不记代码原文与完整输出；trace 写入失败不阻断执行结果返回。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。run_code 的返回内容与执行语义不变，仅旁路新增 trace 写入。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/eval_logger.py`：新增 `log_sandbox_exec(elapsed_s, exit_code, stdout_bytes, stderr_bytes, sandbox_scope=None, agent_name=None, user_id=None)`，append 到既有 `_LOG_PATH` JSONL（复用 `_LOG_PATH.parent.mkdir` + append 写法），记录类型标记（如 `kind: "sandbox_exec"`）便于区分。
  - 修改 `src/fleetent/tools.py`：`run_code` 用 `time.monotonic()` 测耗时，执行后计算输出字节大小并调用 `log_sandbox_exec`；写入包在 try/except，失败 log 警告不影响返回。
- **配置**：无新增配置。
- **测试**：扩充 `tests/test_eval_logger.py` 覆盖 `log_sandbox_exec` 写入字段与类型标记、可选字段省略；扩充 `tests/test_tools.py`（或对应 run_code 测试）断言执行后写入 trace、trace 失败不影响返回。`_LOG_PATH` `monkeypatch` 到 tmp_path 隔离，Docker/SandboxClient mock。
- **不影响**：`log_run` / `log` 既有 trace 行为与字段；SB2 scope、SB3 mode、SB4 资源、SB5 密钥、SB8 清理；不引入新依赖。SB2 未落地时 `sandbox_scope` 记 `None`，落地后由 SB2 提供真实 scope。
