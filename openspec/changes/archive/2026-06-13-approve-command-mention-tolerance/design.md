## Context

`normalizer.route`（`im_gateway/normalizer.py:361`）在进 agent loop 前，用 `_APPROVAL_RE.match(msg.text.strip())`（`:363`，正则 `:20` = `^(approve|reject)(\s+always)?\s+([a-f0-9-]{6,36})\s*$`）拦截文本审批指令。频道里消息必须 @bot 才被 `slack.py` 的 `app_mention` 收到，但其 `event.text` 含 leading `<@botid>`，`.strip()` 不剥离它，导致 `^(approve|reject)` 不匹配 → 审批指令落入 agent loop 当新任务。DM 走 `message`/im handler、不需 @，纯 `approve <id>` 可匹配（已实测）。

## Goals / Non-Goals

**Goals:**
- 频道里 `<@bot> approve <id>` / `reject <id>` 能被识别为审批指令并正常 resolve。
- 抽纯函数承载预处理 + 匹配，unit 可覆盖。
- 守 agent/platform 解耦；不破坏既有行为。

**Non-Goals:**
- 不改 `_APPROVAL_RE` 本身（仍严格要求 `approve <hexid>`）。
- 不动 Slack `block_actions` 按钮 handler（`slack.py`）。
- 不改 DM 文本审批、`reject`、`approve always` 的语义。

## Decisions

### D1：匹配前剥离单个 leading bot mention
新增纯函数剥离开头一个 mention：`re.sub(r"^\s*<@[^>]+>\s*", "", text, count=1)`。`[^>]+` 同时覆盖 `<@U123>` 与 `<@U123|display>` 两种 Slack 形式；`count=1` 只剥**开头一个**（审批指令形如 `@bot approve <id>`，mention 必在首）。**备选**：在 `_APPROVAL_RE` 里允许可选 mention 前缀——否决，正则会更难读且影响 group 下标。

### D2：抽纯函数，route 复用
新增 `_strip_leading_mention(text) -> str`，并让审批匹配走 `_APPROVAL_RE.match(_strip_leading_mention(msg.text).strip())`。纯函数无 I/O，unit 直接覆盖各形态。**理由**：route 是 async + 触达 store，难直接单测；预处理逻辑抽纯函数后可确定性测试。

### D3：保持正则严格、不误伤自然语言
`_APPROVAL_RE` 仍要求 `approve`/`reject` 后跟 6–36 位 `[a-f0-9-]`。剥离 mention 后，"@bot approve the plan" → "approve the plan" → `the plan` 非 hexid → 不匹配 → 照常进 agent loop。仅真正的 `approve <hexid>` 被拦为审批。

### D4：解耦不变
改动仅在 `normalizer`（agent runtime），不新增任何 import，尤其不 `import fleetent.platform.*`。改后 agent 仍能在无 platform 环境运行。

## Risks / Trade-offs

- **误判自然语言为审批** → D3：正则仍锚定 `^approve <hexid>$`，剥 mention 不放宽 id 格式。
- **多 mention / 中间 mention** → 只剥 leading 单个；审批指令约定 mention 在首，符合频道 @bot 习惯；非首的 mention 不影响（本就不是审批指令）。
- **真人按钮路径受影响** → 零影响：按钮走 `slack.py` 的 `block_actions` handler，与本文本路径独立。

## Migration Plan

纯代码行为修正，无数据迁移。回滚 = 还原 `normalizer.py` 改动，对其他模块零副作用。
