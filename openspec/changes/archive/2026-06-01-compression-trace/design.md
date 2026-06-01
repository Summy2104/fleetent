## Context

`context_mgr._compress(messages, cfg)`（`context_mgr.py`）是所有压缩的唯一汇聚点，两个公开入口都落到它：
- `maybe_compress(messages, config, *, force)`：`force=False` 时仅当超 `Tmax` 触发线才压缩（自动）；`force=True` 是 `/compact` 手动语义。
- `compress_for_context_overflow(messages, config)`：LLM「上下文过长」错误入口，无条件压缩到 `Tretained`。

`_compress` 内部有三种返回形态（皆为本 change 要追溯的对象）：
1. **正常摘要**：`[*head, summary_msg, *tail]`，`summary_msg` 文本为 `_SUMMARY_PREFIX + "\n" + summary_text`（AR14）。
2. **静态降级**：LLM 摘要失败（`_summarize` 返回 None），`[*head, notice_msg, *tail]`，`notice_msg` 为 `_MIDDLE_OMITTED_NOTICE`（AR14 D3）。
3. **无中段退化**：head/tail 已覆盖全部、middle 为空 → 不插摘要，直接返回去重后的 head+tail（AR13 D4）。

`eval_logger` 是 append-only JSONL，单一可注入常量 `TRACE_PATH`，三个 writer（`log_run` / `log` / `log_sandbox_exec`）各打一种 `kind`。既有克制原则：`log_sandbox_exec` 只记 sizes/timing/exit_code 不落 stdout/code 源；`_serialize` 把 base64 图片替换为占位符——**只记元数据，不落原始大对象**。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM（标准库写 JSONL，无 sqlite3 需求）；禁止全局可变状态（`TRACE_PATH` 可 monkeypatch）；新模块/函数 mypy strict 全注解；行长 100；不吞异常（trace 写失败要 log）；TDD Hard Gate；测试 mock LLM、`TRACE_PATH` 隔离到 `tmp_path`。

## Goals / Non-Goals

**Goals:**
- 每次压缩（正常 / 降级 / 退化三分支）写入一条 `kind: "compression"` 的 trace，含：触发原因、压缩前后 token 数与消息数、保留（头 + 尾）与丢弃（中段）的计数、产出摘要的标识（指纹 + 长度）、结果类型、压缩耗时、使用的摘要模型。
- trace 复用 `eval_logger`（新增 `log_compression` writer + `kind: "compression"`），沿用 `TRACE_PATH` 与「只记元数据」克制原则。
- trace 写入失败不影响压缩主流程（只 log，不抛）。
- 触发原因从两个公开入口透传到 `_compress`，不破坏其 `list → list` 公开语义。

**Non-Goals:**
- 不改压缩算法（AR13 分层、AR14 增量摘要 / 降级 / 退化语义）。
- 不落原始消息内容、不落摘要正文整段（只记指纹 + 长度）。
- 不实现 AR17 反抖动（连续 3 次节省率 < 10% 关闭自动压缩）——那是独立功能点；本 change 只记单次元数据，反抖动可日后基于这些 trace 实现。
- 不新增持久化结构、不引入 sqlite 表（trace 是 JSONL，沿用 `eval_logger`）。
- 不引入新依赖。

## Decisions

### D1：新增 `eval_logger.log_compression`，`kind: "compression"`
在 `eval_logger.py` 增 writer：

```python
def log_compression(
    trigger: str,                 # "tmax" / "manual" / "context_overflow"
    outcome: str,                 # "summarized" / "degraded" / "no_middle"
    tokens_before: int,
    tokens_after: int,
    messages_before: int,
    messages_after: int,
    head_count: int,
    tail_count: int,
    dropped_count: int,           # 进摘要被丢弃的中段消息数
    elapsed_s: float,
    summary_model: str | None = None,
    summary_fingerprint: str | None = None,   # 摘要正文的截断哈希，不落正文
    summary_len: int | None = None,           # 摘要正文字符数
    user_id: str | None = None,
    agent_name: str | None = None,
    session_id: str | None = None,
) -> None: ...
```

写法与既有 writer 一致：`ts` + `kind: "compression"` + 必填字段，可选字段「非 None 才写入」，`TRACE_PATH.parent.mkdir` + append 一行 JSON。

