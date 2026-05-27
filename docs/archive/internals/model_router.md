# model_router.py

## 这个模块干什么

做模型路由：根据任务类型返回对应的客户端和路由配置（base_url、model、max_tokens 等）。

模块本身不调用任何 LLM，不维护状态，不知道 agent、tools 和 memory 的存在。

## 两个工厂函数

| 函数 | 客户端类型 | 使用场景 |
|------|-----------|---------|
| `get_client_and_config` | `OpenAI`（同步） | `context_mgr._summarize()`、`memory_layer.extract_and_save()` |
| `get_async_client_and_config` | `AsyncOpenAI` | `agent_loop.run()`、`agent_loop.run_stream()` |

每次调用都创建一个新客户端——客户端是无状态的，创建开销极低，不需要全局单例。

## task_type 是谁传的、为什么

调用方（`agent_loop.py`、`memory_layer.py` 等）在调用时硬编码传入。调用方在写代码时就知道自己在做什么操作，所以直接传字符串（`"default"`、`"memory_extraction"`）。这是设计时决策，不是运行时推断。

好处：确定性强，零开销，路由配置集中、使用分散。

## 换 provider 要改哪里

只需修改 `ROUTES` 字典里对应条目（base_url、model、api_key_env），其余代码不动：

```python
"default": RouteConfig(
    base_url="https://api.openai.com/v1/",
    model="gpt-4o-mini",
    api_key_env="OPENAI_API_KEY",
    max_tokens=4096,
),
```

## get_async_client_and_config 缺 key 时不 raise

同步版本 `get_client_and_config` 在 key 缺失时抛 `RuntimeError`；异步版本用空字符串 fallback（`os.environ.get(cfg.api_key_env, "")`），错误会在首次 LLM 调用时由 SDK 抛出。这是行为不一致，未来可统一。
