## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `eval_logger.py` 的统一 trace 出口形态：单一可注入常量 `TRACE_PATH`、三个 writer（`log_run` / `log` / `log_sandbox_exec`）各打一种 `kind`（`agent_run` / `im_message` / `sandbox_exec`）、可选字段「非 None 才写入」、`TRACE_PATH.parent.mkdir` + append 一行 JSON 的写法；确认新增 `kind: "compression"` 不与既有冲突
- [x] 1.2 核实 `eval_logger` 既有克制原则：`log_sandbox_exec` 只记 sizes/timing/exit_code 不落 stdout/code 源、`_serialize`/`_placeholder_images` 占位 base64 图片——本 change 沿用「只记元数据 / 摘要标识，不落原始大对象」
- [x] 1.3 核实 `context_mgr._compress` 的唯一汇聚点地位与三种返回分支：正常摘要 `[*head, summary_msg, *tail]`、静态降级 `[*head, notice_msg, *tail]`（`_summarize` 返回 None）、无中段退化（middle 为空，返回去重 head+tail）；确认 `maybe_compress`（`force` → 手动 / 否则自动）与 `compress_for_context_overflow`（错误触发）两入口均落到 `_compress`
- [x] 1.4 核实摘要消息标识 `_SUMMARY_PREFIX` 与降级 `_MIDDLE_OMITTED_NOTICE`、摘要模型来自 `get_client_and_config("memory_extraction")` 的 `cfg.model`；`summary_model` 由 `_compress` 复用同一路由解析模型名（不改 `_summarize` 签名）
- [x] 1.5 核实 `agent_loop.py` 调用 `maybe_compress` / `compress_for_context_overflow` 的位置，及其是否持有 `session_id` / `user_id` / `agent_name`（确认哪些可透传、CLI 路径无 session）

## 2. eval_logger 压缩 trace writer（eval_logger.py）

- [x] 2.1 Write failing tests for log_compression：`log_compression(...)` 写出一条 `kind: "compression"` 记录，含 `ts` + 触发原因 + 结果类型 + 压缩前后 token 数与消息数 + 头/尾保留计数 + 丢弃中段计数 + 耗时 + 摘要模型 + 摘要指纹 + 摘要长度；可选字段（model/fingerprint/len/user_id/agent_name/session_id）非 None 才写入。`monkeypatch TRACE_PATH` 到 tmp_path。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `log_compression`（沿用 `TRACE_PATH` + append JSONL + 可选字段非 None 才写入的既有写法），看到绿
- [x] 2.3 Write failing tests：trace 记录 MUST NOT 含原始消息内容、MUST NOT 含摘要正文全文；摘要仅以指纹 + 长度表达；相同摘要正文产出相同指纹。看到红
- [x] 2.4 Implement 摘要指纹（标准库 `hashlib` 短哈希，无新依赖）+ 长度，断言不落正文，看到绿

## 3. 触发原因透传到 _compress（context_mgr.py）

- [x] 3.1 Write failing tests：`maybe_compress(force=True)` → 触发原因「手动」、`force=False` 越过 Tmax → 「自动」、`compress_for_context_overflow` → 「错误触发」，三类经 `_compress` 透传到写出的压缩 trace。`monkeypatch TRACE_PATH`、`patch get_client_and_config`。看到红
- [x] 3.2 Implement：`_compress` 增内部参数 `trigger`（默认自动），两公开入口据来源透传；不改两入口对外 `list → list` 语义，看到绿

## 3a. session_id 归因键透传（context_mgr.py + agent_loop.py）

- [x] 3a.1 Write failing tests：agent_loop 经 `maybe_compress` / `compress_for_context_overflow` 传入 `session_id`（及可选 `user_id` / `agent_name`）时，写出的压缩 trace 含该 `session_id`；同一 session 多次压缩的 trace 均带相同 `session_id`；缺省（None）时压缩 trace 不写该字段且不报错。`monkeypatch TRACE_PATH`、`patch get_client_and_config`。看到红
- [x] 3a.2 Implement：`maybe_compress` / `compress_for_context_overflow` 增可选 kwarg `session_id`（及 `user_id` / `agent_name`，默认 None），随 `trigger` 透传到 `_compress` 再交给 `log_compression`（非 None 才写入）；不改两入口对外 `list → list` 返回语义。看到绿
- [x] 3a.3 Implement：agent_loop 调用压缩入口处传入持有的 `session_id`（及 `user_id` / `agent_name`），无则 None。看到绿

## 4. 在 _compress 三分支采集元数据并写 trace（context_mgr.py）

- [x] 4.1 Write failing tests：正常摘要分支写一条 `outcome=正常摘要` trace，含正确的压缩前/后 token 数与消息数、头/尾/丢弃计数、摘要模型、摘要指纹与长度、耗时（>= 0）。看到红
- [x] 4.2 Implement：`_compress` 入口采集 `tokens_before`/`messages_before` + `t0`；正常摘要分支 return 前算 after/计数/耗时，`summary_model` 复用 `get_client_and_config("memory_extraction").model` 解析（不改 `_summarize` 签名），调 `log_compression`，看到绿
- [x] 4.3 Write failing tests：静态降级分支（`_summarize` mock 返回 None）写一条 `outcome=静态降级` trace，摘要模型为空、无摘要指纹/正文。看到红
- [x] 4.4 Implement 降级分支采集 + 写 trace，看到绿
- [x] 4.5 Write failing tests：无中段退化分支（middle 为空）写一条 `outcome=无中段退化` trace，摘要相关字段为空。看到红
- [x] 4.6 Implement 退化分支采集 + 写 trace，看到绿
- [x] 4.7 Write failing test：每次压缩恰好写一条压缩 trace（三分支各一条，不漏不重）。看到红/绿确认

## 5. trace 写入失败不影响压缩主流程（context_mgr.py）

- [x] 5.1 Write failing test：`log_compression` mock 抛异常时，`_compress` 仍返回原本对 LLM 合法的压缩结果序列、不向调用方抛异常、写失败被 log（不静默吞）。看到红
- [x] 5.2 Implement：`_compress` 中 `log_compression` 调用包 `try/except`，异常只 `logger.warning`，看到绿

## 6. 收尾

- [x] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 6.3 `uv run mypy src` 无新增错误
