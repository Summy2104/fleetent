## Why

sandbox 的密钥防护目前是**单向的**：`secrets.build_sandbox_env` 按名称过滤**入站**环境变量（不把 `*TOKEN*`/`*KEY*`/`*SECRET*` 传进容器），但**出站**毫无防护——容器内代码 `print` 出来的密钥（读了挂载文件、命中过滤名单之外的 env、硬编码、或 `curl -v` 打印的 `Authorization` 头）会原样进入 `run_code` 的返回值，从而进入对话上下文、被发往 LLM、并持久化到 session。

四个参考项目中只有 hermes-agent 做了出站脱敏（`redact_sensitive_text`）。对一个「数据不出内网」的 on-prem 平台，把密钥泄漏给（可能是外部的）模型 provider 是直接的数据主权风险。本 change 补齐出站脱敏，与既有入站过滤对称。

（注：sandbox trace `eval_logger.log_sandbox_exec` 只记录大小/耗时/退出码、从不记录 stdout/stderr 内容，故无需对 trace 脱敏；本 change 只作用于返回给 agent loop 的输出。）

## What Changes

- 新增 `src/fleetent/integrations/sandbox/redaction.py`：`redact_secrets(text) -> str`，按一组可扩展的模式把疑似密钥替换为 `[REDACTED]` 占位符，保留非敏感上下文（如 `Authorization:` 头名、`API_KEY=` 键名、URL 的协议与主机）。覆盖：PEM 私钥块、JWT、常见厂商 key 前缀（`sk-`/`sk-ant-`/`ghp_`/`gho_`/`github_pat_`/`xox[baprs]-`/`AKIA…`/`AIza…`/`glpat-`）、`Authorization` 头凭证、URL 内嵌 `user:pass@`、敏感命名的 `KEY=VALUE` 赋值。模式为模块级常量、可注入（沿用 `secrets.SENSITIVE_TOKENS` 的可扩展风格）。
- 在 `run_code`（`tools/builtin_tools.py`）输出组装处接线：返回前对 stdout、stderr 各自**先脱敏再截断**（先脱敏保证密钥不因截断在边界处逃逸）。trace 的字节大小仍按**原始**输出计（大小是输出量指标，不受脱敏影响）。
- sandbox 包 `__init__` 导出 `redact_secrets`。

## Capabilities

### New Capabilities
- `sandbox-output-redaction`: `run_code` 返回给 agent loop 的 stdout/stderr SHALL 在返回前对疑似密钥脱敏（替换为占位符、保留非敏感上下文），覆盖常见密钥形态且保守地不误伤普通输出；脱敏在截断之前进行；模式集可扩展。

### Modified Capabilities
<!-- 不 MODIFIED。`sandbox-secret-injection`（入站 env 过滤）与 `sandbox-output-truncation` 的既有需求不变；
     出站脱敏是与二者并列的新关注点，落在新 capability 下以 ADDED 表达。 -->

## Impact

- **代码**：新增 `integrations/sandbox/redaction.py`；`tools/builtin_tools.py` `run_code` 输出组装处插入脱敏；`integrations/sandbox/__init__.py` 导出。
- **测试**：新增 `tests/unit/test_sandbox_redaction.py`（各密钥形态被脱敏 + 普通输出不误伤 + 先脱敏后截断）；在 `tests/unit/test_tools.py` 的 run_code 段加「输出含密钥→返回值已脱敏」用例（沿用既有 `_make_manager` + `client.exec` mock）。无 LLM/Docker 真调。
- **不影响**：入站 env 过滤、截断预算、trace 大小语义、exec/超时/生命周期；不引入新依赖（仅用 `re`）。
