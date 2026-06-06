## Context

项目已有 `fleetent.observability.structured_logging` 自定义日志系统（component 命名、分级过滤、文件落盘、自动脱敏）。Yang Zhang 负责的模块（runtime、tui、sandbox、agent_lifecycle）当前分裂使用 structlog 和 stdlib logging，导致：

1. agent 运行时日志不落盘（structlog 仅打控制台）
2. 日志无脱敏（stdlib logging 不经过 `_redact_value`）
3. 无统一 component 标记，无法按子系统过滤

此次变更在不改变任何对外行为的前提下，将所有日志调用统一到自定义系统，并为当前零日志文件新增系统性覆盖。

## Goals / Non-Goals

**Goals:**
- 所有目标模块的日志调用统一使用 `get_logger("component")` API
- 每文件声明模块级私有 `_logger`，component 名用点号分层
- 三级事件策略：`info`（关键节点）/ `debug`（中间状态）/ `trace`（原始数据）
- 为 10 个当前零日志文件新增覆盖
- 删除目标模块对 `structlog` 和 `logging`（stdlib）的直接导入

**Non-Goals:**
- 不改变 `structured_logging.py` 本身的实现
- 不为 `cancellation.py` / `termination.py` 加日志（纯数据结构，无副作用）
- 不修改 `observability` 以外其他团队负责的模块

## Decisions

### D1：模块级私有 `_logger` 常量

每文件顶部声明一次，下划线前缀表明模块私有，不允许在函数内部临时创建。

```python
from fleetent.observability.structured_logging import get_logger
_logger = get_logger("runtime.loop")
```

**为何不用 structlog**：structlog 不落盘，无脱敏，与项目自定义系统并行维护成本高。

### D2：component 命名——点号分层

格式 `<subsystem>.<module>`，与文件路径对应：

| 文件 | component |
|------|-----------|
| `runtime/loop.py` | `runtime.loop` |
| `runtime/context.py` | `runtime.context` |
| `runtime/sub_agent.py` + `sub_agent_lifecycle.py` | `runtime.sub_agent` |
| `runtime/snapshot.py` | `runtime.snapshot` |
| `runtime/budget.py` | `runtime.budget` |
| `runtime/loop_detector.py` | `runtime.loop_detector` |
| `runtime/tool_guardrails.py` | `runtime.guardrails` |
| `runtime/message_hygiene.py` | `runtime.hygiene` |
| `runtime/error_classifier.py` | `runtime.error` |
| `runtime/agent_app.py` + `agent_init.py` | `runtime.agent_app` |
| `tui/app.py` | `tui.app` |
| `tui/backend.py` | `tui.backend` |
| `tui/dispatch.py` | `tui.dispatch` |
| `tui/transport.py` | `tui.transport` |
| `sandbox/client.py` | `sandbox.client` |
| `sandbox/config.py` | `sandbox.config` |
| `sandbox/cleanup.py` | `sandbox.cleanup` |
| `sandbox/enablement.py` | `sandbox.enablement` |
| `agent_lifecycle/controller.py` | `agent_lifecycle.controller` |
| `agent_lifecycle/materialize.py` | `agent_lifecycle.materialize` |
| `agent_lifecycle/lifecycle_admin_api.py` | `agent_lifecycle.api` |
| `im_gateway/slack_supervisor.py` | `im_gateway.slack` |

**为何不用模块路径（`__name__`）**：`__name__` 是实现路径，不是业务语义；component 字段用于日志过滤和告警路由，需稳定的业务标识符。

### D3：API 转换规则

| 来源 | 原写法 | 迁移后 |
|------|--------|--------|
| structlog `warning` | `logger.warning("evt", k=v)` | `_logger.warn("evt", k=v)` |
| stdlib printf | `logger.warning("msg %s", x)` | `_logger.warn("msg", x=x)` |
| stdlib `critical` | `logger.critical(...)` | `_logger.fatal(...)` |

### D4：高频事件用 `trace` 级别

loop 每轮迭代、工具调用原始结果等高频数据打 `trace`，生产默认 file_level=`debug` 不落盘，诊断时调低 trace 级别按需采集。

## Risks / Trade-offs

- **[风险] 新增日志调用增加文件 I/O**：`_write_jsonl` 每条同步写盘。`trace` 级别默认 file_level 为 `debug` 不触发，`info`/`debug` 在正常 agent 会话中频率可控。→ 可接受。
- **[风险] 测试需要 mock `_logger`**：新增日志调用不影响业务逻辑，但若测试断言日志事件需 patch `_logger`。→ 仅对验证日志行为的测试有影响，业务测试无需改动。

## Migration Plan

按模块分四批，每批一个 commit，TDD 顺序（先写测试验证日志调用，再改实现）：

1. **runtime** — loop、context、agent_app、sub_agent、sub_agent_lifecycle 迁移 + snapshot、budget、loop_detector、guardrails、hygiene、error 新增
2. **tui** — app、backend、dispatch、transport
3. **sandbox** — client、config、cleanup、enablement
4. **agent_lifecycle + im_gateway** — controller、materialize、api、slack_supervisor

回滚：每批独立 commit，可逐批 revert，不影响其他批次。
