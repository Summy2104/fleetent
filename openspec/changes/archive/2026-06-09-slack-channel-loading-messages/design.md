## Context

`_make_status_funcs` 服务频道 `app_mention` 与非-assistant DM fallback,用 raw `client.assistant_threads_setStatus(...)`。它只设 `status`,未传 `loading_messages`,故 Slack 在频道用其内置默认 loading 轮播。raw Web API 已支持 `loading_messages` 参数。

## Goals / Non-Goals

**Goals:** 频道路径的消息区轮播也展示 fleetent 工具文案,与 assistant 路径对称。

**Non-Goals:** 不改 assistant 路径(已正确);不改底部状态栏逻辑;不引入新 helper(复用 `_loading_messages_for_event`)。

## Decisions

### D1: `_make_status_funcs` 两处 setStatus 增传 loading_messages
初始 `status="🤔 思考中..."` 配 `loading_messages=["🤔 思考中..."]`;progress 配 `loading_messages=_loading_messages_for_event(evt)`。与 `_route_assistant_message` 同一辅助,保证两路径一致。

## Risks / Trade-offs

- [频道里 assistant 状态语义] → 现状 Slack 已在频道渲染该 loading(我们已在调 setStatus),补 loading_messages 只是替换默认占位为我方文案,无新副作用;setStatus 失败仍按既有逻辑降级。
