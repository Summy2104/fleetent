## Context

`redact_secrets`（sandbox-output-redaction，已合并）目前只在 `builtin_tools.run_code` 调用。工具结果落地点在 `runtime/loop.py`：`run()` 走 `_backfill_slots`（~858 行 `tool_content = ... truncate_tool_result(content)`），`run_stream()` 走内联 backfill（~2519 行同形）。两处都把 `content` 截断后 append 进 `messages`。约束：纯 agent 运行时、不改 redact_secrets 实现、不改 run_stream 审批（另一 change）。

## Goals / Non-Goals

**Goals:**
- 所有真实工具结果进 messages 前统一脱敏，覆盖 run() 与 run_stream。
- 顺序正确：hook 之后、截断之前。
- placeholder 豁免；始终开启。

**Non-Goals:**
- 不改 `redact_secrets` 的模式集（按需后续扩展，模式集已是 module-level 常量）。
- 不做可配置开关（安全默认始终开启）。
- 不脱敏 assistant 文本 / 最终回复（本 change 只管工具结果；最终回复另有 `_apply_output_transform`）。

## Decisions

**D1：脱敏点 = 两条 backfill 路径的「hook 之后、截断之前」。**
`_backfill_slots`：`content`（经 post_tool_use hook）→ `redact_secrets(content)` → `truncate_tool_result`。run_stream 内联 backfill 同样插入。两路径共用同一语义。

**D2：只脱敏非 placeholder。**
placeholder（deny/reject/approval 占位）是系统自产、无外部密钥；`is_placeholder` 为真时跳过 redact，省开销且语义清晰。

**D3：复用 redact_secrets，不抽新函数。**
直接 `from fleetent.integrations.sandbox.redaction import redact_secrets`。幂等，对已脱敏的 run_code 输出再过无副作用。runtime → integrations/sandbox 属 agent 运行时内部依赖，合规。

**D4：始终开启，无 config。**
输出防火墙是安全默认；redact_secrets 保守（PEM/JWT/vendor 前缀/Authorization/URL 凭证/密钥名赋值），全工具覆盖误伤低。若未来需豁免，再引 config，不在本 change。

## Risks / Trade-offs

- **误伤**：全工具输出脱敏可能把恰好匹配密钥模式的正常文本替换为 `[REDACTED]`。缓解：redact_secrets 模式高精度（结构化 + 仅密钥名信号赋值，已排除 bare KEY/AUTH）；误伤面小且偏安全侧。
- **双重脱敏 run_code**：run_code 输出被脱敏两次。redact_secrets 幂等，无副作用，仅极小冗余开销。
- **大输出脱敏开销**：对每个工具结果跑正则。结果通常不大；run_code 大输出本就走 spill 路径（已脱敏）。可接受。

## Migration Plan

增量：仅在两处 backfill 插入一行 redact，对不含密钥的输出零变化。无数据迁移。Rollback：移除两处 redact 调用。
