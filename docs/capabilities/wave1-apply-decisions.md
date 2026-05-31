# Wave-1 Apply 决策日志

> 全自主 apply 期间，遇到的冲突 / Open Question 及其解决记录，供 zy 最后核实。
> 每个 change 一节：遇到什么、怎么解的、影响。

## error-classification (AR5) — feat/error-classification

**前置核实结论(openai SDK 2.36.0):**
- `context_overflow` 判据：`APIStatusError` 且 `error.code == "context_length_exceeded"`（上下文超限以 400 + 该 code 呈现，仅状态码无法与普通 400 区分，故以 code 为准）。
- `auth_failed` 判据：`APIStatusError` 且 `status_code in {401,403}`（`AuthenticationError`/`PermissionDeniedError` 本就是 401/403，状态码判据自然覆盖，无需对子类单独 isinstance）。

**自行解决的冲突：**
1. tasks 提到的 `agent-runtime.md` 不存在 → 预留码标志位以 design.md D3 明确取值为准（tool_timeout/sandbox_* 全 False，mcp_disconnect 仅 should_retry）。
2. `tool_crash` 在表中但 `classify()` 永不返回（工具崩溃在 _safe_dispatch 归一化为字符串、不抛给 classify）→ 保留为词汇表项，守卫测试只断言不产出 4 个预留码。
3. `run_stream` 异常出口原 `return` 跳过了 log_run → 补 `_log_run_error` 在 return 前写 error_category，使"fallback 耗尽记分类码"对流式路径也成立。
4. ruff format 会误改 47 个无关文件 → 已还原，仅留本 change 的 6 个文件。

**影响：** 新增 error_classifier.py；agent_loop fallback 判定改读 should_switch_model（行为等价）；log_run 加 error_category 字段。416 passed，ruff/mypy 无新增（agent_loop 的 N814 _CU 为 AR1 既有遗留）。
**需 zy 核实：** 上述判据 #2（tool_crash 不产出）与 #3（流式补写 trace）是否认可。

## message-hygiene (AR6) — feat/message-hygiene

**实现：** 新增 message_hygiene.py（`sanitize(messages)->(clean,report)` 纯函数、`RepairKind`/`HygieneReport`/`MessageContractError`、三类修复按 D2 顺序、幂等）；run/run_stream 在 maybe_compress 后 LLM 前接入；log_run 加 hygiene_repairs 字段；不可修复 raise 由主循环按错误处理。

**MessageContractError 对齐 AR5：** 它是普通 Exception，经 AR5 `classify()` 落到 `unknown`（正是 design Open Question 预期），复用 `_log_run_error` 在循环出口写 `error_category="unknown"`。

**⚠️ 编排者验证抓到的关键 bug + 修复（重点核实）：** AR6 agent 最初把 run() 改为操作 sanitize 的副本（rebind `messages = sanitize(...)`），但 `im_gateway/normalizer.py:105-112` 的 IM 路径**依赖 run(history) 就地改 history** 再 `save(session_id, history)` 持久化（其注释明写"run already appended in-place, do NOT append again"）。rebind 会让 history 收不到 assistant/tool 追加 → **每个 IM session 只存到 [system,user]、丢失 AI 回复**（449 测试未覆盖故未报）。
**解法：** run() 改用**就地内容赋值** `messages[:] = maybe_compress(messages)` 与 `messages[:] = clean`，保住调用方列表引用（顺带也修了 maybe_compress 压缩时同样的 detach 隐患）。新增回归测试 `test_run_mutates_caller_messages_in_place` 守卫此契约。run_stream 的 messages 为内部局部变量、无外部 save 依赖，不受影响。

**agent 自解冲突：** 同名占位可达性（重写为实际可达用例）、test mock 的 model_dump 返回真 dict、stale 行号更新。

**影响：** 450 passed。run() 现保证就地改调用方 messages（IM 持久化正常）。
**需 zy 核实：** 上述就地赋值修复（run() mutation 契约）是否认可；MessageContractError→unknown 的处理是否认可。

## multimodal-input (AR21) — feat/multimodal-input

**实现：** 新增 multimodal.py（is_multimodal_content/build_image_block(base64)/build_message_with_images/has_image_block/非图片归一化占位）；agent_loop content 放宽 str|list、user_input 取文本块、`_select_route` 按 has_image_block 选 vision/default 路由；context_mgr.estimate_tokens 图片块计固定 1000 token；eval_logger._serialize 图片块→`[图片:mime,字节]` 占位；model_router ROUTES 加 vision task_type。

