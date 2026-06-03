## Context

前五包已迁，张洋域只剩 runtime 13 模块平铺。调用边（已扫描）：
- `agent_loop` 被 import：`cron_scheduler`、`__main__`、`server`、`tui/dispatch`、`im_gateway/normalizer`（`run_stream`、`run_sync as run`）、`tools/builtin_tools`（届时路径）、`sub_agent`（包内化）
- `context_mgr` 仅被 `agent_loop` 引用；其余 11 个治理模块主要被 `agent_loop` 消费（budget/cancellation/termination/loop_detector/message_hygiene/error_classifier/tool_guardrails/layered_budget/sub_agent_lifecycle/agent_runtime.load_active）
- `cancellation.CancelToken` 是跨域类型（server/sub_agent/cron 等持有引用）
- 测试 patch 面：**39 处 patch/setattr 打在 `fleetent.agent_loop` 命名空间**（18 文件）；其余 12 模块零直接 patch（经 loop 命名空间间接 patch）

## Goals / Non-Goals

**Goals**：13 文件迁入 `runtime/`、三处去重命名、`__init__` 收口、调用方改新路径、13 shim、39 处 patch 随迁、全量绿、行为不变。
**Non-Goals**：不拆 `runtime/governance/` 子包（蓝图已决：先平铺）；不改 loop↔sub_agent lazy import 依赖方向；不改 run/run_stream 契约、压缩算法、预算/取消/终止语义；不在本 change 删 shim（统一收尾 change 做）。

## Decisions

### D1 — 文件映射
```
agent_loop.py            → runtime/loop.py
context_mgr.py           → runtime/context.py
agent_runtime.py         → runtime/snapshot.py
sub_agent.py             → runtime/sub_agent.py          # 以下 10 个仅移动
sub_agent_lifecycle.py   → runtime/sub_agent_lifecycle.py
termination.py           → runtime/termination.py
loop_detector.py         → runtime/loop_detector.py
budget.py                → runtime/budget.py
layered_budget.py        → runtime/layered_budget.py
cancellation.py          → runtime/cancellation.py
message_hygiene.py       → runtime/message_hygiene.py
error_classifier.py      → runtime/error_classifier.py
tool_guardrails.py       → runtime/tool_guardrails.py
```
`git mv` 保留历史。

### D2 — 公共 API 收口 `runtime/__init__.py`
对外真正消费的：`run, run_stream`（loop）、`CancelToken, CancellationChecker`（cancellation）、`load_active`（snapshot）、`SubAgentExecutor`（sub_agent）。治理模块符号（BudgetChecker、StopReason、classify 等）按 src+tests 实际外部使用决定是否包级导出，原则：**只导外部用的，包内消费不导**。`__all__` 显式。

### D3 — 包内 import 方式
loop 对 12 个兄弟模块的 import 改 `from fleetent.runtime.<mod> import ...`（子模块直引，不经包 `__init__`，避免环）；loop↔sub_agent 既有 lazy import 边界**原样保留**，仅改路径。

### D4 — 13 个旧路径 shim
全部留 shim（含 `agent_loop.py`→re-export from `runtime.loop`）。三处重命名的 shim 注释标注新名。`import fleetent.agent_loop` 仍可用且仍触发工具注册副作用（经 loop 顶部 `import fleetent.tools`）。

### D5 — 39 处 patch 随迁（本包最大机械面）
shim 上 patch 不生效（import * 复制引用）。处置：
- `patch("fleetent.agent_loop.X")` / `monkeypatch.setattr(agent_loop, "X", ...)` → 全部改 `fleetent.runtime.loop`；
- 符号名不变（patch 的是 loop 命名空间内的名字，如 `get_async_client_and_config`、`match_skill`、`dispatch`），仅前缀变；
- 逐文件机械替换后跑该文件测试，18 文件分批推进，避免一次性大爆炸。
- `context_mgr` 的测试直接 import 私有名（`_keep_tail` 等）→ 改 `fleetent.runtime.context`。

### D6 — 调用方改法
module-style（`from fleetent import agent_loop`）改 `from fleetent.runtime import loop as agent_loop`；符号式改 `from fleetent.runtime import run, run_stream`。`run_sync as run` 的别名习惯保留。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 39 处 patch 漏改 → 测试假绿/假红 | D5 分批 + 每批跑对应文件；收尾 `grep -rn "fleetent\.agent_loop\|setattr(agent_loop" tests` 必须为零 patch 残留 |
| loop↔sub_agent 循环 import | lazy 边界原样保留，只改路径；import 自检双向 |
| 注册副作用经由 loop 断链 | loop 顶部 `import fleetent.tools` 原样保留；回归断言 get_schemas() 非空 |
| 压缩 identity check（`m is tail[0]`）被误碰 | 纯移动不改逻辑；现有测试覆盖 |
| 1706 行大文件移动 + import 区重写易引入语序错误 | 只动 import 区；ruff/mypy + 全量 pytest 把关 |

## 验收

- `runtime/` 成包（13 模块 + `__init__.py`），公共 API 收口，`__all__` 显式。
- 13 个旧路径仅 re-export（无逻辑）。
- src 调用方全部走 `fleetent.runtime`；tests 零 patch 残留在旧命名空间。
- 全量 pytest 绿；ruff 干净；mypy 不新增错误模式。
- 自检：`from fleetent.runtime import run, run_stream, CancelToken`、`import fleetent.runtime.loop` 后 `get_schemas()` 非空、旧路径 `from fleetent.agent_loop import run` 仍成功。
