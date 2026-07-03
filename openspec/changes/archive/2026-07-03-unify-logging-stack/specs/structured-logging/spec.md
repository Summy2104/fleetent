# structured-logging 规格（delta）

## ADDED Requirements

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
