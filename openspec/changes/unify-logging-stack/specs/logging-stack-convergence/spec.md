# logging-stack-convergence 规格（delta）

## ADDED Requirements

### Requirement: src 内 structlog 使用清零
src 内业务与运行时代码 MUST NOT 使用 structlog（`import structlog` 与 `structlog.get_logger`）。唯一豁免为 `fleetent/logging_setup.py`（负责 `structlog.configure`，保证三方库经 structlog 的输出跟随 LOG_FORMAT）。既有 6 处使用（im_gateway/slack.py、im_gateway/telegram.py、im_gateway/normalizer.py、im_gateway/outbound.py、skills/registry.py、tools/plugin_loader.py）迁移至 `fleetent.structured_logging.get_logger`。

#### Scenario: 遗留站点全部迁移
- **WHEN** 检视上述 6 个文件
- **THEN** 均从 fleetent.structured_logging 获取 logger，调用风格为 event + kwargs，`.warning(` 改为 `.warn(`

#### Scenario: 护栏拦截新增 structlog
- **WHEN** src 内 logging_setup 之外任一文件出现 `import structlog`
- **THEN** 护栏测试失败

### Requirement: stdlib logging.getLogger 存量棘轮
护栏测试 SHALL 内置 src 内使用 `logging.getLogger` 的文件冻结清单（当前存量），并断言实际集合是清单子集：新增文件即失败；存量迁移后 MUST 同步从清单移除（棘轮只减不增）。`import logging` 本身不受限（级别常量等合法用途）。

#### Scenario: 新增 stdlib logger 被拒
- **WHEN** 清单外的 src 文件新出现 `logging.getLogger` 调用
- **THEN** 护栏测试失败并指出该文件

#### Scenario: 棘轮只减不增
- **WHEN** 某存量文件迁移到 structured_logging 后从清单移除
- **THEN** 护栏保持通过；将其重新加回清单属违规变更（注释声明该约定）

### Requirement: 新代码统一使用 structured_logging
新增运行时/服务代码获取 logger SHALL 使用 `fleetent.structured_logging.get_logger(component)`。CLI 面向用户的 print 输出与 TUI 自建渲染 sink 不在此约束内。

#### Scenario: 约定可被机器验证
- **WHEN** 运行本能力两条护栏（structlog 禁用 + stdlib 棘轮）
- **THEN** 通过即代表新代码无法引入第三套 logger 路径
