## Context

沙箱优先执行把 agent 的代码执行与文件写入搬进容器 `/workspace`，"产物送回用户"的闭环随之断裂、且现存回流机制对容器世界结构性失效。三处现状均已核实：

- `im_gateway/normalizer.py:154-178` 的 `_extract_generated_image_paths` 扫本轮 tool 结果里的 `_IMAGE_GENERATED_RE`(`"image generated: <path>"`) / `_FILE_WRITTEN_RE`(`"written N bytes to <path>"`)，再用宿主 `Path(p).is_file()`(175) 判存在，命中的交 `route()` 末尾(615-620)的 `upload_func` 上传。容器内写文件回的是容器内路径，宿主 `Path.is_file()` 必然命不中 → 静默跳过 → 静默漏发。
- `tools/builtin_tools.py:584` 的 `send_im_message`（risk=medium）只发文本，收件人 `target` 由模型任意指定，故保持 gated。无任何工具能把文件送回当前发起人。
- `outbound.py` 是 `fleetent.outbound` 的 re-export shim；真实模块 `fleetent/outbound.py` 的 `send_to`(20) 按 `platform` 分派到 `_slack_send_dm`/`_slack_send_channel`/`_telegram_send`(145)，全部只发文本。Slack 出站文件能力只存在于 `slack.py:_make_upload_func`(255-277) → `files_upload_v2`；Telegram 侧零出站文件。
- 收件人来源已就绪：`ToolContext.session_context`（im-message-context 已落，`platform`/`sender_id`/`chat_type` 由 IM 适配器填充、平台权威）；连接器来源已就绪：`ToolContext.outbound_connectors`（builtin-outbound-tool 已落）。
- workspace 相对路径 → 宿主真实路径的翻译已就绪：`SandboxManager.workspace_host_path(scope, session_id, agent_name)`(manager.py:221) 求宿主根 + `file_sandbox_io.resolve_host_path(root, path)`(file_sandbox_io.py:123) 做 `..` 越界拒绝的相对翻译——这正是文件工具宿主围栏用的同一翻译。
- 工作区 scope 来自 `SandboxManager.scope`（`Scope.SESSION`/`Scope.AGENT`，manager.py:45-47、81）。

## Goals / Non-Goals

**Goals:**
- 新增宿主侧 `send_file(path)`：workspace 相对路径经宿主翻译读真实文件后发回**当前发起人**；收件人由 harness 从 `session_context` 固定、模型不可指定。
- `send_file` 免审批当且仅当 `workspace_scope==session ∧ dm ∧ session_context 非空`，否则 fail-closed 回审批路径；`session_context=None`（scheduled/sub_agent/invoke_agent）一律 fail-closed。
- 废弃结构性失效的正则嗅探自动回流，把静默漏发改为显式"外发失败"提示。
- 补齐 Telegram `send_document` 出站，Slack/Telegram 共用统一出站文件原语。

**Non-Goals:**
- 不改 `resolve_action_mode` 契约、不改 registry 既有 risk 常量、不新增 action gate 动态 risk 缝（见 D1）。
- 不碰 `builtin-shell-tool`、`image-generation-tool`、`vision-as-tool`、`skill-yaml-frontmatter`、`action-gate`/`approval-minimization` spec（其他 change 所有权）。
- 不改 inbound 文件接收（`im-file-attachment` / `_save_file_to_workspace` / `_download_attachments` 不动）。
- 不动 workspace rooting、不动 scope 语义。

## Decisions

### D1：`send_file` 条件免审批 = 收件人 harness 固定 + 工具体内 fail-closed，不经 action gate

`send_file` 以 registry `risk_level="none"` 注册 → action gate 解析为 `DIRECT`（不弹审批）。其"免审批当且仅当三条成立"的条件门控**在工具体内**实现：工具读 `tool_context.session_context` 与 `SandboxManager.scope`，三条任一不成立则不发送、返回引导改用 `send_im_message` 的文本。

为何这样而非"注册 medium + 让 gate 动态判定"：
- action gate 的 `risk = get_risk_level(name)`（loop.py:741）是**静态工具名查表**，无 per-call 动态 risk 缝；`resolve_action_mode` 的契约（CRITICAL hardcode REJECT、unknown fail-closed、SANDBOX→非 sandbox-backed 升 APPROVAL）是全批共识"绝不改"的红线。
- `send_file` 与 `send_im_message` 的安全差异在**收件人**：后者收件人由模型任意指定（不可信目标）故 medium gated；前者收件人由 harness 从 `session_context` 固定（无模型可控目标）。把不可信输入消除在源头（固定收件人），免审批正当性就不再依赖 gate 弹窗，而依赖"收件人受约束 + 会话私有封闭"——与地基 `sandbox-containment-gating`"免审批绑封闭"同构。
- **备选 A：注册 medium，gate 弹审批，工具内不判** → 否决：变成每次外发都弹审批，丢失"会话私信内自动送回产物"的核心价值；且无法表达"仅 session+dm 免审批"的条件性（gate 是静态的）。
- **备选 B：新增 action gate 动态 risk 回调**（让工具按上下文返回 risk）→ 否决：直接违反"不改 `resolve_action_mode` 契约、不新增动态 risk 缝"红线，且把条件逻辑漏进 governance 公共契约。
- **备选 C：注册 none，工具内永远直发不判** → 否决：等于无条件免审批，违反"fail-closed"要求，频道/agent-scope/无上下文场景会指向不确定收件人。
- 故选**工具体内 fail-closed**：免审批能力由 registry=none 提供，条件性与安全边界由工具体内前置条件 + harness 固定收件人提供，governance 契约零改动。

