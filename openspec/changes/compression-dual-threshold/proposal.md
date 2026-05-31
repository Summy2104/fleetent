## Why

`context_mgr.maybe_compress` 当前只有单一阈值 `compress_threshold`（默认 0.8）：当估算 token 超过 `max_tokens * 0.8` 即触发压缩，但压缩目标没有独立约束——压缩后只保留 `keep_recent` 条尾部消息，token 占用是「保留了多少」决定的，而非「压到了哪个目标线」。这带来两个问题：

- **缺乏目标线**：压缩后的体量不可控，可能压得过狠（丢失过多上下文），也可能压得过浅，刚好停在触发线附近。
- **频繁压缩 / 缓存失效**：若压缩后仍接近触发阈值，下一轮新增几条消息就会再次越线，导致反复压缩；每次压缩都改写历史前缀，使 LLM 的 prompt 缓存命中失效，成本与延迟上升。

此外，现状只能在「新一轮 LLM 调用前自动检查」时触发压缩，缺少两个明确的触发入口：用户主动压缩（`/compact` 命令语义）、以及 LLM 报「上下文过长」错误时的自动补救。

## What Changes

- 引入**双阈值压缩**：用 `Tmax`（触发压缩的上限比例）与 `Tretained`（压缩目标比例）两个阈值替代单一 `compress_threshold`。
  - `Tmax`：估算 token 超过 `max_tokens * Tmax` 时触发压缩（替代现状 `compress_threshold` 的触发语义）。
  - `Tretained`：压缩的目标线——压缩后估算 token 应回落到 `max_tokens * Tretained` 附近或以下。
  - 两阈值之间 MUST 保持足够间距（`Tretained < Tmax`），避免压缩后立即再次越过 `Tmax`（频繁压缩、缓存失效）。
- 支持**显式触发**压缩，不依赖是否越过 `Tmax`：
  - **手动触发**（`/compact` 命令语义）：调用方请求时无条件压缩到 `Tretained`。
  - **LLM 上下文过长错误触发**：当 LLM 返回「上下文过长」类错误时，调用方可请求一次压缩后重试。
- 新增两个部署级配置字段：`config.py` 的 `Settings` 增加 `context_tmax_ratio`、`context_tretained_ratio`（env 可配，沿用既有 `context_*` 模式）。
- `maybe_compress` 的 `config` 注入契约保持兼容：测试仍通过传 config dict 注入，不实例化真 `Settings`。

## Capabilities

### New Capabilities
- `context-compression-threshold`: 上下文压缩的双阈值触发策略（AR12）——以 `Tmax` 触发、压缩到 `Tretained` 目标线，两阈值保持间距以抑制频繁压缩；并提供手动触发与「上下文过长」错误触发两个显式入口。

### Modified Capabilities
<!-- 本次为新增 capability；不修改既有 spec 的需求级行为。context_mgr 的尾部保留 / tool-pair 完整性等既有行为不变。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/context_mgr.py`：`_default_config()` 读取新的 `tmax_ratio` / `tretained_ratio`；`maybe_compress` 以 `Tmax` 判触发、以 `Tretained` 为压缩目标；新增显式触发入口（手动 / 错误触发）。
- **配置**：`config.py` 的 `Settings` 增加 `context_tmax_ratio: float = 0.8`、`context_tretained_ratio: float = 0.6`（env 可配，与 `context_max_tokens` / `context_keep_recent` 同类），并**移除** `context_compress_threshold`（触发角色由 `context_tmax_ratio` 取代，迁移见 design D5）。
- **测试**：新增/扩展 `tests/test_context_mgr.py`：双阈值触发、压缩目标线、两阈值间距、手动触发、错误触发；LLM 摘要调用按规范 mock（`patch get_client_and_config`）。
- **不影响**：agent_loop 主循环结构、model fallback、工具 dispatch、终止框架；不引入新依赖（无 AI 框架、无 ORM、无云服务）。
