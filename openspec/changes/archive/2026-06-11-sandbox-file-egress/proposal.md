## Why

沙箱优先执行让 agent 在容器 `/workspace` 里生成产物（报告、图表、转换后的文件），但**送回用户的闭环是断的、且现存回流机制对容器世界结构性失效**：

1. **旧的"正则嗅探自动回流"在容器模式下命不中**：`im_gateway/normalizer.py` 的 `_extract_generated_image_paths`（154–178）扫本轮 tool 结果里的 `"image generated: <path>"` / `"written N bytes to <path>"`，再用宿主 `Path(p).is_file()`（175）判存在后交 `upload_func` 上传。但 `run_code` / `write_file` 在**容器内**写文件，工具结果里回的是**容器内路径**（如 `/workspace/out.png`）——宿主 `Path.is_file()` 必然命不中（容器路径在宿主不存在），路径被静默跳过。结果：沙箱产物**永远发不回去，且用户毫无感知**（静默漏发）。这是把执行搬进容器后必然出现的回归。
2. **agent 没有"主动送文件给当前用户"的安全工具**：现有 `send_im_message`（`tools/builtin_tools.py:584`，risk=medium）只发文本、且收件人 `target` 由模型任意指定（故保持 gated）。没有一个工具能把 workspace 产物作为附件发回**当前对话的发起人**。
3. **Telegram 完全没有出站文件能力**：出站文件上传只有 Slack 一条路径（`slack.py:_make_upload_func` → `files_upload_v2`，255–277）；`outbound.py` 的出站原语（`send_to` → `_telegram_send`，145）只发 `send_message` 文本，Telegram 侧连 `sendDocument` 都没有。

本 change 把"沙箱产物 → 送回用户"补成闭环：新增**宿主侧** `send_file` 工具（收件人由 harness 从 `session_context` 固定、模型不可指定），废弃结构性失效的正则嗅探回流并把"静默漏发"显式化为"外发失败"提示，补齐 Telegram `sendDocument` 出站。

## What Changes

- **新增宿主侧工具 `send_file(path)`**：`path` 为 **workspace 相对路径**（沙箱优先执行的单根 `/workspace` 坐标系，依赖 `sandbox-execution-world`）；经 `SandboxManager.workspace_host_path()` + `resolve_host_path()` 翻译为宿主真实文件并读字节，再经 `outbound.send_to`/出站文件原语发出。**收件人由 harness 从 `tool_context.session_context` 固定**（platform + sender_id），**不接受任何模型参数指定收件人**——这是它区别于 `send_im_message`（收件人任意 = 保持 medium gated）的核心。
- **`send_file` 免审批当且仅当三条同时成立**：`workspace_scope == session` ∧ 当前会话为 `dm` ∧ `session_context` 非空。三条任一不成立则 **fail-closed**：工具不发文件，返回显式说明文本，引导回 medium 审批路径（`send_im_message`）。`scheduled task` / `sub_agent` / `invoke_agent` 等 `session_context = None` 的运行路径一律 fail-closed。工具结果回显**实际收件人**（platform:sender_id），不回显模型臆测的目标。
- **废弃正则嗅探自动回流**：移除 `normalizer.route()` 末尾（615–620）基于 `_extract_generated_image_paths` + 宿主 `Path.is_file()` 的自动上传。过渡期内：保留 `upload_func` 注入通道（供新出站文件原语复用），但把"扫到容器路径却命不中 → 静默跳过"改为，对**确实在本轮生成、却因结构性失效无法宿主命中**的产物，给用户一条显式"外发失败：请用 send_file 发送"提示，杜绝静默漏发。
- **补齐 Telegram 出站文件**：在 `outbound` 出站原语新增 `send_file_to`（或等价出站文件能力），Telegram 经 `bot.send_document(chat_id=..., document=...)` 出站；Slack 复用既有 `files_upload_v2`。`send_file` 工具经统一出站文件原语按平台分派，单平台失败返回显式失败文本、绝不抛。
- **本 change 明确不做**：不改 `resolve_action_mode` 契约、不改 registry 的 risk 常量、不新增 action gate 的动态 risk 缝（`send_file` 的条件免审批由**收件人 harness 固定 + 工具体内 fail-closed 前置条件**实现，不经 gate）；不碰 `builtin-shell-tool`、`image-generation-tool`、`vision-as-tool`、`skill-yaml-frontmatter`、`action-gate`/`approval-minimization` spec（属其他 change 所有权）；不改 inbound 文件接收（`im-file-attachment` 不动）。

## Capabilities

### New Capabilities
- `sandbox-file-send`: 宿主侧 `send_file(path)` 工具契约——workspace 相对路径经宿主翻译读真实文件后发出；收件人由 harness 从 `session_context` 固定、模型不可指定；免审批当且仅当 `workspace_scope==session ∧ dm ∧ session_context 非空`，否则 fail-closed 回审批路径；`session_context=None` 路径（scheduled/sub_agent/invoke_agent）一律 fail-closed；结果回显实际收件人；无连接器/不可达/发送失败各返回说明文本，绝不抛。

