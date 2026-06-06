## 1. Sprint 1 — 基础设施

- [x] 1.1 Write failing tests for schema_builder: list[T], Optional[T], Literal, Annotated types, out-of-band param filtering
- [x] 1.2 Implement `src/fleetent/tools/schema_builder.py` with full type system support (typing.get_origin/get_args recursion)
- [x] 1.3 Write failing tests for @tool availability: unavailable tool excluded from get_schemas(), exception in availability treated as unavailable, _registry unaffected
- [x] 1.4 Add `availability: Callable[[], bool] | None` param to `@tool` decorator and update `get_schemas()` filter in `registry.py`
- [x] 1.5 Write failing tests for result_truncation spillover: file created on overflow, preview=100 lines, path+hint in result, 7-day cleanup registration, self_truncates skip
- [x] 1.6 Upgrade `result_truncation.py`: raise threshold to 50KB, write spillover file to `data_dir()/tool_spillover/`, return 100-line preview + path + read hint
- [x] 1.7 Register daily spillover cleanup task in `cron_scheduler.py` startup
- [x] 1.8 Run `uv run pytest -x -q` — all tests green; run `uv run python scripts/check_test_layers.py`

## 2. Sprint 2 — 文件操作工具链

- [x] 2.1 Write failing tests for read_file: offset/limit pagination, directory listing, binary detection (magic bytes + non-printable ratio), paging hint when truncated
- [x] 2.2 Implement upgraded `read_file` in `src/fleetent/tools/file_tools.py` (offset/limit, dir tree, binary detection)
- [x] 2.3 Write failing tests for edit_file: ExactReplacer, LineTrimmedReplacer, WhitespaceNormalizedReplacer, LineEndingNormalizedReplacer, IndentationFlexibleReplacer, ContextAwareReplacer, no-op guard, replace_all, all-layers-fail diagnostic
- [x] 2.4 Implement `edit_file` with 6-layer fallback matcher in `src/fleetent/tools/file_tools.py`
- [x] 2.5 Write failing tests for search_content: ripgrep backend, Python re fallback, include filter, max_results truncation, format `file:line:content`
- [x] 2.6 Implement `search_content` (grep) in `src/fleetent/tools/file_tools.py`
- [x] 2.7 Write failing tests for search_files: glob pattern, mtime sort, max_results truncation, ripgrep backend + pathlib fallback
- [x] 2.8 Implement `search_files` (glob) in `src/fleetent/tools/file_tools.py`
- [x] 2.9 Register all file tools via `tools/__init__.py` import; move `read_file`/`write_file` to `file_tools.py` with re-export shim in `builtin_tools.py`
- [x] 2.10 Run `uv run pytest -x -q` — all tests green; run `uv run python scripts/check_test_layers.py`

## 3. Sprint 3 — 执行与网络工具

- [x] 3.1 Write failing tests for bash_exec: description required, permission_gate risk_level=high, stdout+stderr+exit_code output, timeout (SIGTERM→SIGKILL), cancel_token, workdir, spillover for large output
- [x] 3.2 Implement `bash_exec` in `src/fleetent/tools/shell_tool.py`
- [x] 3.3 Register `bash_exec` via `tools/__init__.py`
- [x] 3.4 Write failing tests for web_fetch: markdown/text/html format, 5MB size limit, timeout, binary content-type error, HTML→Markdown conversion
- [x] 3.5 Add `html2text` dependency to `pyproject.toml`
- [x] 3.6 Implement `web_fetch` in `src/fleetent/tools/web_tools.py`
- [x] 3.7 Write failing tests for web_search: SearXNG JSON API call, num_results param, availability gate (SEARXNG_URL unset → not in schema), SearXNG error handling
- [x] 3.8 Implement `web_search` in `src/fleetent/tools/web_tools.py` with `availability=lambda: bool(os.getenv("SEARXNG_URL"))`
- [x] 3.9 Register web tools via `tools/__init__.py`
- [x] 3.10 Run `uv run pytest -x -q` — all tests green; run `uv run python scripts/check_test_layers.py`

## 4. Sprint 4 — 交互工具

- [x] 4.1 Write failing tests for user_input_gate: session-scoped Event, answer() sets event, await with timeout, isolation from permission_gate, cleanup on session end
- [x] 4.2 Implement `src/fleetent/governance/user_input_gate.py` (asyncio.Event + answer store, session lifecycle)
- [x] 4.3 Write failing tests for clarify tool: blocks until answer, timeout returns timeout string, open-ended and choices modes, tool_context session_id used for gate lookup
- [x] 4.4 Implement `clarify` in `src/fleetent/tools/interaction_tools.py` using `user_input_gate`
- [x] 4.5 Write failing tests for Slack clarify rendering: choices → Block Kit Actions buttons, button click → user_input_gate.answer()
- [x] 4.6 Implement clarify rendering in `im_gateway/clarify_renderer.py`: Slack Block Kit buttons with session_id in value
- [x] 4.7 Write failing tests for Telegram clarify rendering: choices → InlineKeyboardMarkup, callback → user_input_gate.answer()
- [x] 4.8 Implement clarify rendering in `im_gateway/clarify_renderer.py`: InlineKeyboardMarkup with callback_data JSON
- [x] 4.9 Implement fallback text rendering in `im_gateway/clarify_renderer.py` for non-IM sessions (numbered list)
- [x] 4.10 Write failing tests for todo: set/get/clear actions, session isolation, session-end cleanup, list[str] schema
- [x] 4.11 Implement `todo` in `src/fleetent/tools/interaction_tools.py` (in-memory session dict)
- [x] 4.12 Register interaction tools via `tools/__init__.py`
- [x] 4.13 Run `uv run pytest -x -q` — all tests green; run `uv run python scripts/check_test_layers.py`