**D6 视觉路由（方案A）：** 含图片但 ROUTES 无 vision → `RuntimeError`（LLM 调用前，运行时查 `model_router.ROUTES` 以便 monkeypatch）。run/run_stream 共用。

**自解冲突：**
1. get_async_client_and_config 对未知 task_type 静默回落 default → 无法检测"无 vision 路由"。解：在 `_select_route` 显式 `"vision" not in model_router.ROUTES` 检查（引模块属性、非 bound import，便于测试 monkeypatch）。
2. run_stream 是 user_input:str 无 messages → 加可选 `images: list[tuple[bytes,str]]` 参数，经 build_message_with_images 构造;server.py 接入属后续(Non-Goal)。
3. 每图占位 token = 1000（保守常量；Anthropic 按像素约 ≤1600，避免 100KB base64 误加 ~25k token）。

**AR6 协调：** sanitize 只看 role/tool_call 配对、不索引 content，list content 原样通过；加守卫 `test_image_message_passes_sanitize`。run() 的 messages[:] 就地改未破坏。

**影响：** 477 passed，ruff/mypy 无新增。
**需 zy 核实：** 每图 1000 token 占位是否合理;vision task_type 默认指向(本次用 Sonnet vision,部署可改);run_stream 的 images 参数形态。

## compression-dual-threshold (AR12) — feat/compression-dual-threshold

**实现：** context_mgr 双阈值——`tmax_ratio`(触发,默认0.8)/`tretained_ratio`(目标,默认0.6);`maybe_compress(..., force=False)` 触发改读 tmax、force 实现手动 /compact;新增 `compress_for_context_overflow()` 错误触发入口;`_select_tail` 按目标线动态收缩尾部、tool-pair 完整性优先(可略超目标线、不截断 tool 对);system 头部继续单独保留(prompt-cache 依赖不破坏)。复用 AR21 改过的 estimate_tokens。

**D5 移除 context_compress_threshold：** config.py 删字段 + 新增 context_tmax_ratio/context_tretained_ratio;_default_config 改返回新键;.env.example 迁移(CONTEXT_COMPRESS_THRESHOLD→CONTEXT_TMAX_RATIO + 新增 CONTEXT_TRETAINED_RATIO);测试键更新 + 加 `test_context_compress_threshold_removed` 守卫。src 零残留。

**自解冲突：**
1. 非法配置(tretained≥tmax)选 **raise ValueError** 而非 clamp(spec 二选一,raise 更明确可断言)。
2. 摘要占位 token 用 `_SUMMARY_OVERHEAD_TOKENS=512`(对齐 _summarize 的 max_tokens=512)投影尾部,避免压后超目标。
3. 手动触发用 `force` 参数(最小侵入)、错误触发用独立函数 `compress_for_context_overflow`(语义清晰,design D4 留作实现决策)。

**影响：** 489 passed,ruff/mypy 无新增。解锁 prompt-cache(其依赖 AR12 的 system 头部保留)。
**需 zy 核实：** 非法配置 raise(非 clamp);_SUMMARY_OVERHEAD_TOKENS=512 估算;force 参数 vs 独立函数的入口形态。

## mcp-http-streamable (MCP1) — feat/mcp-http-streamable

**实现(方案A:替换非标 http 为标准 Streamable HTTP,transport 值仍 "http"):** 重写 `_register_http_server`(initialize 握手 → 存 Mcp-Session-Id → tools/list)与 `_call_http_tool`(tools/call + session id + 递增 id + Content-Type 分流);纯函数 `_extract_jsonrpc_from_sse(body,request_id)`(忽略注释、拼多行 data、按 id 过滤);session_id 与 _request_id 按 McpServerConfig 实例持有(field repr/compare=False,无全局可变态);Accept 协商;复用 transport=="http" 分支/命名空间/register_all 降级/Bearer 认证。

**自解冲突:**
1. protocolVersion 取规范最新 `2025-06-18`(design Open Question)。
2. initialize 后补发 best-effort `notifications/initialized`(失败仅 debug log 不阻断),兼容要/不要该通知的服务。
3. JSON 单响应不强制 id 匹配(无多事件干扰);SSE 严格按 id 过滤。

**影响:** 509 passed;mcp_client 的 2 个 no-any-return 为既有同模式,无新增。stdio 路径无回归。
**需 zy 核实:** protocolVersion=2025-06-18、是否所有目标 MCP server 都接受/需要 notifications/initialized。
