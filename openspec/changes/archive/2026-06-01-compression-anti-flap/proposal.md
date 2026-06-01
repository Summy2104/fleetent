## Why

AR12（context-compression-threshold，已实现于 `context_mgr.py`）通过双阈值 `Tmax`/`Tretained` 让一次压缩把 token 从触发线 `max_tokens * Tmax` 回落到目标线 `max_tokens * Tretained`，两阈值间距已能抑制「压缩后少量新增消息立即再触发」的即时抖动。但 AR12 只保证「触发时机」与「目标线」，无法应对**压缩本身无效**导致的抖动：

- **低节省抖动**：当中段可压缩内容很少（头/尾本身就接近 `Tmax`，或尾部 `keep_recent` 撑满），一次压缩只省下极少 token，压缩后估算仍贴近 `Tmax`。下一轮少量新增即再次越线，于是「压缩 → 几乎没省 → 立即再压缩」反复发生：既烧 LLM 摘要调用成本，又反复让 prompt 缓存前缀失效（CLAUDE.md prompt-cache-optimization），却始终救不回上下文。AR12 的「目标线让位于工具对完整性」relaxation 会进一步放大此场景——实际值可合法地略高于 `Tretained`，恰好留在 `Tmax` 附近。
- **目标线擦边抖动**：即使节省达标，若实际回落值反复贴着 `Tmax` 之下一点点，仍可能被新增消息快速顶回触发线，形成高频压缩。

`docs/capabilities/agent-runtime.md`「压缩反抖动」明确要求：**连续 3 次压缩节省率均低于 10% → 关闭自动压缩并告警**（提示扩大 context 上限或拆分任务）。本能力把这条治理规则与一道**滞后/最小间隔窗口**落到 `context_mgr` 的自动压缩入口 `maybe_compress` 上，作为 AR12 双阈值之上的反抖动层。

## What Changes

- 在 `maybe_compress` 自动路径上引入**反抖动状态** `AntiFlapState`：记录最近若干次自动压缩的**节省率**（`(before - after) / before`）与触发计数。该状态作用域为 **session 生命周期级**，**按 session_id 持久化于 `users.db`**（复用 `session-metadata-index` 已有的 per-session sqlite 家，不落 `session_mgr` 的裸消息数组），由 **`agent_loop` 在 run 边界 load/save**、逐 turn 按次传入 `maybe_compress`（纯函数式收发）；turns 计数与节省率滑窗随对话**跨 run（跨多条用户消息）累计**，无全局可变状态。手动 `/compact`（`force=True`）与 `compress_for_context_overflow` 不受反抖动门控约束（见 design D4）。
- **低节省熔断**：连续 `flap_window` 次（默认 3）自动压缩的节省率均低于 `min_savings_ratio`（默认 0.10）时，**关闭该会话的自动压缩**并发一次告警（结构化日志 + 可供上层消费的状态），提示「扩大 context 上限或拆分任务」。熔断后 `maybe_compress` 在自动路径直接原样返回，不再调用 LLM 摘要；手动与 overflow 入口仍可压缩。
- **最小压缩间隔 / 滞后窗口**：两次自动压缩之间须间隔至少 `min_interval_turns`（默认 1）个新增 turn 的「滞后窗口」，避免在 `Tmax` 擦边时同一批消息上连发压缩；窗口内即使越线也跳过自动压缩（overflow 入口不受此限，保证正确性兜底）。
- **回落余量校验**：明确 AR12 的 `Tretained` 作为「低水位线」语义——压缩后估算应回落到目标线附近以留出余量；当回落后仍贴近 `Tmax`（余量低于 `min_savings_ratio` 对应的可压缩空间）时计为一次「低节省」，纳入熔断窗口统计。
- 所有阈值/窗口为**可注入常量/配置**（沿用 AR12 的 `ContextConfig` dict 注入与 `Settings` env 字段惯例），无全局可变状态。

## Capabilities

### New Capabilities
- `compression-anti-flap`: 在 AR12 双阈值之上对自动压缩做反抖动治理——以节省率统计、连续低节省熔断（默认连续 3 次 < 10% 即关闭自动压缩并告警）与最小压缩间隔/滞后窗口，避免上下文在 `Tmax` 附近反复触发压缩。

