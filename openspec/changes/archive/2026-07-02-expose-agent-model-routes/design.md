## Context

Agent 配置页用 `ROUTE_BINDINGS`（`configure.tsx:120`）声明式地渲染每个模型路由的选择器。
每个 binding 有三字段：`labelKey`（i18n 标签）、`protocols`（候选模型按 `model.protocol` 过滤的白名单）、
`routeKey`（写入 `model_overrides.routes[routeKey]` 的键）。保存时 `onSave`（`configure.tsx:280`）
用 `withRouteModel` 把每个 binding 的选择折叠进 `model_overrides`，再 `PATCH` 给后端。回读时
`routeModelId` 从 `model_overrides.routes[routeKey][0]` 取回已选模型 id。

后端 `STANDARD_ROUTE_KEYS`（`model/resolver.py:10`）定义 9 个标准路由；`materialize._models_from_overrides`
（`materialize.py:263`）对任意路由键逐一合并进 baseline，并从 model 记录 `protocol` 分派协议
（`_target_from_model_override`，`materialize.py:329`）。所以后端已能接收任意路由键——差距只在 UI 未暴露。

各路由与其运行时协议对应关系（据 `agent.example.yaml` 与 resolver）：

| route_key | 运行时协议 | UI 候选过滤 `protocols` |
|---|---|---|
| default | openai_chat | `openai_chat`（已存在） |
| embedding | http_embedding | `http_embedding`（已存在） |
| memory_extraction | openai_chat | `openai_chat`（已存在） |
| image_generation | openai_image_generation / openai_image_chat | 已存在 |
| **vision** | openai_chat（多模态输入） | `openai_chat` |
| **kb_extraction** | openai_chat（抽取） | `openai_chat` |
| **rerank** | http_rerank | `http_rerank` |
| **audio_transcription** | 保留（暂无 protocol） | 见 D2 |
| **audio_generation** | 保留（暂无 protocol） | 见 D2 |

## Goals / Non-Goals

**Goals**
- UI 覆盖全部 9 个 `STANDARD_ROUTE_KEYS`，运维无需手写 YAML 即可为每个路由选模型。
- 新增路由的选择、保存、回读端到端 round-trip，与现有 4 个路由完全同构。
- 保留路由（audio）在无候选模型时给出明确、不误导的空态。

**Non-Goals**
- 不新增后端 API 字段或 schema 迁移（`model_overrides` 已是 free-form passthrough）。
- 不实现音频 provider protocol / adapter（audio 路由仅占位可选）。
- 不改动 `withRouteModel` / `routeModelId` 帮助函数的既有语义（新路由复用）。
- 不改 `default` 路由的特殊呈现（provider hint、`selectProvider` 文案）。

## Decisions

### D0 — 模型路由独立成 Models tab

把全部 9 个路由选择器 + provider key override 从 overview tab 迁到独立的 `ModelsTab`
（overview 只留 name/system_prompt/allowed_tools/memory_namespace/YAML 导出）。两个 tab 各自
持有独立的表单 state 与 save：overview 的 save 只 PATCH 前四项，`ModelsTab` 的 save 只 PATCH
`model_overrides` 并处理 provider key secret。两者共用同一 `useAgentDetailQuery`（react-query 按
key 去重，不重复请求）。

理由：9 个选择器塞进 overview 会淹没 prompt/tools 这些高频基础字段；拆开后各 tab 职责单一、
save 语义清晰（改模型不再顺带回写 prompt，反之亦然）。PATCH `exclude_unset` 语义保证各自只写自己
的字段、互不覆盖。

### D1 — 声明式扩展 `ROUTE_BINDINGS`，复用既有渲染循环

在 `ROUTE_BINDINGS` 数组追加 5 个条目（vision / kb_extraction / rerank / audio_transcription /
audio_generation）。渲染循环（`configure.tsx:340`）、保存折叠（`onSave`）、回读（`useEffect` 里
`ROUTE_BINDINGS.map`）都已按数组驱动，无需改控制流——只加数据 + i18n 键。

理由：最小改动面、与现有 4 路由行为严格同构，回归风险集中在「数组多了几项」而非逻辑分支。

### D2 — 音频保留路由：显式空态而非隐藏

音频两路由当前无 provider protocol（`model_admin_store` 里不会有 `audio_*` protocol 的模型），
候选 `protocols` 过滤后必为空。方案：为 audio binding 设一个「未来协议」占位过滤集
（如 `['openai_audio_transcription']` / `['openai_audio_generation']`，命名与现有 `openai_*` 风格一致），
候选为空时 `SimpleSelect` 呈现禁用/空态，并在该路由下渲染一行 hint：「暂无支持该协议的模型，
请先在模型管理中注册」。

理由：用户明确要求暴露全部 5 个路由。显式空态比「隐藏到有支持才出现」更符合 authoring 入口的可发现性，
且不会写出无效 `model_overrides`（空选择不落库）。备选（仅暴露 3 个有协议的路由）已被用户否决。

### D3 — 后端只验证不改契约

不改 `UpdateBody` / `CreateBody` 的 `model_overrides: dict[str, Any]`。新增 integration 测试：
构造带 `models.routes.rerank` / `.vision` / `.kb_extraction` 的 `model_overrides`，经
`PATCH /admin/agents/{name}` 存入，再 `GET` 回读断言 round-trip；并断言 materialize 后的
`agent.yaml` 的 `models.routes` 含这些键、目标 protocol 正确解析。

理由：用户选择「Frontend + verify backend」。测试锁住「新路由键端到端可用」这一行为，
防止后续有人给 `model_overrides` 加白名单校验时静默破坏这些路由。

### D4 — i18n 键命名沿用 `agents.model<Route>` 风格

新增键：`agents.modelVision` / `agents.modelKbExtraction` / `agents.modelRerank` /
`agents.modelAudioTranscription` / `agents.modelAudioGeneration`，以及音频空态 hint 键
`agents.modelAudioUnsupportedHint`（或复用一个通用「无候选」提示键）。中英双语同步补齐
（`messages.ts` 英文段 ~L133、中文段 ~L830）。

## Risks / Trade-offs

- **音频空选择器观感**：无候选时选择器为空态，可能被误读为「坏了」。→ 用 D2 的 hint 文案缓解。
- **vision/kb_extraction 与 default 共用 `openai_chat` 候选**：候选列表相同，用户可能选到同一模型。
  这是预期行为（同一 chat 模型可服务多路由），非缺陷。
- **前端测试覆盖**：需确认 `configure.tsx` 有对应测试宿主（RTL）；若无则新增最小渲染断言，
  用 `pnpm`（非 `npx`）跑 vitest。

## Open Questions

- 音频占位协议名（`openai_audio_transcription` / `openai_audio_generation`）是否需与后端未来
  实现预先对齐命名？当前仅作 UI 过滤字符串，后端不消费，故可后续统一——若已有倾向命名请在 apply 前确认。
