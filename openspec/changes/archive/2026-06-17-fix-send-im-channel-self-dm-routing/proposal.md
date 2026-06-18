## Why

Slack 黑盒 E2E（2026-06-16，发现④）暴露一处**文件投递目标不一致**：用户在**频道**里让 agent 把产物"发给我"（如"生成一张图发给我"）时，模型有时不走 `send_file`，而是调 `send_im_message(target=<发起人>, target_type="user", files=[...])`。

根因是两条投递路径的目标语义不同，且审批边界与投递面口径错位：

- `send_file`（`builtin_tools.py` ~968-1034）的 recipient **由 harness 钉死**为当前会话地址（`conversation_address` 的 chat_id/target_type/thread_id），模型无法改写——频道里必然落回**该频道线程**。
- `send_im_message`（~829-913）由模型自传 `target`/`target_type`；`target_type="user"` 路由到**该用户的私信(DM)**。其审批在**收件人身份轴**上判级（`approval_policy.risk_for`）：当 `(target,target_type)` 落在"当前会话"上时为 `none`（免审）。

错位点：当 `target=发起人本人`、`target_type="user"`、但**入站会话发生在频道**时——审批轴把"发给发起人"判为"当前会话"→**免审静默放行**，可投递面却是发起人的 **DM**，而非用户此刻所在的**频道线程**。于是产物被静默搬进发起人私信，与 `send_file` 行为不一致。

硬证据：该次回复尾部出现 `📬 实际投递：文件 1（U09…R25）；消息 1（U09…R25）`（`traces.py:render_delivery_trailer` ~151-174）——文本消息+文件**都投给了发起人**，这是 `send_im_message` 独有的产物（`send_file` 不发独立文本消息）。

## What Changes

仅做经与用户确认的 **①(方案A) + ②**，明确**不含**方案B（升级审批）与 ③（`generate_image` 默认投递）。

- **① 会话钉定护栏（方案A）**：在 `send_im_message` 中，当存在权威 `conversation_address` 且其为**频道会话**（`chat_type == "channel"`），且本次请求 `target` 解析为**当前会话发起人**、`target_type == "user"` 时，把投递**改投回当前会话地址**（频道 + 线程），与 `send_file` 同面——文本与文件都落频道线程，而非发起人 DM。该改写对**给他人外发**（`target != 发起人`）与**纯 DM 会话**（`conversation_address` 本身是 DM）**无任何影响**，他人外发仍按 medium 审批。
- **② 收紧 `send_im_message` docstring**：明确"本工具用于在对话之外**主动给其他用户 / 其他频道**发消息；要回复当前对话，请用 `send_file`（或直接文本回复）"，降低模型一开始就把"发给我"误路由到本工具的概率。

不做：不改 `send_file`；不动他人外发的审批门；不改 `generate_image` 的返回/投递语义；不触碰 `im_gateway` 里 `conversation_address` 的构造（`target_type` 字段的潜在 latent bug 另案，本 change 依赖 `chat_type` 判频道，规避之）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `builtin-outbound-tool`: 在"recipient-identity axis"既有判级之上，补充**投递面钉定**要求——频道会话中针对当前发起人的 `target_type="user"` 投递，投递面 SHALL 钉回当前会话地址（频道线程），而非发起人 DM；免审口径不变（仍是当前会话→`none`）。docstring 措辞收紧（描述性，不改对外签名）。

<!-- 不变：delivery-receipts（footer 渲染不变）、sandbox-file-send（send_file 行为不变）、im-message-context。 -->

## Impact

**owning package**：agent runtime —— `src/fleetent/tools/builtin_tools.py`（`send_im_message` 内的投递路由决策）。全程 agent runtime 侧，**不 import `fleetent.platform.*`**（保持单向依赖）。

**public API surface**：无新增对外 API；`send_im_message` 工具签名不变（行为内部收敛）。新增一个**纯函数**决策助手（如 `_resolve_self_dm_redirect(target, target_type, address, sender_id)`）返回可选的投递改写，便于 unit 层在无 DB/HTTP 下隔离测试。

**owned tables**：无（零 schema、零迁移）。

**config namespace**：无（无新配置；护栏无条件生效）。

**cross-module dependencies**：读取 `tool_context.conversation_address` / `session_context`（`send_file` 已在用）；投递经既有 `fleetent.outbound.send_to` / `send_file_to`（已在用，本 change 需把 `target_type`/`thread` 一并透传给文件投递分支以落线程）。无新增跨模块契约，不触碰 agent↔platform 边界。

**migration / shim plan**：无（无模块迁移、无持久层改动）。

**受影响代码**：`src/fleetent/tools/builtin_tools.py`（`send_im_message` + 新纯函数 + docstring）；新增 `tests/unit/test_send_im_self_dm_routing.py`（纯函数红/绿）；视需要补 integration 用例覆盖端到端透传（频道会话 → 发起人 user 投递落频道线程）。