### D2：统一出站文件原语 `send_file_to`，按平台分派，Slack/Telegram 共用

在 `fleetent.outbound` 真实模块新增 `send_file_to(platform, connector, target, path, *, target_type="user", thread=None)`，对齐既有 `send_to` 的按 `platform` 分派结构：
- Slack：`files_upload_v2(channel=<target/解析的 DM channel>, thread_ts=thread, file=path)`，复用 `slack.py` 既有上传行为。
- Telegram：`bot.send_document(chat_id=target, document=path)`（新增；此前 Telegram 零出站文件）。
- 返回 `bool`（成功/失败），失败记 warning 不抛——与 `send_to` 同语义。
- `slack.py:_make_upload_func` 收敛到该原语之上（行为不变，去重）；`send_file` 工具与 IM 适配器上传共用同一投递实现。
- **备选：在 `send_file` 工具内直接调连接器方法** → 否决：会让工具同时承担"平台分派 + 投递细节"，且与适配器各写一套 Slack 上传逻辑漂移。收敛到 `outbound` 原语单点投递。
- 模块边界：`outbound` 是顶层基础设施（已声明无 platform 依赖），`tools` 与 `im_gateway` 均经其 public API；新原语加在真实模块、由 `outbound.py` shim re-export。

### D3：正则嗅探回流退役 + 显式外发失败，杜绝静默漏发

移除 `route()` 末尾(615-620)基于 `_extract_generated_image_paths` + 宿主 `Path.is_file()` 的自动上传。过渡策略：
- 保留 `NormalizedMessage.upload_func` 注入通道（出站文件原语复用它，且 `im-generated-image-upload` 该字段契约不变）。
- 把"扫到产物路径却宿主命不中 → 静默跳过"改为：本轮确有生成型工具产物（仍可由 tool 结果文本判断"有产物意图"，但**不再用宿主 `is_file` 判存在/不再据此上传**）却无法宿主命中时，`route()` 追加一条显式"外发失败：请用 send_file 工具发送产物"提示到回复。
- 正路是 agent 显式调 `send_file`；normalizer 端只负责"不静默漏发"，不再做宿主端路径推断上传。
- **备选：normalizer 端也翻译容器路径后宿主上传** → 否决：normalizer 不持有 ToolContext/manager scope，且这会把"产物送回"决策权从 agent（显式 send_file）夺回到宿主正则推断，违背"执行面收敛 + 显式工具"方向；且无法表达收件人固定/fail-closed 语义。
- `_extract_generated_image_paths` / `_IMAGE_GENERATED_RE` / `_FILE_WRITTEN_RE` 降级为仅"是否有产物意图"的过渡提示判断，或随退役删除——实现期按是否还需提示判断决定保留与否。

## Risks / Trade-offs

- **退役正则回流后，旧"自动上传生成图片"行为消失** → 这是有意为之（容器模式下它本就失效）；用显式 `send_file` + 过渡期外发失败提示替代，避免用户以为产物已送达。集成测试覆盖"不再静默漏发"。
- **`send_file` 误把敏感文件发出** → 收件人 harness 固定（只发回当前发起人）、路径限定 workspace 相对（`resolve_host_path` 拒 `..`）、仅 session+dm 免审批——三重约束；非满足场景 fail-closed 回审批。
- **`workspace_scope` 读取时机** → `send_file` 读 `_get_manager().scope`（进程级，启动时定），与文件工具/`run_code` 同源；unit 覆盖 session/agent 两分支。
- **无 IM 网关路径（CLI/HTTP/scheduled/sub_agent）调用 `send_file`** → 一律 fail-closed/返回说明文本不抛，保证无 platform 环境 `fleetent agent run` 不被打断。
- **Telegram `send_document` 的 `document` 入参形态**（文件路径 vs 打开的文件对象 vs `InputFile`）→ 实现期按 python-telegram-bot 版本定，以 integration mock 锁定调用契约；失败不抛。
- **收敛 `_make_upload_func` 触碰既有 Slack 上传路径** → 行为保持不变（同 `files_upload_v2` 调用），仅改为经统一原语；integration 对照原行为。

## Migration Plan

- 无 DB 迁移（仅文件读 + 出站投递）。
- `send_file` 为新增工具，默认随内置工具注册；agent 经 `allowed_tools` 控制可用性（不在白名单则不暴露），无需新增配置字段。
- 退役正则回流为纯行为变更：部署后生成图片不再自动上传，改由 agent 显式 `send_file`；过渡期提示引导用户/agent 迁移。
- Rollback：回滚代码即可；`send_file` 工具消失、正则回流恢复（但其对容器模式本就失效），无数据残留。

## Open Questions

- 过渡期"外发失败提示"是否需要可配置开关，还是固定行为——倾向固定（杜绝静默漏发是安全要求），实现期定。
- `_extract_generated_image_paths` 是否完全删除，还是保留为"有产物意图"判断以驱动过渡提示——取决于过渡提示是否需要"仅在确有产物时"才出，实现期以测试锁定。
- `send_file_to` 的 Slack `target`：DM 场景需先 `conversations_open` 解析 channel（同 `_slack_send_dm`）还是直接用 `session_context` 已知 channel——实现期对齐 `_make_upload_func` 现状（其用 inbound channel），DM 收件人解析复用 `_slack_send_dm` 范式。
