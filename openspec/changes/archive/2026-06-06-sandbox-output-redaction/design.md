## Context

`secrets.build_sandbox_env` 已做入站 env 名过滤（`secrets.SENSITIVE_TOKENS` 模块级可扩展集）。出站零防护：`run_code`（`builtin_tools.py`）把容器 stdout/stderr 经 `output_truncation.truncate_stream` 截断后直接拼进返回值 → 进对话、发 LLM、存 session。`run_code` 的 trace（`eval_logger.log_sandbox_exec`）只记大小/耗时/退出码，不记内容。

## Goals / Non-Goals

**Goals:**
- 在 `run_code` 返回前对 stdout/stderr 做基于模式的密钥脱敏，与入站过滤对称。
- 高精度覆盖结构化密钥（PEM/JWT/厂商前缀/连接串/Authorization 头），保守覆盖命名型 `KEY=VALUE`。
- 模式集模块级、可扩展，零新依赖（仅 `re`）。

**Non-Goals:**
- 不做占位符级 Secret（代码内只见随机占位符、网络边界透明替换）——非 Docker 原生，留作后续（sandbox.md 既有结论）。
- 不改入站过滤、截断预算、trace 大小语义。
- 不追求“零漏报”——脱敏是纵深防御层，不替代「不向容器注入凭证」这一首要原则。

## Decisions

**D1：独立 `redaction.py` 模块 + 模块级模式列表，镜像 `secrets.py` 风格。** 一组 `(compiled_pattern, replacement)`，`redact_secrets(text)` 顺序应用。模式为模块级常量（可 monkeypatch 扩展），与 `secrets.SENSITIVE_TOKENS` 的可扩展约定一致。

**D2：结构化模式高精度 + 命名型 KEY=VALUE 保守。** 结构化形态（PEM 块、JWT 三段、厂商前缀、`scheme://user:pass@`、`Authorization:` 头）以精确正则匹配，误报极低。命名型赋值仅在键名含明确密钥词（`TOKEN`/`SECRET`/`PASSWORD`/`PASSWD`/`CREDENTIAL`/`(API|ACCESS|PRIVATE|SECRET)[_-]?KEY`）时脱敏其值——**刻意不含裸 `KEY`/`AUTH`**，避免 `MONKEY`/`AUTHOR` 之类误伤（比 `secrets.py` 的入站名过滤更克制，因出站误伤会降低输出可用性）。

**D3：保留非敏感上下文，只替换敏感片段。** `Authorization: Bearer X` → `Authorization: [REDACTED]`（留头名）；`postgres://u:p@h` → `postgres://u:[REDACTED]@h`（留协议/用户/主机）；`API_KEY=x` → `API_KEY=[REDACTED]`（留键名）。便于模型仍理解输出结构。

**D4：先脱敏后截断。** `run_code` 对每个流 `truncate_stream(redact_secrets(raw), budget)`。先脱敏保证跨越截断边界的密钥也被处理；truncate 仍保证最终字节预算。trace 的 `stdout_bytes/stderr_bytes` 仍取**原始** `result.stdout/stderr` 的长度（输出量指标，与脱敏无关）。

**D5：新建 capability，不 MODIFIED 既有。** 出站脱敏与 `sandbox-secret-injection`（入站）、`sandbox-output-truncation`（截断）并列，互不改既有需求。

## Risks / Trade-offs

- **[漏报：未知密钥形态未被覆盖]** → 模式集可扩展；脱敏定位为纵深防御，首要防线仍是不向容器注入凭证（入站过滤）。文档明示非「零漏报」。
- **[误报：命名型赋值过度脱敏，如 `PASSWORD_POLICY=strict`]** → 接受保守过度脱敏（安全优先）；已通过去除裸 `KEY`/`AUTH` 把高频误伤压低。
- **[正则在超大输出上的开销]** → 输出已有截断上限语境；脱敏在截断前作用于原始流，但 sandbox 输出本就有体量约束，开销可接受；模式以锚定/前缀降低回溯。
