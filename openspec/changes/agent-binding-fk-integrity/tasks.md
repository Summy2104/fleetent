# agent-binding-fk-integrity Tasks

> 阶段 4（阶段 2/3 已落地；当前 Alembic head=`083`）。TDD：先测试见红、再实现见绿。

## 1. MCP 两表正名（方案 A，Alembic）

> 与第 2 节同一新迁移完成（迁移内先做改名腾名、再 batch 加 FK）。改名顺序：**先 `agent_mcp_servers`→`mcp_servers` 腾名，再 `agent_mcp_server_bindings`→`agent_mcp_servers`**——顺序换、无需临时名。

- [ ] 1.1 [测试] integration：head 后表名为 `mcp_servers`（注册表，原 `agent_mcp_servers`，列/UNIQUE 保留）+ `agent_mcp_servers`（绑定表，原 `agent_mcp_server_bindings`，PK(agent_id,server_id)/`created_by` 保留、既有 FK 保留）；旧表名 `agent_mcp_server_bindings` 不再存在；索引为 `idx_mcp_servers_agent`（先红）
- [ ] 1.2 [实现] 新迁移内执行两步顺序改名 + 索引改名；`connector_management/agent_mcp_server_store.py` 注册表 SQL 表名→`mcp_servers`；`agent_store.py` 的 bind/unbind/list_mcp_servers_for_agent + 删 agent 清理（:464）绑定 SQL 表名→`agent_mcp_servers` → 1.1 转绿
- [ ] 1.3 [实现] store 文件/函数名同步正名（推荐，避免「表名已正、代码名仍反」）：`agent_mcp_server_store.py`→ 注册表语义名（如 `mcp_server_store.py`），调用方（materialize / connector_admin_api / mcp_runtime）随动 import；保留 re-export shim 或一次性改全（按仓库迁移惯例）

## 2. 补 FK（同一 Alembic 迁移）

- [ ] 2.1 [测试] integration：head 后 `user_agents` / `channel_agents` / `agent_versions` / `mcp_servers` / `agent_secrets` 各有 FK→agents.id ON DELETE CASCADE；各自主键/唯一约束/索引保留（先红）
- [ ] 2.2 [测试] integration：删除一个持有这些绑定的 agent → 五表（含正名后 `mcp_servers` 的 per-agent 行、`agent_mcp_servers` 绑定行）对应行级联清空；非空孤儿存量行迁移前已清理/处理（先红）
- [ ] 2.3 [实现] 同一新迁移（append after head、勿硬编码）：改名腾名后 batch 重建五表加 FK→agents.id ON DELETE CASCADE（保留主键/唯一约束/索引）；迁移内先清理（或拒绝）违规孤儿行；downgrade 反向（去 FK + 反向改名）→ 2.1/2.2 转绿

## 3. 回归 + 守护 + 文档

- [ ] 3.1 [测试] integration：**改名回归**——materialize 的 `_mcp_servers_for_agent` 在新表名下仍正确：绑定（`agent_mcp_servers`）+ 版本快照 union 取 id、注册表（`mcp_servers`）取定义（per-agent 行优先、全局 `agent_id=NULL` 行兜底）（先红或现态确认）
- [ ] 3.2 [测试] integration/unit：守护——五表 FK 存在 + 级联；`connectors.agent_id` 仍无 FK（休眠列，确认未误加）；全仓无残留旧表名 `agent_mcp_server_bindings`（迁移历史/归档除外）
- [ ] 3.3 `docs/architecture/data-model.md` §3.2 + ER 图（约 line 148-149）：标注五表 FK→agents.id ON DELETE CASCADE（注明属 identity-model 阶段 4）；MCP 两表更新为 `mcp_servers`（注册）/`agent_mcp_servers`（绑定）新名与角色、ER 边随动

## 4. 收尾

- [ ] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（重点：agent 删除级联正确 + MCP 解析改名后无回归）
- [ ] 4.2 `openspec validate agent-binding-fk-integrity` 通过；checkbox 全 `[x]`
