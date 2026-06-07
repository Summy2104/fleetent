## Context

`session-tool-result-extern` 建立了 externalize/rehydrate 纯函数，但 save/load 未调用它们。本 change 是该机制的接入（wiring），无新逻辑。

## Goals / Non-Goals

**Goals:**
- save 写盘前外部化大 tool result，load 读出后读回
- round-trip 透明，调用方无感知

**Non-Goals:**
- 不改 externalize/rehydrate 函数本身
- 不改 save/load 签名

## Decisions

### D1：接入位置

**save**（manager.py:493-495）：序列化前插入
```python
externalized = externalize_tool_results(session_id, messages)
tmp.write_text(json.dumps({"meta": meta, "messages": externalized}, ...))
```
写盘的是 `externalized`（引用版），原 `messages` 不变（externalize 是纯函数）。

**load**（manager.py:465-467）：读出后插入
```python
messages, _ = _read(session_id)
return rehydrate_tool_results(session_id, messages)
```

### D2：round-trip 正确性

- load: 文件(引用) → `_read` → rehydrate → 完整内容（调用方/agent 看到完整）
- save: 完整内容 → externalize → 文件(引用)
- 新会话（未 load）：从空起，save 时 externalize；下次 load rehydrate。一致
- tool_call_id 按 session 分目录，无跨会话冲突

### D3：失败容错沿用已有

externalize 写外部文件失败会抛异常——但 save 中 externalize 在原子写之前，若抛异常则整个 save 失败（消息未落盘）。这与「外部化是持久化的一部分」一致：若外部文件写不了，不应假装存了引用却丢内容。rehydrate 已有容错（文件缺失保留引用占位）。

## Risks / Trade-offs

- **[风险] externalize 在 save 写盘前抛异常导致 save 失败** → 可接受：外部文件是数据的一部分，写不了就该失败而非静默丢内容。50KB+ 写盘失败通常意味着磁盘问题，整个 save 都会失败
- **[风险] 已落盘的引用 session 被旧版本代码 load（无 rehydrate）** → 旧版本会把 `[stored:xxx]` 当普通内容——但本 change 一旦合并，load 总是 rehydrate；不存在新旧混用同一进程

## Migration Plan

无 schema 变更。部署即生效。已有内联 session 不受影响（无引用，rehydrate 原样返回）；新 save 的大 result 落到 .tool_outputs。
