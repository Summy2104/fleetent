# Tasks:退役 agent 版本化与 askit

> 纪律:每个实现 task 前先写测试(见红→见绿)。`agents` 加列+backfill 为**加法**先落,读写切换后再 DROP 旧表/列,避免中间态断裂。

## 1. agents 加列 + 回填(加法,迁移前半)

- [x] 1.1 写测试:Alembic 升级后 `agents` 表含 `model_overrides`/`memory_namespace`/`skills_dir` 列,且对每个 agent 其值等于原 active 版本对应字段(backfill 正确性)。先红。
- [x] 1.2 写测试(**哈希稳定硬验收**,design D4):对一组样本 agent,迁移前后 `materialize.desired_state_payload_from_agent_file(agent_file_from_store(...))` 的 `_config_hash` **相等**。先红。
- [x] 1.3 实现 Alembic 迁移上半段:`agents` ADD `model_overrides`/`memory_namespace`/`skills_dir`(默认值对齐 `agent_versions`)+ 从各 agent `active_version_id` 指向行原样回填这三列与 `system_prompt`/`allowed_tools`。跑 1.1/1.2 见绿。

## 2. agents 成单一真相源:读源切换 + 写入收口(design D1/D3)

- [x] 2.1 写测试:`agent_store.get_by_name/get_by_id` 构造的 Agent 的运行时字段全部取自 `agents` 行(不再读 `agent_versions`)。先红。
- [x] 2.2 写测试:新增统一配置写入 choke point(如 `update_agent_config`),控制台编辑(prompt/tools/model/memory/skills_dir/caps/config_overrides)经它原地写 `agents`、不建版本。先红。
- [x] 2.3 实现:`agent_store` 读源改读 `agents`;收口配置写入到单一更新函数,控制台 edit 各路径改走它。跑 2.1/2.2 见绿。
- [x] 2.4 写测试 + 实现:`materialize.agent_file_from_store`、`credential_slots` 两处 `JOIN agents a ON a.active_version_id = av.id`、`server.py:356` 控制台投影 全部改读 `agents` 自身列。见绿。

## 3. 退役配置版本化机器(迁移后半 + 端点)

- [x] 3.1 写测试:`GET /admin/agents/{name}/versions`、`POST /admin/agents/{name}/versions/{version}/activate` 返回 404/不存在;`create_version`/`activate_version`/`list_versions`/`get_version_by_id` 已移除。先红。
- [x] 3.2 实现:删除版本相关 store 函数与两个端点;`runtime/snapshot.py` 的 DB 版本加载器(`load_version`/`load_version_by_name`)按需清理(file-sourced 运行时路径保持不变)。跑 3.1 见绿。
- [x] 3.3 实现 Alembic 迁移下半段:DROP `agent_versions` 表、`agents.active_version_id` 列。重跑 1.2 哈希稳定测试仍绿。

## 4. 退役 askit / apply(spec: fleetent-apply-api)

- [x] 4.1 写测试:`POST /admin/agents/apply`、`apply:batch` 不存在;`askit_console/agent_apply_api` 已移除;server 不再接 `_apply_create`/`_apply_update` seam。先红。
- [x] 4.2 实现:删除 apply 路由、`askit_console/agent_apply_api` 模块、server 中 apply seam 接线。跑 4.1 见绿。

## 5. 移除 provenance(spec: agent-provenance / fleetent-self-managed-provenance)

- [x] 5.1 写测试:控制台 agent 投影不含 `provenance`;`stats_store` 聚合不含 provenance/source 分布;`agent_admin_state` 无 `provenance` 列。先红。
- [x] 5.2 实现:删 `set_provenance`、控制台投影字段、`stats_store.py:245` provenance 统计;Alembic DROP `agent_admin_state.provenance`。跑 5.1 见绿。

## 6. 外科移除 agent 级 drift,保 skill backflow(design D5)

- [x] 6.1 写**回归测试(护栏)**:node 上报含 `skill.drift=true` 时仍触发 `backflow_store.nominate_if_absent`、仍写 `agent_skills` 的 drift/base_version/base_commit(per-skill 链不受影响)。先确保绿(实现前它本就应绿)。
- [x] 6.2 写测试:`agent_admin_state` 无 `drift` 列;`mark_drift`/`clear_drift` 已移除;`node_desired_state_api` 不再做 `any_drift→mark/clear` 汇总。先红。
- [x] 6.3 实现:删 `agent_admin_state.drift` 列(Alembic)、`mark_drift`/`clear_drift` 函数、`node_desired_state_api.py:286-290` 汇总段、`agent_console_api.py:477` 的 mark_drift 调用。**`node_desired_state_api.py:266-285` per-skill 段一行不碰**。跑 6.2 见绿、6.1 仍绿。

## 7. MCP 挂载单一真相源(spec: agent-mcp-binding)

- [x] 7.1 写测试:materialize 的 agent MCP 集合**只**来自 `agent_mcp_servers` 关系表(不再合并任何 `mcp_server_ids` JSON 源)。先红。
- [x] 7.2 实现:`materialize._mcp_servers_for_agent` 改为只读 `agent_mcp_servers`(`mcp_server_ids` 随 `agent_versions` 已消失)。跑 7.1 见绿。

## 8. 安全保证落位(spec: agent-config-single-source)

- [x] 8.1 写测试:物化产物中 model 目标只含 `api_key_env` 变量名,无明文 key(迁移自 apply-api 的活安全保证)。先红/或确认既有等价测试覆盖。
- [x] 8.2 实现/确认:配置改住 `agents` 后,模型凭证仍只以 env 名引用、明文经 secret 注入路径下发。见绿。

## 9. 前端清理(spec: agent-admin-ui)

- [x] 9.1 写前端测试:agent 配置页无版本历史 section / 无激活控件;agent 列表无 provenance badge、无 drift badge;`useAgentVersionsQuery`/activate mutation 已移除。先红。
- [x] 9.2 实现:删 `features/agents` 的版本 UI、provenance/drift badge、版本 query/mutation 及相关类型字段。跑 9.1 见绿。

## 10. 收尾验证

- [ ] 10.1 `make test-pr` + `make test-integration-ci` 全绿(无新增失败)。
- [ ] 10.2 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过(node 侧仍不引入 DB、解耦契约不破)。
- [ ] 10.3 live 冒烟(managed 栈):迁移→起栈→现有 agent **不被批量 respawn**(对照 desired-state 哈希),控制台编辑 agent 配置即生效;node skill drift→backflow 提名链仍工作。
