## 1. 依赖与脚手架

- [x] 1.1 在 `pyproject.toml` 新增依赖 `prompt_toolkit>=3.0.50`、`rich>=14.0`、`websockets>=12.0`(WS 客户端);新增 script `fleetent-tui = "fleetent.tui.app:main"`;`uv sync` 后确认可解析
- [x] 1.2 创建 `src/fleetent/tui/` 包骨架(`__init__.py` 及空模块占位:`protocol.py` / `transport.py` / `dispatch.py` / `backend.py` / `render.py` / `commands.py` / `app.py`),`uv run mypy src/fleetent/tui` 通过(空骨架)

## 2. 协议编解码(protocol.py)

- [x] 2.1 Write failing tests for JSON-RPC 协议:`tests/test_tui_protocol.py` —— 请求/响应/通知的编解码、`event` 通知构造(gateway.ready/text_delta/tool_call/tool_result/done/error/approval_required)、parse error(-32700)构造、newline-framed 序列化
- [x] 2.2 Implement `protocol.py`(方法/事件常量、`encode_frame`/`decode_frame`、`make_event`/`make_response`/`make_error`)使测试转绿

## 3. Transport 抽象与 WSTransport(transport.py)

- [x] 3.1 Write failing tests for Transport:`tests/test_tui_transport.py` —— `WSTransport.write` 用 fake ws 成功路径返回 True;客户端断开(WebSocketDisconnect/closed)返回 False;真实非断开错误被 re-raise(不伪装断开);`close()` 幂等
- [x] 3.2 Implement `transport.py`(`Transport` Protocol、`WSTransport`、peer-gone 分类)使测试转绿

## 4. dispatch 与网关方法(dispatch.py)

- [x] 4.1 Write failing tests for dispatch:`tests/test_tui_dispatch.py` —— `send` 触发(mock 的)`run_stream` 并把事件序列映射为 event 通知且保序;`session.new`/`session.list`(mock session_mgr)返回正确结构且仅本 user;未知方法回 -32601;`send` 响应含 run_id
- [x] 4.2 Implement `dispatch.py` 的 `send` + `session.*`(消费 `run_stream`,经 transport 推 event;接 `session_mgr`)使测试转绿
- [x] 4.3 Write failing tests for abort:`tests/test_tui_dispatch_abort.py` —— `abort{run_id}` 取消对应 CancelToken;中断后推收口通知;未知 run_id 返回 `{aborted:false}` 不崩
- [x] 4.4 Implement abort(连接级 `{run_id: CancelToken}` 表,接 `cancellation`)使测试转绿
- [x] 4.5 Write failing tests for approve:`tests/unit/test_tui_dispatch_approve.py` —— `approve{approval_id, decision}` 转 `permission_gate.resolve`(approved/rejected 两路、返回 `{ok}`);非法 decision 回 `-32602`;复用既有 gate 不改行为。(v1:`approval_required` 推送已 descope——`run_stream` 不门控,见 spec 范围说明;流式门控+推送留给 follow-on `streaming-approval-gating`)
- [x] 4.6 Implement approve(接 `permission_gate.resolve`)使测试转绿

## 5. WS 端点与认证(server.py)

- [x] 5.1 Write failing tests for WS 端点:`tests/test_tui_ws_endpoint.py`(starlette TestClient.websocket_connect)—— 连接即收 `gateway.ready`;有效 `ma-` key 通过、无效/缺失 key 关闭连接;非法 JSON 帧回 -32700 不断连;断开触发清理(在途 run 取消、session 解绑)
- [x] 5.2 Implement `@app.websocket("/ws")`(认证复用 user_store、绑定 user/连接状态、accept 后发 ready、receive 循环 → dispatch、finally 清理),确认 `/chat` SSE 不受影响,使测试转绿

## 6. 客户端后端连接(backend.py)

- [x] 6.1 Write failing tests for client backend:`tests/test_tui_backend.py` —— `GatewayBackend` 用 mock websockets 连接:`send`/`abort`/`approve`/`session.*` 发出正确 JSON-RPC 帧;`on_event` 回调收到解析后的 event;连接失败/超时报错;断连触发退避重连钩子
- [x] 6.2 Implement `backend.py`(`TuiBackend` 抽象 + `GatewayBackend`:websockets 连接、收发协程、on_event 分发、重连/超时),`--url`/`--token` 解析,使测试转绿

## 7. 渲染层(render.py)

- [x] 7.1 Write failing tests for render:`tests/test_tui_render.py`(`rich.Console(file=StringIO)` 捕获)—— `text_delta` 增量文本、`tool_call`/`tool_result` 面板(结果截断)、`error` 展示、`approval_required` 审批提示、spinner/状态行
- [x] 7.2 Implement `render.py`(rich 渲染函数,纯 IO 隔离、Console 可注入)使测试转绿

## 8. 斜杠命令与主程序(commands.py / app.py)

- [x] 8.1 Write failing tests for commands:`tests/test_tui_commands.py` —— 解析 `/new /session /abort /approve /quit /help`(及参数);未知命令处理;补全候选列表(Completer)
- [x] 8.2 Implement `commands.py`(解析 + prompt_toolkit `Completer`)使测试转绿
- [x] 8.3 Write failing tests for app 主循环:`tests/test_tui_app.py`(prompt_toolkit `create_pipe_input` 注入按键)—— 输入提交触发 backend.send;`/abort` 触发 backend.abort;Ctrl-C 触发 abort;event 到达驱动 render;`patch_stdout` 下输入行与输出共存
- [x] 8.4 Implement `app.py`(`PromptSession.prompt_async` + 接收协程并发、patch_stdout、命令分发、`main()` 入口)使测试转绿

## 9. 收尾

- [x] 9.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 通过;`uv run ruff format && uv run ruff check` 仅校验本 change 文件;`uv run mypy src/fleetent/tui` 通过
- [x] 9.2 更新 `.env.example`/`README.md`/`CLAUDE.md`(架构图新增 `tui/` 模块说明、`fleetent-tui` 命令);在 PR 中说明新增依赖必要性与自托管性
