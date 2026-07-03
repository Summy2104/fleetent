# structured-logging Specification

## Purpose
TBD - created by archiving change structured-logging-infrastructure. Update Purpose after archive.
## Requirements
### Requirement: Structured logging 作为独立基础设施模块

`structured_logging` SHALL 作为顶层独立基础设施模块存在（`src/fleetent/structured_logging.py`），与 agent runtime 模块并列，而非置于 `observability/`（被 CLAUDE.md 标为 agent 运行时）之下。它 SHALL 是无状态的跨域日志底座，提供结构化程序日志、级别过滤、console/file 双通道、脱敏基线与通道故障隔离能力，被 runtime / integrations / tui / platform / knowledge_base / im_gateway / session / config 等多方消费。

#### Scenario: 作为顶层底座被多方消费
- **WHEN** 任一 agent runtime 模块或 platform 模块需要结构化日志
- **THEN** 它 SHALL 通过 `fleetent.structured_logging` 的公共 API 使用
- **AND** structured_logging SHALL 不感知具体调用方的业务语义

#### Scenario: platform 亦可直接消费
- **WHEN** `platform` 下模块需要结构化日志
- **THEN** 它 SHALL 可直接 import `fleetent.structured_logging`（底座对 agent 与 platform 同等开放）

### Requirement: Structured logging 依赖方向约束

`structured_logging` MUST NOT import 任何业务能力模块（`runtime` / `memory` / `knowledge_base` / `reflection` / `long_term_ctx` / `session` / `tools` 等），MUST NOT import `fleetent.platform`。它只被消费，不反向依赖业务或控制面。

#### Scenario: 不依赖业务模块
- **WHEN** 检查 `structured_logging` 模块的 import
- **THEN** 其中 SHALL NOT 出现对业务能力模块的 import

#### Scenario: 不依赖 platform
- **WHEN** 检查 `structured_logging` 模块的 import
- **THEN** 其中 SHALL NOT 出现对 `fleetent.platform.*` 的 import

### Requirement: Structured logging 公共 API 稳定且旧路径过渡可用

迁移为顶层模块 SHALL NOT 改变 structured logger 的公共 API 签名或语义（`get_logger`、七级 level、console/file 分别配置 level、脱敏基线、通道故障隔离行为保持不变）。旧 import 路径 `fleetent.observability.structured_logging` SHALL 通过 re-export shim 在迁移过渡期保持可用；所有调用方迁移完成后 shim SHALL 被删除，且全仓 SHALL NOT 残留对旧路径的 import。

#### Scenario: 公共 API 行为不变
- **WHEN** 调用方经新路径 `fleetent.structured_logging` 使用任一公共 API
- **THEN** 其行为 SHALL 与迁移前完全一致

#### Scenario: 旧路径过渡期可用
- **WHEN** 既有代码经旧路径 `fleetent.observability.structured_logging` import
- **THEN** 在迁移过渡期 SHALL 仍然可用（re-export shim）

#### Scenario: 收口后无残留旧路径
- **WHEN** 所有调用方迁移完成、shim 删除后全仓检查 import
- **THEN** SHALL NOT 存在对 `fleetent.observability.structured_logging` 的 import

### Requirement: 异常日志保留 traceback
经 structured_logging Logger 记录已捕获异常时，调用点 SHALL 使用 `exception=exc` 关键字参数（由 `_exception_fields` 展开 error_type / error_message / stack / file / line），MUST NOT 以 `error=str(exc)` 等字符串化字段替代异常对象。既有违规存量（约 114 处）清零；AST 护栏测试扫描 src 内 logger 调用（方法名 ∈ {error, warn, warning, fatal, critical, exception}），拦截 `error=str(...)` 形态 kwarg，误伤 API 响应 payload 中的合法 `error=str(...)`（非 logger 调用）不在扫描范围。

#### Scenario: 异常日志携带栈信息
- **WHEN** 代码捕获异常并以 `logger.error("...", exception=exc)` 记录
- **THEN** 落盘 JSONL 记录含 error_type、error_message、stack、file、line 字段

#### Scenario: 护栏拦截丢栈写法
- **WHEN** src 内任一 logger 调用出现 `error=str(exc)` 风格 kwarg
- **THEN** AST 护栏测试失败并指出文件与行号

#### Scenario: 非 logger 调用不受影响
- **WHEN** API 响应构造等非 logger 调用中使用 `error=str(exc)`
- **THEN** 护栏不报告违规