**为何**：复用唯一 trace 出口与 `kind` taxonomy，运维一处查所有 trace；新增一个 `kind` 而非塞进 `agent_run`，因为压缩是 agent_run 内部的子事件、独立可查（按 `kind == "compression"` 过滤即得全部压缩历史）。字段直接对齐 AR16 文案要求（触发原因 / 前后消息数与 token 数 / 耗时 / 摘要模型），并补足「保留与丢弃范围」（head/tail/dropped 计数）与「摘要标识」（指纹 + 长度）。
**Alternatives**：①把压缩元数据挂到 `log_run` 的新字段——被否，压缩可能一次 run 内发生多次（自动 + 手动 + 错误重试），挂单条 run 无法表达多次压缩，且不是每次 run 都压缩；②新建独立压缩 trace 文件 / sqlite 表——被否，违背「复用 `eval_logger` 单一出口」，且引入新持久化结构。

### D2：只记元数据 + 摘要指纹，绝不落原始消息 / 摘要正文
- 保留 / 丢弃用**计数 + token 数**表达（`head_count` / `tail_count` / `dropped_count`、`tokens_before/after`、`messages_before/after`），不落消息对象。
- 摘要标识 = `summary_fingerprint`（摘要正文的短哈希，如 sha256 前 16 hex）+ `summary_len`（字符数），**不落摘要正文**。指纹足以在多条 trace 间判断「是否同一摘要 / 是否变化」，定位「上下文被压成什么样」的入口，又不把可能含敏感对话的摘要正文写进 append-only 日志。

**为何**：与 `eval_logger` 既有克制原则（`log_sandbox_exec` 不落 stdout、`_serialize` 占位图片）严格一致，避免日志膨胀与敏感数据落盘；指纹 + 长度在「可追溯」与「克制」之间取平衡——能回答「压成什么样、是否变化」，但不暴露正文。
**Alternatives**：落摘要正文全文——被否，违背克制原则、可能含敏感内容、长会话日志膨胀；完全不记摘要任何信息——被否，AR16 要可追溯「上下文被压缩成什么样」，至少需要一个稳定标识。

### D3：触发原因从公开入口透传到 `_compress`，不破坏 `list → list` 语义
- `_compress` 增内部参数 `trigger: str`（默认 `"tmax"`）。
- `maybe_compress` 据 `force` 决定：`force=True → "manual"`，否则 `"tmax"`，透传给 `_compress`。
- `compress_for_context_overflow` 透传 `"context_overflow"`。
- 两个公开入口的对外签名与 `list → list` 返回语义**不变**（`trigger` 是内部传递，不进公开签名的语义契约）。

**为何**：`_compress` 是唯一汇聚点，在此采集 + 写 trace 一处覆盖三入口三分支；触发原因只有入口知道，必须透传。`_compress` 是模块内部函数（下划线前缀），加参数不破坏公开 API。
**Alternatives**：在三个入口各自写 trace——被否，重复代码且 `_compress` 内部的 outcome（降级 / 退化）入口看不到，仍需下沉；用模块级可变变量记 trigger——被否，违反「禁止全局可变状态」。

### D3a：本 change 接通 `session_id` 归因，随 trigger 一并透传到 `_compress`

- 与 `trigger` 同范式：`maybe_compress` / `compress_for_context_overflow` 增可选 kwarg `session_id: str | None = None`（及可选 `user_id` / `agent_name`，默认 None），随 trigger 经调用链（agent_loop → `maybe_compress` / `compress_for_context_overflow` → `_compress`）一并透传到 `log_compression`。
- agent_loop 调用压缩入口时，有 `session_id`（及 `user_id` / `agent_name`）则传入、无则 None；CLI 无 session 时即为 None。
- 公开入口加可选 kwarg（默认 None）**不破坏** `list → list` 返回语义（kwarg 不进语义契约，缺省即旧行为）。
- `_compress` 把 `session_id`（及 `user_id` / `agent_name`）随其余元数据一并交给 `log_compression`，由后者「非 None 才写入」（与 `log_run` 可选字段同范式）。

