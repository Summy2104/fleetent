## Context

`im-progress-feedback` 已建立 `progress_func` 管线:normalizer 在每次工具调用前 await `progress_func({"type":"tool_call","name":...})`。Slack 适配器订阅该回调。原实现走"占位消息 + chat.update",但 `isinstance(resp, dict)` 判断对 `SlackResponse`(非 dict 子类)恒为 False,占位 ts 取不到,进度反馈从未真正生效。

Slack Agents & Assistants 的 `assistants.threads.setStatus`(slack-sdk 方法名 `assistant_threads_setStatus`)提供原生状态指示器:显示在 bot 名下方、不占消息、设空字符串即清除。

## Goals / Non-Goals

**Goals:**
- Slack 用户在 agent 运行期间看到原生状态(思考中 → 具体工具),完成自动消失
- 工具名展示为可读中文,而非 `google-workspace__manage_drive` 这类内部名
- 未启用该功能的 App 平滑降级,不报错不阻断

**Non-Goals:**
- 不改 `progress_func` 管线本身、Telegram typing、其它适配器
- 不实现 Assistants API 的其它能力(suggested prompts / title)

## Decisions

### D1:用 `assistant_threads_setStatus` 而非占位消息
原生状态指示器形态正确(不占消息位、自动消失),且避开了 `SlackResponse` 非 dict 的坑。`reply_func` 末尾设空状态再 `say()` 发最终回复。

### D2:工具名 → 可读状态用静态映射 + fallback
`_TOOL_STATUS` dict 覆盖常见工具(Google Workspace 各 manage_*、run_code、web_search 等);`_tool_status_text()` 对未命中的:先前缀匹配(自定义 MCP),再 fallback 为去命名空间+下划线转空格的通用文案。

### D3:能力不可用时降级
首次 `setStatus` 失败(App 未开 Agents & Assistants)→ 记 `_status_ok=False`,后续 progress/清除都跳过,reply 仍走 `say()`。失败 log warning 不抛。

## Risks / Trade-offs

- **[Risk] setStatus 失败被静默** → 首次失败 log warning(含 channel),便于诊断"为何没状态";后续更新失败仅 debug。
- **[Risk] 工具名映射不全** → fallback 保证任意工具都有合理文案,新工具加进 `_TOOL_STATUS` 即可,不影响功能。
- **[依赖] 需 App 开启 Agents & Assistants** → 已在 proposal 标注;降级路径保证未开启时仍可用。
