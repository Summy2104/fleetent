## Context

`save(token_usage=...)` 已就绪但无人传。run() 内部 L1354 拿到 `usage = response.usage`，仅用于日志/trace，未透出给调用方。run() 返回纯 str，被 run_sync/normalizer/cron/sub_agent/大量测试调用。

## Goals / Non-Goals

**Goals:**
- run() 透出实际 token usage，normalizer 传给 save
- 零破坏现有 run() 调用方

**Non-Goals:**
- 不改 run() 返回类型
- 不接入 run_stream / run_sync / cron（IM 路径优先；其他渐进）

## Decisions

### D9：用 usage_out 出参，不改 run() 返回类型

**决策**：run() 加 `usage_out: list | None = None`；正常完成时 append `(prompt_tokens, completion_tokens)`。不改返回类型。

**理由**：run() 返回 str 被广泛依赖（run_sync、normalizer、cron、sub_agent、几十处测试）。改成 tuple 会破坏所有调用方和测试。出参 list 是纯增量：默认 None 时零行为变化，只有显式传入的调用方（normalizer）受益。

**填充位置**：loop.py L1354 `usage = response.usage if response else None` 之后：
```python
if usage_out is not None and usage is not None:
    usage_out.append((
        getattr(usage, "prompt_tokens", 0),
        getattr(usage, "completion_tokens", 0),
    ))
```

**early return 安全**：run() 在 mcp_strict_unavailable 等场景 L1221 提前 return（未跑 LLM，无 usage）。此时 usage_out 保持空，normalizer 读 `usage_out[0] if usage_out else None` → None → save 不累计。正确。

### normalizer 接入

```python
usage_out: list = []
response = await agent_loop.run(..., usage_out=usage_out)
...
await session_mgr.save(
    session_id, history,
    token_usage=usage_out[0] if usage_out else None,
)
```

## Risks / Trade-offs

- **[风险] usage_out 出参不如返回值显式** → 取舍：零破坏 > 接口纯净。出参模式在 Python 不罕见（类似 callback sink）；注释说明用途
- **[风险] 多轮 run 内部理论上可能 append 多次** → run 单次调用只在完成时 append 一次；usage 是整轮聚合的 response.usage。normalizer 取 [0]

## Migration Plan

无 schema 变更。部署即生效——IM 路径 session 开始累计 token。其他路径不传 usage_out，行为不变。
