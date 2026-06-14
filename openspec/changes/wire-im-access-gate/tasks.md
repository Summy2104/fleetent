# wire-im-access-gate Tasks

> TDD：实现 task 先测试见红 → 实现见绿（最窄命令 `uv run pytest <file>::<test> -x -q`），测试在实现之前。**零改名**（connectors/ConnectorAccess/allow_channels 名字保留，留阶段 4）。闸是安全核心——重点覆盖。

## 1. agent_config：能力字段（零改名）

- [ ] 1.1 [测试] unit：`AgentConnectors` 含 `supports_dm`/`supports_groups`（默认 false）；解析/序列化正确（先红）
- [ ] 1.2 [实现] `agent_config.AgentConnectors` 加 `supports_dm`/`supports_groups`；移除残留 `bindings.channels/users`（若模型中仍有；保留 `bindings.default`）→ 1.1 转绿

## 2. materialize 接线

- [ ] 2.1 [测试] integration：`agent_file_from_store` 从 `user_agents`→`allow_users`、`agent_im_groups`→群白名单(allow_channels 字段)、`agents.supports_*`→supports_*；`config_overrides` 里手工 bot 凭据**不被覆盖**（深合并）（先红）
- [ ] 2.2 [实现] materialize 读三表填 access 块（取代 line 91 默认占位），合并顺序保 config_overrides 凭据 → 2.1 转绿

## 3. 准入闸按 chat_type 分流 + 默认关（安全核心）

- [ ] 3.1 [测试] integration：DM 路——supports_dm 开/关 × user 在/不在 allow_users × allow_all_users（先红）
- [ ] 3.2 [测试] integration：群路——supports_groups 开/关 × 群在/不在白名单 × 群单门跳用户门（先红）
- [ ] 3.3 [测试] integration：**默认关**——新 agent 空配置 → DM 拒、群拒；**翻转验证**：空群白名单 = 不进任何群（非旧"放行所有群"）（先红）
- [ ] 3.4 [实现] `im_gateway/normalizer.py` + `access.py`：闸按 msg.chat_type 分流（DM=supports_dm+用户门；群=supports_groups+群白名单单门）；空群白名单默认关 → 3.1/3.2/3.3 转绿

## 4. C：退役旧文件绑定路由

- [ ] 4.1 [实现] `get_agent_for_context` 收口为"连接器识别 agent > 默认 > bare"（去 channel/user 绑定查找死分支/参数）；确认 agent_config 无 `bindings.channels/users` 残留
- [ ] 4.2 archive 时同步 delta：`default-agent`（查找顺序 + 全局默认措辞）、`per-agent-im-access`（闸 chat_type 分流 + 群默认关 + materialize 来源）

## 5. 文档 + 收尾

- [ ] 5.1 `docs/architecture/data-model.md`：§3.3 agent.yaml `connectors` 块注记 supports_*（名保留）；如有 IM access 来源说明同步（user_agents/agent_im_groups/agents→materialize）
- [ ] 5.2 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（**重点：IM 闸 DM/群双路 + 默认关翻转 + allow_all_users 逃生阀 + materialize 不覆盖凭据**）
- [ ] 5.3 确认**零改名**（connectors/ConnectorAccess/allow_channels 名字未动，留阶段 4）
- [ ] 5.4 `openspec validate wire-im-access-gate` 通过；checkbox 全 `[x]`