**为何**：一次 run 可能多次压缩（自动 + 手动 + 错误重试），无 session 归因则压缩 trace 浮空、只能靠时间戳硬猜「哪个 session 压了几次」，取证价值大减。经可选 kwarg（默认 None）透传，零耦合代价：调用方有则传、无则 None，与 `log_run` 既有可选归因字段一致。本 change 直接接通调用链，不再留作 Open Question。
**Alternatives**：把归因留作纯可选字段、本 change 不接通调用链——被否，调用链不接通则字段永远为 None、归因能力名存实亡；用全局/上下文变量隐式携带 session——被否，违反「禁止全局可变状态」。

### D4：在 `_compress` 每个返回分支前采集并写 trace；耗时只计本次压缩
- `_compress` 入口记 `t0 = time.monotonic()` 与 `tokens_before = estimate_tokens(messages)`、`messages_before = len(messages)`。
- 每个返回分支（no_middle / degraded / summarized）构造结果列表后、return 前，算 `tokens_after` / `messages_after` / `head_count` / `tail_count` / `dropped_count`，`elapsed_s = time.monotonic() - t0`，调用 `log_compression`，再 return。
- `summary_model` 取自摘要实际使用的路由模型（`get_client_and_config("memory_extraction")` 的 `cfg.model`）；降级 / 退化分支无摘要则为 None。

**为何**：三分支共享同一套 before 采集，after 因分支而异；在 return 前统一写一条，保证每次压缩恰好一条 trace。耗时计 `_compress` 全程（含 LLM 摘要调用），正是 AR16 要的「压缩耗时」。
**Decision（summary_model 采集）**：`summary_model` 由 `_compress` 直接复用同一路由 `get_client_and_config("memory_extraction").model` 解析摘要模型名，**不改 `_summarize` 签名**。降级 / 退化分支无摘要则为 None。
**为何**：`_summarize` 用的就是 `get_client_and_config("memory_extraction")` 这条路由，`_compress` 复用同一解析即得真实模型名，避免为采集可观测性而改动内部函数 `_summarize` 的返回契约（`text` → `(text, model)`），改动面更小。
**Alternatives**：让 `_summarize` 返回 `(text, model)`——被否，为附加可观测性扩大 `_summarize` 签名不值当，`_compress` 复用路由解析即可拿到同一模型名。

### D5：trace 写入失败不影响压缩主流程
`_compress` 调 `log_compression` 包在 `try/except` 内：异常只 `logger.warning("compression_trace_failed", ...)`，绝不向 `_compress` 调用方（agent_loop 主循环）抛出。

**为何**：压缩本身是上下文治理的降级安全路径（AR14 摘要失败都能静态降级不崩溃）；可追溯是**附加可观测性**，绝不能反过来成为新的失败点。不吞异常 = 记日志（符合 CLAUDE.md「catch 后必须 log 或 re-raise」，此处 log）。
**Alternatives**：trace 失败时连压缩结果一起回滚 / 抛出——被否，可观测性不该影响功能正确性。

## Risks / Trade-offs

- [`summary_model` 采集] → 已定（D4）：`_compress` 复用 `get_client_and_config("memory_extraction").model` 解析模型名，**不改 `_summarize` 签名**，影响面最小。
- [指纹算法选择（哈希算法 / 截断长度）] → 用标准库 `hashlib`（无新依赖），取短前缀；spec 只要求「稳定标识 + 长度」，算法细节在实现定。
- [一次 agent run 多次压缩产生多条 trace] → 正是预期（每次压缩一条）；已定（D3a）：本 change 接通调用链透传 `session_id`（及可选 `user_id` / `agent_name`），同一 session 多次压缩的 trace 均带该 `session_id`，可据此聚合归因。
- [trace 写入 IO 抖动影响压缩延迟] → 写一行 JSON 的开销远小于 LLM 摘要调用；且 D5 保证失败不阻断；可接受。

## Open Questions

- 摘要指纹算法与截断长度（sha256 前 16 hex？）—— 实现时定，spec 不锁。
- 是否需要 admin CLI / `/health` 暴露「最近 N 次压缩节省率」便于运维核对（也是 AR17 反抖动的数据基础）？属后续功能，本 change 只保证元数据落盘。
