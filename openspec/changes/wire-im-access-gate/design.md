# 设计：wire-im-access-gate（IM 访问模型阶段 3 · 功能核心）

## D1 — 零改名（与阶段 4 的分工）

本阶段**不动任何名字**：block `connectors`、类 `ConnectorAccess`/`SlackConnector`、字段 `allow_channels` 全保留。`allow_channels` 字段**语义变窄为群白名单**（DM 不再查它）但名字不变——阶段 4 才 `allow_channels`→`allow_groups`、`connectors`→`im`、`ConnectorAccess`→`ImAccess`。

为什么：①phase 3 已是大功能改动，叠加"外科手术式改一个重载词（connectors 还指 KB/工具）"风险太高；②功能可独立测、改名纯机械——分开干净。代价：phase 3 落地后 `allow_channels` 这名字暂时名实不符（实为群白名单），阶段 4 修。

## D2 — 闸逻辑（按 chat_type 分流 + 默认关）

```
解析 agent（连接器已 stamp）+ 内部 User（im_users）
DM  → 准入 ⟺ supports_dm    ∧ (allow_all_users ∨ user ∈ allow_users ∨ 本地已批准；否则 require_approval 走审批/拒)
群  → 准入 ⟺ supports_groups ∧ group ∈ allow_channels(=群白名单)   # 群单门：命中即放行该群成员，跳用户门
默认关：supports_* 默认 false；allow_channels 空 = 不进任何群（翻转旧"空=放行所有群"）
```

- **翻转点**：现状 `channel_allowed` 空 `allow_channels` 返回 True（放行所有群）。本阶段群路径改为"空=拒"。这是安全修复（agent 不能被拉进任意群）。
- **群单门**沿用现有"channel listing grants implicit user access"的思路，但默认从开翻到关。
- **DM 不查 allow_channels**（它是群白名单）；DM 只看 supports_dm + 用户门。
- `allow_all_users` 逃生阀保留（开放内部 bot）。

## D3 — materialize 接线（凭据 vs 访问的合并）

`agent_file_from_store` 现写默认占位（materialize.py:91）。本阶段改为：
- `allow_users` ← `user_agents`（list_users_for_agent）。
- 群白名单（写进 `allow_channels` 字段）← `agent_im_groups`（按 platform 分组）。
- `supports_dm/groups` ← `agents`。
- **bot 凭据（bot_token_env 等）不在平台表**——仍由 agent 作者经 `config_overrides` 手工授权，materialize **深合并**（line 76 机制）。务必保证：填 access 字段时**不覆盖** config_overrides 里的 connector 凭据/手工字段（合并顺序：base + 平台 access + config_overrides 覆盖）。

## D4 — C：退役旧文件绑定路由

- 旧"channel 绑定 > user 绑定 > default"路由 runtime 早已不走（`get_agent_for_context` 返回 default）。本阶段把 **spec**（default-agent「Agent lookup priority order」+「Global default agent」的 channel/user 措辞）改为"连接器识别的 agent > 默认 agent > bare"。
- 代码：`get_agent_for_context` 清理（去 channel/user 绑定查找的死分支/参数）；agent_config 若仍有 `bindings.channels/users` 字段则移除（**保留 `bindings.default`**——默认 agent 仍 live）。apply 时确认这些字段是否真在模型中（可能早已不在，则 C 仅 spec 改）。

## D5 — 测试重点（安全核心）

integration 重点覆盖：DM 路（supports_dm 开/关 × 用户在/不在 allow_users × allow_all_users）；群路（supports_groups 开/关 × 群在/不在白名单 × 群单门跳用户门）；**默认关**（新 agent 空配置 → DM 拒、群拒）；materialize 不覆盖 config_overrides 凭据。
