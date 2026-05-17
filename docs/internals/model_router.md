# model_router.py

## 这个模块干什么

做模型路由：根据任务类型返回对应的 OpenAI 客户端和路由配置（base_url、model、max_tokens 等）。

模块本身不调用任何 LLM，不维护状态，不知道 agent、tools 和 memory 的存在。

## task_type 是谁传的、为什么

调用方（agent_loop.py、memory_layer.py 等）在调用时硬编码传入。

调用方在写代码时就知道自己在做什么操作，所以直接传字符串（"default"、"memory_extraction"）。这是设计时决策，不是运行时推断。

好处：确定性强，零开销，路由配置集中、使用分散。

## 换 provider 要改哪里

只需修改 ROUTES 字典里对应条目的值（base_url、model、api_key_env），其余代码不动：

```python
"default": RouteConfig(
    base_url="https://api.openai.com/v1/",
    model="gpt-4o",
    api_key_env="OPENAI_API_KEY",
    max_tokens=4096,
),
```

如果需要同一任务类型支持多个 provider（如按负载切换），可以把 ROUTES 按 provider 分组，`get_client_and_config` 额外接收 `provider` 参数——但当前版本不需要。
