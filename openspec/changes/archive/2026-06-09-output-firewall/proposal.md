## Why

`redact_secrets`（`integrations/sandbox/redaction.py`）目前**只**作用于 `run_code` 的 stdout/stderr（`builtin_tools.py`）。但任何工具的输出都可能把密钥带进模型上下文与持久化 session：`read_file` 读到 workspace 里的 `.env`、`search_content` 命中含 token 的文件、MCP 工具返回带 `Authorization: Bearer …` 的响应体——这些都绕过了当前只覆盖 run_code 的脱敏。

本 change 把脱敏提升为**输出防火墙**：所有工具结果在进入 `messages`（→ 模型 / session 持久化）之前统一过一遍 `redact_secrets`。

## What Changes

- **在 `runtime/loop.py` 的工具结果落地处统一脱敏**：`run()` 的 `_backfill_slots` 与 `run_stream` 的内联 backfill 两条路径，对**真实工具结果**（非 placeholder）在 **post_tool_use hook 之后、截断之前** 调用 `redact_secrets`。
  - **hook 之后**：hook 可能改写内容，防火墙覆盖 hook 的最终产物。
  - **截断之前**：与 run_code 现有「先脱敏再 cap」一致——避免密钥跨截断边界残留。
- **placeholder 不脱敏**：拒绝/审批/deny 的占位消息是系统自产文本、无外部密钥，跳过。
- **run_code 维持自身脱敏**：其输出会被再过一次，`redact_secrets` 幂等（已掩码文本无可匹配密钥），无副作用。
- **始终开启**：输出防火墙是安全默认，无开关；`redact_secrets` 模式集保守（结构化高精度 + 仅密钥名信号的赋值），全工具覆盖的误伤面低。

无 BREAKING：仅在工具结果文本中把疑似密钥替换为 `[REDACTED]`，对不含密钥的正常输出零变化。

## Capabilities

### New Capabilities
- `output-firewall`: 所有工具结果进入模型上下文 / session 持久化前统一经 `redact_secrets` 脱敏的契约——覆盖 run() 与 run_stream 两路径、在 hook 之后截断之前执行、placeholder 豁免、始终开启。

### Modified Capabilities
<!-- 无：sandbox-output-redaction 的 redact_secrets 行为不变，只是调用面从 run_code 扩到全工具输出。 -->

## Impact

- **代码**：`runtime/loop.py`（`_backfill_slots` + `run_stream` backfill 两处加 redact）；复用 `integrations/sandbox/redaction.redact_secrets`，不改其实现。
- **约束**：纯 agent 运行时（runtime/ → integrations/sandbox 同属 agent 运行时基础设施），不依赖 platform。
- **测试**：unit（含密钥的工具结果被脱敏后才入 messages；placeholder 不被改；脱敏在截断之前；run_stream 路径同样脱敏；不含密钥的输出不变）。
- **依赖**：基于已合并入 main 的 sandbox-output-redaction（redact_secrets）与 action-gate（placeholder slots）。
