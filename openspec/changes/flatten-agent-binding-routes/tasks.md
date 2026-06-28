## 1. Backend: per-type read endpoints (replace aggregate)

- [ ] 1.1 写测试：在 `tests/integration/test_agent_admin_api.py` 加 `GET /admin/agents/{name}/users`、`/groups`、`/mcp` 各自返回该类绑定（viewer+admin 可读、未知 agent 404）；见红
- [ ] 1.2 实现：在 `agent_admin_api.py` 新增三个 per-type 读 handler（复用 `list_users_for_agent`/`list_groups_for_agent`/`list_mcp_servers_for_agent`），删除 `get_bindings` 聚合 handler；1.1 见绿
- [ ] 1.3 改写 `tests/unit/test_coverage_admin_connector_handlers.py` 中断言 `get_bindings` 形状的用例为新 per-type handler；见绿

## 2. Backend: flatten write routes out of /bindings prefix

- [ ] 2.1 写测试：在 `tests/integration/test_agent_admin_api.py` 把 users/groups/mcp 写路由断言改为 `/agents/{n}/users/{id}`、`/agents/{n}/groups`(+`/{platform}/{group_id}`)、`/agents/{n}/mcp/{id}`；见红
- [ ] 2.2 实现：在 `agent_admin_api.py` 把 `bind_user`/`unbind_user`/`bind_im_group`/`unbind_im_group`/`bind_mcp`/`unbind_mcp` 的路由装饰器去掉 `/bindings/` 前缀（handler 逻辑、audit、权限不变）；2.1 见绿
- [ ] 2.3 跑 `uv run pytest tests/integration/test_agent_admin_api.py -q` 该文件全绿

## 3. Frontend: per-type queries + flattened mutation URLs

- [ ] 3.1 写/改测试：`frontend/src/features/agents/api.test.tsx` 把 `bindings` 聚合 mock 换成 per-type GET（users/groups/mcp），mutation URL 改为去前缀路径；见红
- [ ] 3.2 实现：`api.ts` 用 `useAgentUsersQuery`/`useAgentGroupsQuery`/`useAgentMcpQuery` 替换 `useAgentBindingsQuery`；mutation URL 去 `/bindings/` 前缀
- [ ] 3.3 实现：`configure.tsx` 的 IM tab（users+groups）与 MCP tab 各自取数；3.1 见绿
- [ ] 3.4 跑前端测试套件该 feature 绿，去除死的 `AgentBindings` 聚合类型

## 4. 收尾验证

- [ ] 4.1 全仓 grep 确认无 `/bindings/` 路由残留、无 `get_bindings`/`useAgentBindingsQuery` 引用
- [ ] 4.2 `make test-pr` + 受影响 integration 全绿
- [ ] 4.3 `openspec/specs/agent-admin-api`、`agent-admin-ui` delta 与实现一致（apply 后 sync/archive 用）
