## Why

频道场景下，用户/自动化无法用文本审批指令完成审批。`normalizer.route`（`im_gateway/normalizer.py:363`）用 `_APPROVAL_RE.match(msg.text.strip())` 识别 `approve`/`reject <id>` 指令，而 `.strip()` 只去首尾空白、不剥离 `<@bot>` mention。频道里消息**必须 @bot** 才被 agent 收到（`app_mention`），但 `<@U…>` 前缀破坏 `^(approve|reject)` 匹配 → 审批指令被当成新任务进 agent loop（实测：触发了一个新审批）。结果：频道里文本审批走不通（只能真人点按钮），user-token 自动化审批测试受阻。DM 不需 @、纯 `approve <id>` 已可正常匹配。

## What Changes

- `normalizer.route` 在匹配 `_APPROVAL_RE` 前**剥离 leading bot mention**（单个 `<@id>`，可带 `|label`），使频道里 `<@bot> approve <id>` 也能被识别为审批指令、正常 resolve。
- 抽出纯函数承载「剥离 leading mention + 审批匹配」，便于 unit 覆盖；`route` 复用之。
- 保持不变：真人点审批按钮、DM 文本审批、`reject`/`approve always`；正则仍严格要求 `approve <hexid>`，自然语言（如 "approve the plan"）不误伤。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `im-gateway`: 「Slack approval interactivity」requirement 增补——频道场景下 `approve`/`reject <id>` 文本指令容忍 leading bot mention 前缀（匹配前剥离单个 `<@id>`）。

## Impact

- **改动代码**：`src/fleetent/im_gateway/normalizer.py`（agent runtime）——新增剥离 leading mention 的纯函数 + `route` 复用。新增 unit 测试。
- **模块边界**：owning = `im_gateway`（agent runtime）；public API surface 无新增；owned tables = 无；config namespace = 无；cross-module deps = 无，**不 import platform，守 agent/platform 解耦**（改后 agent 仍能在无 platform 环境 `fleetent agent run`）；migration/shim = 无。
- **风险**：低。仅在审批匹配入口前剥离一个 leading mention；`_APPROVAL_RE` 仍锚定 `^approve <hexid>$`，普通含 @bot 的自然语言不会被误判为审批。真人按钮路径（`block_actions` handler）完全不动。
