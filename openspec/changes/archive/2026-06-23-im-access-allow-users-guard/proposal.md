## Why

托管部署下，任何「配了 IM 平台（slack/telegram）+ 绑了 user」的 managed agent 都会在启动时崩溃。

复现链：agent pin+enable 正常 running → 绑定 user（内部 user_id 是 UUID，如 `5f5904ef-efcf-42bb-82fa-ad5a150b078c`）+ 配 slack/telegram → 下一轮 reconcile，platform `materialize._materialize_im_access` 把 `agent_store.list_users_for_agent()` 返回的**内部 user_id（UUID）**写进落地 `agent.yaml` 的 `im.<platform>.access.allow_users`。agent 进程启动时，`agent_config._reject_inline_secrets` 扫描 `im` 子树，`secret_scan.looks_inline_secret` 的 `_SECRET_RE` 含 `[A-Za-z0-9_-]{24,}` 分支，把 36 字符的 UUID 误判为内联 secret，抛：

```
ValueError: inline secret-like value in agent 'demo' at 'im.slack.access.allow_users.0';
reference secrets by environment-variable name instead
```

agent 崩溃，无法启动。

**根因定性**：`allow_users` 存内部 UUID 是**正确的设计**，不是 bug 源——agent 侧 `im_gateway/access.py:user_allowed` 用 `identity in access.allow_users` 匹配入站用户，`identity` 来自 `resolve_identity()`；managed 下 platform 经 `set_im_identity_resolver` 注入 resolver，把入站 `platform_user_id` 解析成内部 user_id（UUID），与 `list_users_for_agent()` 写入的 UUID 同源、可比对。问题纯粹是 inline-secret 守卫把这个**非 secret 的 id 列表**误判为 secret。

## What Changes

- **给 `im.*.access.allow_users` / `im.*.access.allow_groups` 路径加 inline-secret 豁免**：`agent_config._reject_inline_secrets` 在扫描 `im` 子树时，对落在这两个路径下的值跳过 secret 检测——它们是 id 列表（内部 user_id / 群组 id），不是凭据。这与现有对 `command` / `args` / `id` / `transport` 的结构化字段豁免是同类做法。
- **不削弱真 secret 防护**：豁免仅限 `access.allow_users` / `access.allow_groups` 两个路径；`im.slack.bot_token_env`、`im.telegram.bot_token_env` 等真凭据字段仍被扫描，明文 token 仍 fail loud。
- **不改 agent 运行时行为、不改 materialize**：`allow_users` 仍存内部 UUID，匹配逻辑不变；本 change 只放宽加载校验对已知非 secret 字段的误报。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `file-agent-runtime`：MODIFY 既有「Secrets rejected in agent files」requirement——明确 `im.*.access.allow_users` / `im.*.access.allow_groups` 属结构化非 secret 字段，不被 inline-secret 扫描标记；新增对应正/反场景。

## Impact

- **owning package**：`agent_config.py`（顶层共享 schema / 加载模块）。
- **public API surface**：无新增/变更对外 API；`_reject_inline_secrets` 是模块内私有函数，仅内部豁免逻辑收紧。
- **owned tables**：无。
- **config namespace**：无。
- **cross-module dependencies**：无新增。`agent_config.py` 仍只依赖 `fleetent.secret_scan`（中性纯函数），**不 import `fleetent.platform.*`**，符合 agent/platform 解耦方向。改动落在 agent 侧共享 schema 的「加载校验误报修正」，不触碰 agent 运行时对话行为，不触碰 platform。
- **模块边界确认**：项目硬约束「不改 agent 运行时」管的是 agent 对话循环 / 生命周期行为；`agent_config._reject_inline_secrets` 是 agent.yaml 的**加载期校验**，给它对一类已知非 secret 字段加白名单豁免不改变任何运行时语义、不引入反向依赖，判定**不越界**。无需改 platform 侧 materialize（`allow_users` 存 UUID 是正确设计）。
- **migration / shim plan**：无 schema/迁移。纯行为修正：存量崩溃的 managed agent 在本 change 上线后下一轮 reconcile / 重启即可正常加载。
- **范围外**：不改 `secret_scan._SECRET_RE`（全局熵阈值不动，避免削弱其它字段的 secret 检测）；不改 IM 身份解析 / `allow_users` 匹配语义；不改 materialize 写入内容。
