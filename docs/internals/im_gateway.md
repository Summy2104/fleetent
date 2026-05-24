# im_gateway/

## 架构

```
Slack Socket Mode ──┐
Telegram polling ───┤──→ NormalizedMessage ──→ route() ──→ agent_loop.run()
（未来：WhatsApp）  ┘        normalizer.py              session_mgr + reply_func
```

每个平台适配器把平台原生事件转换为 `NormalizedMessage`，然后调 `route()`。`route()` 是统一入口，不知道消息来自哪个平台。

## NormalizedMessage

```python
@dataclass
class NormalizedMessage:
    platform: str           # "slack" | "telegram"
    session_id: str         # 用于加载/保存会话历史
    user_id: str            # 内部 user UUID（经 im_user_store 映射）
    text: str
    attachments: list
    reply_func: Callable    # 异步函数，接收文本并回复到原平台
```

`reply_func` 是闭包，封装了平台回复 API 的调用细节，`route()` 只需 `await msg.reply_func(text)` 而无需感知平台。

## route() 流程

```python
async def route(msg: NormalizedMessage) -> None:
    history = await session_mgr.load(msg.session_id)
    history.append({"role": "user", "content": msg.text})
    reply = await agent_loop.run(history, user_id=msg.user_id)
    history.append({"role": "assistant", "content": reply})
    await session_mgr.save(msg.session_id, history)
    await msg.reply_func(reply)
```

## session_id 推导规则

### Slack（`slack.py`）

| 场景 | session_id |
|------|-----------|
| DM（`channel_type == "im"`） | `user:{slack_user_id}` |
| 频道消息带 thread_ts | `thread:{thread_ts}` |
| 频道消息不带 thread_ts | `user:{slack_user_id}`（fallback，bot 会在 thread 里回复） |

### Telegram（`telegram.py`）

| 场景 | session_id |
|------|-----------|
| 私聊（`chat_type == "private"`） | `user:{tg_user_id}` |
| 群组回复某条消息 | `thread:{reply_to.message_id}` |
| 群组非回复消息 | `user:{tg_user_id}` |

## im_user_store：平台 ID → 内部 User

Slack/Telegram 的 user ID 是平台本地 ID（`U123`、`12345`），需要映射到内部 UUID：

```python
user = get_or_create("slack", slack_user_id)
# 首次见到：在 im_users 表插入一行，关联到 users 表
# 再次见到：直接返回已有 User
```

这样内部系统（记忆、traces、session）始终用统一的 UUID，平台 ID 只在适配器层出现。

## 适配器启动

适配器在 FastAPI lifespan 里以后台任务启动：

```python
if os.environ.get("SLACK_BOT_TOKEN") and os.environ.get("SLACK_APP_TOKEN"):
    asyncio.create_task(_start_slack_adapter())
```

启动失败时 `logger.warning` 并继续，不影响 HTTP 服务器正常运行。
