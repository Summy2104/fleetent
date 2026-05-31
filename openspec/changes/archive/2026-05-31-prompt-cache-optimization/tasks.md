## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `run_sync` / `run_stream` 现状提示组装：`full_system = f"{memory_ctx}\n\n{system_prompt}"` + 追加 matched skill，全拼进首条 system（确认在 `run_sync` L449-459、`run_stream` L489-503；`run()` 收预构建 messages，无组装）；`match_skill` / `load_skill` / `load_memories` 功能契约不变
- [x] 1.2 定 memory/skill 后置承载形式：**独立的第二条 system 消息**（base system 作 `messages[0]` 稳定前缀，memory+skill 合并为 `messages[1]` 的 system 消息），后端无关、不依赖单条多段 system 行为
- [x] 1.3 定缓存指标提取口径：从 `usage` 对象尽力 getattr `cache_read_input_tokens` / `cache_creation_input_tokens`（Anthropic 风格）+ `prompt_tokens_details.cached_tokens`（OpenAI 风格），缺失则跳过；流式路径合成 usage 不含这些字段，安全降级为不记
- [x] 1.4 确认 `log_run` 签名末位加 `cache_tokens: dict | None = None`（同 `stop_reason`/`error_category` 模式）；AR12 `_compress` 已单独保留 system_msgs 头部，重排后 base system 仍在被保留头部内

## 2. 提示组装重排（稳定前缀）

- [x] 2.1 Write failing tests：构造两次"基础 system 相同、memory/skill 不同"的组装，断言基础 system 前缀部分逐字相同（差异仅在其后）；断言 memory 与 skill 内容仍在提示中（功能等价）。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement：`run_sync` / `run_stream` 经新 `_assemble_prompt` 改为 base system 作首条稳定 system 前缀、memory_ctx 与 matched skill 合并为其后第二条 system 消息（无可变内容则省略）。看到绿

## 3. 缓存指标写入 trace

- [x] 3.1 Write failing tests：mock `response.usage` 含缓存指标 → `log_run` 收到 `cache_tokens`（Anthropic + OpenAI 两种风格 + 流式 usage chunk）；`usage` 不含缓存字段 → 不报错、不写该字段。看到红
- [x] 3.2 Implement：`log_run` 增加 `cache_tokens: dict | None = None`（默认 None 向后兼容，非 None 写入 entry）；新 `_extract_cache_tokens` 从 `usage` 尽力提取，`run`（response.usage）/ `run_stream`（usage chunk）收尾传入。看到绿

## 4. 后端无关守卫 + AR12 协调

- [x] 4.1 Write failing tests：断言主循环 LLM 调用请求 kwargs 与 messages 中**不含** `cache_control` 标记——回归守卫。作为既有行为的防回归守卫（实现未引入标记，守卫即绿）
- [x] 4.2 确认/Implement：不注入任何缓存标记（依赖自动前缀缓存）；`_assemble_prompt` docstring 标注稳定前缀意图，`context_mgr._compress` 已单独保留 system 头部（base system + 变量 system 消息），AR12 协调点在 test_context_mgr 增守卫 `test_compress_preserves_base_system_cacheable_prefix`。看到绿

## 5. 收尾

- [x] 5.1 全量 `ANTHROPIC_API_KEY=dummy-key-for-tests uv run pytest -q` → 712 passed，无回归
- [x] 5.2 我的文件 ruff format + ruff check 全绿（agent_loop 行 657 的 PLC0415 import-outside-top-level 为既有，非本 change 引入）；`uv run mypy src` 不新增错误模式（before/after diff 为空）
- [x] 5.3 既有 skill 注入用例（test_agent_loop_skill_binding）适配为跨 system 消息断言后仍绿，功能等价（memory/skill 仍进提示，仅位置后移）
