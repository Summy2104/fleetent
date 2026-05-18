# API Layer Design

## 端点

| 端点 | 鉴权 | 说明 |
|------|------|------|
| `POST /chat` | Bearer token | 核心接口，SSE 流式响应 |
| `GET /health` | 无 | 服务存活检查 |

用户管理不走 HTTP，走 CLI 命令（见下文）。

## 鉴权

```
Authorization: Bearer ma-xxxx
  → user_store.get_by_api_key("ma-xxxx")
  → user_id（注入后续调用）
  → 找不到 → 401
```

## 流式响应（SSE）

`POST /chat` 返回 `text/event-stream`，逐事件推送：

```
data: {"type": "tool_call", "name": "get_current_time", "args": {}}

data: {"type": "tool_result", "name": "get_current_time", "content": "2026-05-18 ..."}

data: {"type": "text_delta", "content": "现在是 "}

data: {"type": "text_delta", "content": "2026 年..."}

data: {"type": "done", "content": "现在是 2026 年..."}
```

客户端可以实时渲染 `text_delta`，`done` 携带完整回复方便非流式客户端直接取值。

## agent_loop 改造

现有 `run()` 是同步函数，返回完整回复。需要新增异步流式版本：

```python
# 现有（保留，CLI 继续用）
def run(user_input: str, user_id: str) -> str: ...

# 新增（API 层用）
async def run_stream(user_input: str, user_id: str) -> AsyncIterator[dict]: ...
```

`run_stream` 在每次 tool_call、tool_result、text_delta 时 `yield` 事件，不等循环结束再返回。

## 框架

FastAPI：async-native，SSE 用 `StreamingResponse`，无需额外依赖。

```python
@app.post("/chat")
async def chat(req: ChatRequest, user_id: str = Depends(require_auth)):
    return StreamingResponse(
        _stream(req.message, user_id),
        media_type="text/event-stream",
    )

async def _stream(user_input: str, user_id: str):
    async for event in run_stream(user_input, user_id=user_id):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
```

## 用户管理 CLI

不暴露 HTTP 端点，管理员在服务器上执行：

```bash
uv run mini-agent-admin create-user --name "Randy"
# User created. API key (shown once): ma-a3f9c2...

uv run mini-agent-admin list-users
uv run mini-agent-admin rotate-key --user-id <id>
```

API key 创建时打印一次，之后不再显示。丢失则 rotate。

## 模块文件

```
src/mini_agent/
  server.py        ← FastAPI app，端点定义，鉴权 Depends
  admin.py         ← CLI 用户管理命令
```

`server.py` 只负责 HTTP 层：解析请求、鉴权、流式响应。业务逻辑在 agent_loop，不下沉到 server.py。
