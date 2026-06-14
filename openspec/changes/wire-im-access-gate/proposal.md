# wire-im-access-gate

> IM 访问模型（[im-access-model](../../../docs/architecture/im-access-model.md)）**阶段 3（功能核心）**：把阶段 2 立的平台表/能力列接进 materialize，准入闸按 chat_type 分流、默认关，并退役被取代的旧文件绑定路由（C）。**不做任何改名**（`connectors`/`ConnectorAccess`/`allow_channels` 名字保留，全留阶段 4）。head=088（新迁移若需则 append，**勿硬编码**；本阶段多为代码/agent.yaml，可能无管理库迁移）。已核 `knowledge-base-standalone-service` 不碰。

## Why

阶段 2 立了 `agent_im_groups` + `agents.supports_dm/supports_groups`，`user_agents` 早已在。但 materialize 现在对 connector access **写默认占位**（materialize.py:91 "until authoring lands"），且准入闸不看会话类型、群默认开（空 `allow_channels`=放行所有群）。本阶段"authoring lands"：把平台配置接进 agent.yaml，闸按设计模型执行：私聊/群聊能力分流 + 群默认关。同时退役被 connector=agent 模型取代的旧"文件绑定路由"（阶段 1 推迟的 C）。

## What Changes（功能，零改名）

### A — 接线 + 闸
- **能力列上 agent.yaml**：`AgentConnectors` 加 `supports_dm` / `supports_groups`（agent 级）。
- **materialize 接线**：`agent_file_from_store` 从平台表填 connector access——`allow_users` ← `user_agents`、群白名单 ← `agent_im_groups`（暂仍写进 `allow_channels` 字段，阶段 4 改名 `allow_groups`）、`supports_dm/groups` ← `agents`。connector 凭据（bot_token_env）仍经 `config_overrides` 手工授权、materialize 深合并（不被覆盖）。
- **闸按 chat_type 分流**（`im_gateway/normalizer.py` + `access.py`）：
  - **DM**：准入 ⟺ `supports_dm` ∧ 用户门（`allow_users` 或本地批准；`allow_all_users` 仍是逃生阀）。
  - **群**：准入 ⟺ `supports_groups` ∧ 群 ∈ 群白名单（群单门：群在白名单即视为该群成员授权，跳用户门）。
  - **默认关翻转**：群白名单为空 = **不进任何群**（现状是空=放行所有群，安全风险）；`supports_*` 默认 false = 默认不接私聊/群聊。

### C — 退役旧文件绑定路由（阶段 1 推迟项）
- 移除 agent.yaml 文件绑定路由残留（`bindings.channels` / `bindings.users` 若仍在模型中）；`bindings.default`（默认 agent 标志）**保留**（仍是 live 的默认 agent 机制）。
- `get_agent_for_context` 收口为"连接器已 stamp 的 agent > 默认 agent > bare run"（去掉 channel/user 绑定查找——本就返回 default，清理签名/死参）。

## Capabilities

### Modified Capabilities
- `per-agent-im-access`: 准入闸**按 `chat_type` 分流**（DM=supports_dm+用户门；群=supports_groups+群白名单单门）；**群白名单默认关**（空=不进任何群，取代"空=放行所有群"）；新增 `supports_dm`/`supports_groups` 能力位由闸消费；access 配置由平台表（`user_agents`/`agent_im_groups`/`agents.supports_*`）**materialize 进 agent.yaml**（取代默认占位）。
- `default-agent`: agent 查找顺序改为"**连接器已识别的 agent > 默认 agent > bare run**"（移除已死的 channel 绑定 > user 绑定层）；默认 agent 机制（`bindings.default`）保留。

## Impact

- **owning package**：`runtime`/`im_gateway`（闸 + agent_config）、`platform`（materialize 接线）。注意：闸与 agent_config 在 agent 侧、materialize 在平台侧——边界不变（平台单向写 agent.yaml，agent 只读）。
- **public API surface**：agent.yaml `connectors`（保留名）新增 `supports_dm`/`supports_groups`、access 块改由 materialize 填（之前默认占位）；闸行为变更（默认关）。无 HTTP API 变更。
- **owned tables**：无新表/列（消费阶段 2 的）；可能无管理库迁移（纯代码 + agent.yaml）。
- **config namespace**：agent.yaml `connectors.*`（名保留）；`bindings.channels/users` 退役。
- **cross-module dependencies**：不碰 agent 零 platform import；materialize 在平台侧读表、agent 侧只读 agent.yaml。
- **migration / shim plan**：无 schema 迁移（若需则 append after head 088、勿硬编码）；agent.yaml 字段演进，pre-launch 无回填。**改名零**（`connectors`→`im`、`ConnectorAccess`→`ImAccess`、`allow_channels`→`allow_groups` 全留阶段 4）。
- **风险**：① 群默认关是**行为翻转**——现有依赖"空=放行所有群"的部署会变（pre-launch，预期）；② materialize 填 access 时勿覆盖 `config_overrides` 里手工授权的 bot 凭据（深合并顺序）；③ 闸改动是安全核心，integration 重点覆盖 DM/群 双路 + 默认关 + allow_all_users 逃生阀。
- **相邻切片**：依赖阶段 1/2 已落地（已落）；阶段 4（改名）在其后；已核无在跑 change 碰这些文件；apply 前 pull 确认。