### Modified Capabilities
- `im-generated-image-upload`: 废弃基于正则嗅探 + 宿主 `Path.is_file()` 的自动回流（对容器内写文件结构性失效），把"静默漏发"改为显式"外发失败"提示；同时把出站文件能力从"仅 Slack `files_upload_v2`"扩展为统一出站文件原语，新增 Telegram `send_document` 出站路径。

## Impact

- **代码**：
  - `tools/builtin_tools.py`：新增 `send_file` 工具（risk=`none` → action gate 直跑，因收件人 harness 固定无可 gate 的不可信目标；fail-closed 与免审批前置条件在工具体内）。复用 `_get_manager()` / `workspace_host_path()`（`builtin_tools` 已 import）+ `file_sandbox_io.resolve_host_path`。
  - `outbound.py`：新增出站文件原语（`send_file_to`），Slack 经 `files_upload_v2`、Telegram 经 `send_document`。
  - `im_gateway/normalizer.py`：移除/改造 `route()` 末尾的正则嗅探自动上传（615–620），把静默漏发改为显式外发失败提示；`_extract_generated_image_paths` / `_IMAGE_GENERATED_RE` / `_FILE_WRITTEN_RE` 退役或降级为仅过渡提示用途。
  - `im_gateway/telegram.py`：补 Telegram 侧出站文件投递（`bot.send_document`）。
  - `im_gateway/slack.py`：`_make_upload_func` 收敛到统一出站文件原语之上（行为不变）。
- **复用而非新建**：收件人固定复用 `ToolContext.session_context`（im-message-context 已落）；连接器复用 `ToolContext.outbound_connectors`（builtin-outbound-tool 已落）；workspace 相对路径翻译复用 `workspace_host_path` + `resolve_host_path`（sandbox-workspace-mount / file-tools-sandbox-execution 已落）；出站分派复用 `outbound.send_to` 的平台分派范式。
- **模块边界声明**：
  - owning package：`tools`（`send_file` 工具）、`outbound`（顶层基础设施，出站文件原语）、`im_gateway`（normalizer 回流退役 + telegram 出站文件投递）。
  - public API surface：新增 `outbound.send_file_to(platform, connector, target, path, ...)`（供 `tools.send_file` 与 IM 边调用）；`send_file` 经 `@tool` 注册进 registry，对 LLM 暴露 `path` 单参数（`tool_context` 为 out-of-band 注入，不进 schema）。
  - owned tables：无（仅文件系统读 + 出站投递，不落 DB）。
  - config namespace：无新增（复用现有 connector 配置与 `sandbox.*` workspace 路径）。
  - cross-module dependencies：`tools.send_file` → `outbound`（public API）、`integrations.sandbox` 的 `SandboxManager`/`workspace_host_path`（public API）、`tools.file_sandbox_io.resolve_host_path`（同包）；`im_gateway` → `outbound`（public API）。`outbound` 是顶层基础设施，**不 import `fleetent.platform.*`**；全部涉及模块（`tools`/`outbound`/`im_gateway`）MUST NOT `import fleetent.platform.*`，保持 agent/platform 单向解耦；agent 须仍能在无 platform、platform 表不存在环境下 `fleetent agent run`（`send_file` 在无 IM 连接器的 CLI/HTTP 路径下返回说明文本，不报错）。
  - migration / shim plan：无模块迁移；`outbound.py` 已是 `fleetent.outbound` 的 re-export shim，新原语加在 `fleetent.outbound` 真实模块、由 shim re-export；`normalizer` 内退役的 `_extract_generated_image_paths` 为 internal 实现，无 re-export 兼容负担。
- **测试**：unit（`send_file` 路径翻译：相对路径 → 宿主真实文件、`..` 逃逸被拒；免审批前置三条任一不成立 → fail-closed 不发；`session_context=None` → fail-closed；收件人取 session_context 而非模型参数；无连接器/不可达/发送失败各返回说明文本不抛——均 mock 连接器与 manager，不碰真实 DB）；integration（Slack/Telegram 出站文件原语经 mock 连接器投递；normalizer 不再静默漏发、改出显式外发失败；scheduled/sub_agent 路径 fail-closed）。
- **依赖**：`sandbox-execution-world`（`send_file` 依赖单根 `/workspace` 相对路径世界与容器/降级同坐标系解析）、`sandbox-isolation-foundation`（workspace key 无碰撞派生 + 运行时封闭性门控）。基于已合并 main 的 `builtin-outbound-tool`、`im-message-context`、`im-generated-image-upload`、`sandbox-workspace-mount`、`file-tools-sandbox-execution`、`per-agent-telegram-connector`。
