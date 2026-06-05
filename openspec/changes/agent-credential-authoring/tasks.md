## 1. 导出层补齐（model/mcp/bindings/knowledge/tenant/team/skills_dir）

- [x] 1.1 Write failing tests: `agent_file_from_store` 回填 `tenant_id`/`team_id`/`skills_dir`；有 model_overrides 时展开真实 `models.targets/routes`（target `api_key_env` 复用 provider 级、无 localhost 占位）、无覆盖时回退 `default_models()`；`mcp_server_ids`→`mcp_servers`、`channel_agents`/`user_agents`→`bindings`、`agent_kbs`→`knowledge.bindings`（tests/integration，DB fixture 隔离）
- [x] 1.2 Implement: 扩展 `agent_file_from_store` 与 provider 展开逻辑；接入 mcp/bindings/knowledge 查询；`_build_agent_yaml` 改为单一委托（console 预览 == 部署 home）
- [x] 1.3 Verify green: `uv run pytest tests/integration/test_agent_export_from_store.py -x -q`（含 agent_admin/lifecycle 回归）

## 2. 加密 secret store

- [x] 2.1 Write failing tests: `set` 后库里是密文非明文；`get_decrypted` 还原；`status` 只回 set/unset；缺/坏 `FLEETENT_SECRET_KEY` 时 inject 读写 fail loud；空值写入被拒（tests/integration，真实 DB + Alembic）
- [x] 2.2 Implement: `agent_secrets` 表 + Alembic 迁移（named params、统一 store 边界）；对称 AEAD 加解密，主密钥读 `FLEETENT_SECRET_KEY`；store API set/get_decrypted/status/delete
- [x] 2.3 Verify green: `uv run pytest tests/integration/test_agent_secret_store.py -x -q`

## 3. 密钥槽元数据（env_name + mode）

- [x] 3.1 Write failing tests: 新槽默认 `operator`；env 名派生 `FLEETENT_AGENT_<NAME>_<SLOT>`；改名不静默变 env 名；撞名 fail loud；mode/value 不进生成的 agent.yaml（tests/integration）
- [x] 3.2 Implement: 槽元数据持久化（复用 `agent_versions` JSON 列，key 前缀隔离）；env 名派生 + 撞名校验
- [x] 3.3 Verify green: 跑新增槽元数据测试

## 4. write-only 凭据 API + required-env

- [x] 4.1 Write failing tests: `PUT secret` 不回显值、响应只含 env_name+status；`GET secrets` 不含明文；空值 `PUT` 被拒；`DELETE` 清值；`GET required-env` 按当前定义列出 `*_env`+来源标签+mode+status，新增 MCP 后即时反映，无 `*_env` 的段不误报（tests/integration，FastAPI TestClient）
- [x] 4.2 Implement: 凭据路由（PUT/DELETE/GET secrets、GET required-env，复用 `_env_var_names`）；写/删审计不记值
- [x] 4.3 Verify green: `uv run pytest tests/integration/test_agent_secret_api.py -x -q`

## 5. materialize resolver（按 mode 写 .env）

- [ ] 5.1 Write failing tests: inject 槽写解密真值；operator 槽保留运维已填值、否则写 `NAME=`；inject 标记 set 但解密失败 fail loud；任意 mode 下 agent.yaml 不含明文（tests/integration）
- [ ] 5.2 Implement: `_seed_env` 接入 secret resolver；materialize 记 required/ inject/operator 计数（不记值）
- [ ] 5.3 Verify green: 跑 materialize resolver 测试

## 6. console CredentialField 控件 + 「所需密钥」面板

- [ ] 6.1 Write failing tests: admin.html UI-marker 断言——CredentialField 控件（来源单选、inject password + set/unset chip、高级 env 名）、所需密钥面板（required 列表 + 复制 .env 模板 + 校验缺失）、模型密钥复用 provider 不重复输入（tests/integration/test_admin_console_ui.py）
- [ ] 6.2 Implement: admin.html 控件 + 面板 + 调 凭据/required-env API
- [ ] 6.3 Verify green: `uv run pytest tests/integration/test_admin_console_ui.py -x -q` + `node --check` 内联 JS

## 7. `.env.example` 拆分为进程级模板

- [ ] 7.1 Write failing tests: `config/agent/.env.example` 含 `FLEETENT_SECRET_KEY`、不含 agent 级 model/Slack/MCP/KB `*_env`、所有条目为 `NAME=` 无值（tests/integration 解析断言）
- [ ] 7.2 Implement: 拆分模板，新增 `FLEETENT_SECRET_KEY`，删除 agent 引用密钥；更新 `agent.yaml.example` 注释指向生成路径
- [ ] 7.3 Verify green: 跑模板解析测试

## 8. Quality gates

- [ ] 8.1 Run `uv run pytest -x -q`
- [ ] 8.2 Run `uv run ruff format src tests`
- [ ] 8.3 Run `uv run ruff check src tests`
- [ ] 8.4 Run `uv run mypy src`
- [ ] 8.5 Run `uv run python scripts/check_test_layers.py`
- [ ] 8.6 Run `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
