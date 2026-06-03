## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `maybe_compress` 现状触发边界（`estimate_tokens(messages) <= threshold` 直接返回）与 `_keep_tail` 的 tool-pair 完整性 identity check，确认压缩回落策略不破坏既有行为
- [x] 1.2 确认 `_default_config()` 当前返回键（`max_tokens` / `compress_threshold` / `keep_recent`）与 `Settings.context_compress_threshold` 的耦合点
- [x] 1.3 按 D5 移除 `context_compress_threshold`：核查代码内所有引用点（config.py、context_mgr._default_config、相关测试），规划全部改为 `context_tmax_ratio`。引用点：config.py:17、context_mgr.py:21/55、.env.example:16、tests/test_context_mgr.py:43（config key `compress_threshold`）

## 2. 配置接入（Settings + _default_config）

- [x] 2.1 Write failing tests：`Settings` 含 `context_tmax_ratio`（默认 0.8）、`context_tretained_ratio`（默认 0.6）；`context_mgr._default_config()` 返回 `tmax_ratio` / `tretained_ratio` 两键。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement：`config.py` 的 `Settings` 增加两个字段并**移除** `context_compress_threshold`；`_default_config()` 返回 `tmax_ratio` / `tretained_ratio`（不再返回 `compress_threshold`）。看到绿

## 3. 双阈值触发判定

- [x] 3.1 Write failing tests for `maybe_compress` 触发边界：估算 token 超过 `max_tokens * tmax_ratio` 触发压缩（返回被压缩序列）；未超过则原样返回。阈值经 config dict 注入。看到红
- [x] 3.2 Implement：`maybe_compress` 触发判定改用 `tmax_ratio`。看到绿

## 4. 压缩回落到 Tretained 目标线

- [x] 4.1 Write failing tests：因超过 `tmax_ratio` 触发压缩后，估算 token 回落到 `max_tokens * tretained_ratio` 附近或以下；LLM 摘要调用按规范 mock（`patch get_client_and_config`）。看到红
- [x] 4.2 Implement：压缩以 `tretained_ratio` 为目标线选择保留尾部规模。看到绿
- [x] 4.3 Write failing tests for 工具对完整性优先：当严格回落会切断 tool_call/tool_result 对时，保留完整对、允许略高于目标线、消息序列对 LLM 合法。看到红
- [x] 4.4 Implement：目标线让位于 `_keep_tail` 的 tool-pair 完整性。看到绿

## 5. 两阈值间距与配置校验

- [x] 5.1 Write failing tests：默认配置下压缩后估算 token 低于 `tmax_ratio` 触发线（间距有效，不会即时再触发）；注入 `tretained_ratio >= tmax_ratio` 的非法配置被报错或规整，不以非法形式生效。看到红
- [x] 5.2 Implement：间距保障 + `tretained_ratio < tmax_ratio` 校验。看到绿

## 6. 手动触发入口（/compact 语义）

- [x] 6.1 Write failing tests：未超过 `tmax_ratio` 时请求手动强制压缩，仍执行压缩并回落到 `tretained_ratio` 目标线。看到红
- [x] 6.2 Implement：手动强制压缩入口（force 参数或独立函数，按实现决策）。看到绿

## 7. 上下文过长错误触发入口

- [x] 7.1 Write failing tests：因 LLM 上下文过长错误请求压缩时，执行压缩并回落到 `tretained_ratio` 目标线，返回压缩后序列供重试。看到红
- [x] 7.2 Implement：错误触发压缩入口（context_mgr 侧 API；端到端编排属调用方，不在本次）。看到绿

## 8. 收尾

- [x] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求），确认无回归
- [x] 8.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 8.3 `uv run mypy src` 确认未新增 mypy 错误模式
