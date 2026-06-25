## Context

`frontend/src/features/chat/api.ts` 的 `useAgentChat` 在 `POST /admin/agents/{name}/chat` 返回非 2xx 时,调 `toIngressError(agentName, status)`——一个**只看状态码**的纯函数:404→"not found",503→"no active placement",其余→generic。

后端 ingress(`platform/node_management/agent_transport.py`、`agent_management_console/agent_console_api.py`)用 FastAPI `HTTPException(status_code, detail=...)`,响应体形如 `{"detail": "node 'local-node' service key unavailable"}`。503 的 detail 至少有三类:service key 解不出、上游流式异常(`str(exc)`)、真正无 placement。前端丢弃 detail、把所有 503 归因 placement,造成误导。

## Goals / Non-Goals

**Goals:**
- 前端透出后端 ingress 的真实错误 detail,使 operator 看到的原因与后端一致
- 404 维持清晰语义(detail 通常即 `agent not found`)
- 无 detail / body 解析失败时,回落到中性、不误导的提示(按状态码给通用 "unavailable"/"failed")
- 同步 `agent-chat-console` spec,去掉"503 必为 placement"的措辞

**Non-Goals:**
- 不改后端(已返回正确 `{detail}`)
- 不改 SSE 事件流处理(`text_delta`/`done`/`error` 不变)——本 change 只管**非 2xx HTTP 响应**的错误呈现
- 不做错误文案 i18n / 美化,仅透出 detail

## Decisions

### D1:基于响应体 detail 呈现,而非状态码硬编码

**决定**:错误分支改为读取响应体并提取 `detail`:
- 解析 `await response.json()`,取 `detail`(string)。
- 有 detail → 直接呈现该 detail(可加 agent 名前缀,如 `Agent "X": <detail>`)。
- 无 detail / 非 JSON / 解析失败 → 按状态码回落到中性文案:404→`Agent "X" was not found.`;503→`Agent "X" is currently unavailable.`(去掉 placement 断言);其他→`Agent "X" request failed with status <N>.`。

`toIngressError` 由 `(agentName, status)` 改为接收已解析的 detail(或 `(agentName, status, detail)`),调用点先读 body 再调。注意:响应体在错误分支只能消费一次,且当前错误分支未读 body——安全。

**备选**:保留纯状态码映射、只把 503 文案改中性。弃用:仍丢弃后端已提供的精确原因,排查体验差,未根治"误导"问题。

### D2:body 读取的健壮性

ingress 错误响应体预期是 JSON `{detail}`,但需容错(空体、text/plain、网络截断)。用 try/catch 包 `response.json()`,失败即走状态码回落。不得因解析失败而抛未捕获异常、让 UI 卡在 streaming 态。

## Risks / Trade-offs

- **detail 可能含内部术语**(如 `node 'local-node' service key unavailable`)→ 对 operator/dev 控制台可接受(本就是调试面),比误导文案强;若未来要面向终端用户再做语义映射层。

- **测试 mock 形状**:现有 `api.test.tsx` 的 503 用例 mock body 用 `{error: 'no placement'}`(非 `detail`)并断言旧文案。需改为 `{detail: ...}` 对齐 FastAPI 真实形状,并断言透出 detail——否则测试与后端契约脱节(假绿)。

## Migration Plan

1. 改 `api.ts`:错误分支读 body→提取 detail→`toIngressError` 基于 detail 呈现 + 状态码回落
2. 更新 `api.test.tsx`:404/503 用例改 `{detail}` body、断言透出 detail;补一个 503 无 detail 回落到中性文案的用例
3. 跑 `make test-frontend`(vitest + tsc + eslint)绿
4. 同步 `agent-chat-console` spec

无后端、DB、配置改动。
