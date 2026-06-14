# descope-channel-agents Tasks

> TDD：实现 task 先测试见红 → 实现见绿（最窄命令 `uv run pytest <file>::<test> -x -q`），测试在实现之前。迁移号 append after head、**勿硬编码**（apply 前 pull 确认）。窄边界：不碰 agent.yaml `bindings.channels/users` 与 default-agent 查找顺序（留阶段 3）。

## 1. 迁移：drop channel_agents（Alembic）

- [x] 1.1 [测试] integration：跑到 head 后 `channel_agents` 表不存在（先红）
- [x] 1.2 [测试] integration：删除一个 agent 仍正常（不再有 channel_agents 子表参与级联）；其余绑定级联不受影响（先红/现态确认）
- [x] 1.3 [实现] 新迁移（append after head、勿硬编码）：`DROP TABLE channel_agents`；downgrade 重建空表（列含 `bound_version_id`、UNIQUE(platform,channel_id)、FK→agents.id ON DELETE CASCADE，不恢复数据）→ 1.1/1.2 转绿

## 2. 代码：移除 channel_agents 读写

- [x] 2.1 [测试] integration：`agent_store` 不再有 `assign_channel`/`unassign_channel`/`get_agent_for_channel`/`list_channels_for_agent`/`get_channel_bound_version_id`；`/admin/agents/{name}/bindings/channels*` 端点 404；`references()` 仅按 user_agents + default 判（先红）
- [x] 2.2 [实现] `agent_store.py` 删上述 5 函数；`admin_cli/agents.py` 删 `assign-channel`/`unassign-channel` 命令；`agent_admin_api.py` 删 channel bind/unbind 端点 + bindings 列表里的 channels 段（:123-128/:226-239/:252）；`agent_admin_store.references()`（:124）去 channel_agents 检查 → 2.1 转绿
- [x] 2.3 [测试] integration：archive 保护现仅按 user 绑定 + default 阻挡（删 channel 检查后行为正确）；clone 不复制 user 绑定/default（现态确认）

## 3. 文档 + spec 同步

- [x] 3.1 `docs/architecture/data-model.md`：§3.2「Agent 定义/绑定」段删 `channel_agents`；ER 图删节点 `channel_agents` + 边 `agents→channel_agents`、`agent_versions→channel_agents`（含 bound_version_id 休眠列那条）；图例「活边」计数随之更新
- [x] 3.2 archive 时同步 delta 到 canonical：`channel-agent-binding`(REMOVED 整 capability)、`agent-admin-api`、`agent-admin-ui`、`agent-definition`(FK 列去 channel_agents)、`agent-template-clone`、`agent-lifecycle-toggle`
- [x] 3.3 **不动**（留阶段 3）：`default-agent` 查找顺序、`Agent lookup priority order`、agent.yaml `bindings.channels/users`——proposal/design 已声明暂留

## 4. 收尾

- [x] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（重点：agent 删除/archive/clone 路径、无 channel_agents 残留引用报错）
- [x] 4.2 全仓 grep：无残留 `channel_agents` / `assign_channel` / `get_agent_for_channel` 代码引用（迁移历史/归档除外）；`/bindings/channels` 端点引用清零
- [x] 4.3 `openspec validate descope-channel-agents` 通过；checkbox 全 `[x]`
