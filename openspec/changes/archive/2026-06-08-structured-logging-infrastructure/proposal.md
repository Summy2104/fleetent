## Why

`observability/structured_logging`（structured logger / 启动诊断 / 脱敏基线 / console·file 通道）是**纯横切日志基础设施**，被 37 个文件跨 9 个区域消费——`runtime`(13) / `integrations`(6) / `tui`(4) / `platform`(4) / `knowledge_base`(4) / `observability`(3) / `im_gateway`(2) / `session`(1) / `config.py`(1)。它无业务态、不 import `platform`，却物理躺在 `observability/`——一个被 CLAUDE.md 标为「agent 运行时模块」的目录下，定位错位（跨域底座被当成 agent 运行时业务）。

`platform` 自己也 import 它（4 处），说明它本就不是「agent 运行时」语义——它是 agent 与 platform 共同依赖的底座，性质等同已在 intelligence-layering 重构中被提为顶层基础设施的 `vector_store`。这是该重构精神在 observability 线上的延续（见 [`docs/architecture/intelligence-layering.md`](../../../docs/architecture/intelligence-layering.md) 对 vector_store 的处理），但范围独立、是一个纯物理迁移的小 change。

## What Changes

- **物理迁移**：`src/fleetent/observability/structured_logging.py` → `src/fleetent/structured_logging.py`，作为与 `runtime` / `session` / `vector_store` 并列的顶层基础设施模块（单文件，沿用 `config.py` / `db.py` / `paths.py` 的顶层单模块惯例；不建新 package）。
- **兼容 shim**：旧路径 `observability/structured_logging.py` 保留为 re-export shim，37 处调用方分批迁移，迁移完成前不删 shim（沿用 roadmap Shim 策略）。
- **依赖契约固化**：structured_logging MUST NOT import 任何业务能力模块，MUST NOT import `platform`；它只被消费（含被 platform 消费），不反向依赖。
- **行为零变更**：公共 API（`get_logger` / 七级 level / console·file 双通道 level / 脱敏基线 / 通道故障隔离）签名与语义完全不变。
- **target 名约束**：顶层模块名为 `structured_logging`，**不用 `logging`**（会 shadow stdlib）。

## Capabilities

### New Capabilities
- `structured-logging`: 把 structured_logging 作为独立基础设施模块的**放置与边界契约**固化为 spec（顶层位置 + 依赖方向规则 + 旧路径经 shim 可导入）。此前它只有行为 spec（在 `observability`），无放置/边界契约。

### Modified Capabilities
- `module-dependency-guardrails`: 把 `structured_logging` 加入基础设施组件依赖护栏——MUST 可经顶层路径 `fleetent.structured_logging` 导入，MUST NOT import 业务能力模块或 `platform`。

（`observability` spec 不作 Requirement 级改动：structured logger 的**行为** requirements 维持原样不变；其**模块归属/放置**契约由新的 `structured-logging` spec 承载。observability Purpose 的范围注记 + CLAUDE.md 文字随实现在 tasks 内更新，不构成 spec delta。）

## Impact

- **物理移动**：`observability/structured_logging.py`（约 7KB 单文件）→ 顶层 `structured_logging.py`。
- **调用方**（37 文件 import 路径更新，或暂走 shim）：`runtime`(13) / `integrations`(6) / `tui`(4) / `platform`(4) / `knowledge_base`(4) / `observability`(3，含 `__init__` 与 `traces`/`diagnostics`) / `im_gateway`(2) / `session`(1) / `config.py`。
- **shim**：`observability/structured_logging.py` re-export 顶层模块，保留至所有调用方迁移完成。
- **CLAUDE.md**：把 structured_logging 从「agent 运行时模块」列表移到基础设施定位（理由从"属 agent runtime"改为"跨域底座"）；本 change 内同步更新（不像 intelligence 那样统一收口，因这是独立单 change）。
- **不含**：logger 行为/level/脱敏逻辑变更；traces / usage / diagnostics / pilot_verification 的归属（仍留 observability，本 change 不动）；platform/maintenance 写 trace 的边界问题（属 governance 线，另议）。