### Modified Capabilities
<!-- 不以 MODIFIED 表达 AR12（context-compression-threshold）。AR12 既有需求（双阈值、回落目标线、间距不变式、手动/overflow 入口、可注入）保持原样不改；本能力以 build-on 方式在自动压缩入口外加反抖动层，全部为 ADDED，落在新 capability compression-anti-flap 下，避免 archive sync 找不到同名既有需求。 -->

### 共享资源引用
- **`context_mgr.maybe_compress` 自动压缩入口 owner = AR12**：本能力仅在其自动路径前后**追加**反抖动门控与统计，不改 AR12 的 `Tmax`/`Tretained` 判定与 `_compress` 分层逻辑。
- **`Settings` 的 `context_*` 配置族 owner = AR12**：本能力向其**追加** `context_flap_*` 字段（窗口、最小节省率、最小间隔），与既有 `context_tmax_ratio`/`context_tretained_ratio` 共处同族。

## Impact

- **代码**：
  - 修改 `src/fleetent/context_mgr.py`：在 `maybe_compress` 自动路径外加反抖动门控（统计节省率、熔断判定、间隔窗口判定）；新增反抖动状态数据类 `AntiFlapState` 与纯函数判定逻辑（无全局可变状态，状态按次传入、返回更新后状态）。
  - `AntiFlapState` 持久化：复用 `session-metadata-index` 在 `users.db` 维护的 per-session sqlite 家（`sessions` 表加列或建以 `session_id` 为键的姊妹表），标准库 `sqlite3` 直写 SQL、复用 `_conn()`、`DB_PATH` 可 monkeypatch，不新建 db 文件、不落 `session_mgr` 裸消息数组。
  - 修改 `src/fleetent/agent_loop.py`：在 `run()` / `run_stream()` 的 run 边界按 `session_id` 从 `users.db` load `AntiFlapState`、逐 turn 传入 `maybe_compress` 并接住返回值、run 结束/压缩后 save 回 `users.db`，使 turns 计数与节省率滑窗跨 run 累计。
  - 扩展配置：`Settings` 追加 `context_flap_window`（默认 3）、`context_min_savings_ratio`（默认 0.10）、`context_min_interval_turns`（默认 1）；`_default_config()` 注入对应键。
- **配置**：新增 `context_flap_window` / `context_min_savings_ratio` / `context_min_interval_turns` env 字段，全部可选，缺省用安全默认。
- **测试**：扩充 `tests/test_context_mgr.py`：连续低节省触发熔断并告警、熔断后自动路径原样返回、手动/overflow 入口不受熔断与间隔门控、最小间隔窗口内跳过、节省率统计正确、阈值可注入、`AntiFlapState` 按 session_id 在 `users.db` 读写往返（`DB_PATH` 隔离 tmp_path）、**跨多次 run（多条用户消息）累计连续低节省触发熔断**。LLM 摘要调用全部 mock，路径与状态隔离到 tmp_path / 注入对象。
- **不影响**：AR12 双阈值判定与 `_compress` 分层、`session_mgr` 裸消息数组契约、`session-metadata-index` / `session-ttl-cleanup` / `session-disk-management` 既有行为、memory_layer、knowledge_base、permission_gate；不引入新依赖（仅 `structlog`、标准库 `sqlite3`）。

## Dependencies

- **`session-metadata-index`（已实现）**：复用其在 `users.db` 维护的 per-session sqlite 持久化家（`sessions` 表 + 标准库 `sqlite3` 连接惯例）承载 `AntiFlapState`——加列或建以 `session_id` 为键的姊妹表，不新建 db 文件、不破坏其既有元数据语义。
- **`agent_loop`（`src/fleetent/agent_loop.py`）**：在 `run()` / `run_stream()` 的 run 边界 load/save `AntiFlapState`、逐 turn 把状态传入 `maybe_compress` 并接住返回值，使 turns 计数与节省率滑窗跨 run 累计。
- **AR12（`context-compression-threshold`，已实现于 `context_mgr.py`）**：本能力在其自动压缩入口 `maybe_compress` 外加反抖动门控，复用其 `Tmax`/`Tretained` 判定、`_compress` 分层、`ContextConfig` 注入与 `Settings` 配置族，不改其既有逻辑。
