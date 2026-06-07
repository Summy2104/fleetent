## 1. 共享密钥作用域（store + 迁移）

- [x] 1.1 Write failing tests: secret store 支持 shared 作用域（`agent_id` NULL / `scope=shared`）；shared 与 per-agent 同名槽并存且唯一约束不冲突；`get_decrypted` 解析顺序 agent 优先回退 shared；materialize resolver 能解出 shared 槽值（tests/integration，真实 DB + Alembic）
- [x] 1.2 Implement: Alembic 迁移放宽 `agent_secrets.agent_id` 非空 + 调唯一索引（`coalesce`）；store set/get/status/delete 接受可选 owner 维度（named params，统一 store 边界）
- [x] 1.3 Verify green: `uv run pytest tests/integration/test_agent_secret_store.py -x -q`

## 2. 自动 env 名派生（来源实体稳定派生）

- [x] 2.1 Write failing tests: provider 输值派生 `FLEETENT_MODEL_<ID>_API_KEY`、KB token 派生 `FLEETENT_KB_<ID>_<SLOT>`（大写、`-`→`_`）；派生名写回实体 `*_env`；撞名 fail loud（tests/integration）
- [x] 2.2 Implement: 派生函数（复用现有 `_env_var_names`/派生规则）+ 实体 `*_env` 回填 + 撞名校验
- [x] 2.3 Verify green: 跑派生测试

## 3. 凭据 API 接受 inline 值 + 回填引用

- [x] 3.1 Write failing tests: value 模式 PUT 经凭据 API 加密存（shared 作用域）+ 派生名写回 provider.api_key_env / connector.<key>_env，响应不回显值；reference 模式只设 `*_env` 不存值；DELETE 清值 + 状态回 unset（tests/integration，FastAPI TestClient）
- [x] 3.2 Implement: 凭据 API / provider+connector 写路径接受 inline 值（走 secret store 而非明文塞 provider body）；核查 provider runtime 读 key 路径仍经 `*_env` resolver（必要时兼容垫片）
- [x] 3.3 Verify green: `uv run pytest tests/integration/test_agent_secret_api.py tests/integration/test_agent_admin_api.py -x -q`

## 4. CredentialField 控件（前端，value-first + 高级引用）

- [x] 4.1 Write failing tests: admin.html UI-marker 断言——`cred-field` 控件含 value(password)/reference(text) 两态、`data-mode`、set/unset chip、「⚙ 引用现有变量」高级 toggle；value 默认态；编辑态不回显已存值（tests/integration/test_admin_console_ui.py）
- [x] 4.2 Implement: 可复用 CredentialField 渲染 + 状态机（value↔reference）+ 调凭据 API 存值/设名/清除
- [x] 4.3 Verify green: `uv run pytest tests/integration/test_admin_console_ui.py -x -q` + `node --check` 内联 JS

## 5. Provider 表单合并到 CredentialField

- [x] 5.1 Write failing tests: Provider 表单只剩一个密钥控件（`pv-api-key-env` 独立框已移除）；value 模式存值 + 回填 api_key_env、不塞明文；reference 模式只设 api_key_env；编辑留空不改（tests/integration UI marker + provider save 路径）
- [x] 5.2 Implement: 删 `pv-api-key-env` 框，`pv-api-key` 升级为 CredentialField；改 prSave/body 组装
- [x] 5.3 Verify green: `uv run pytest tests/integration/test_admin_console_ui.py -x -q`

## 6. KB connector token 字段挂 CredentialField

- [ ] 6.1 Write failing tests: KBC google_drive/confluence 的 token 类字段渲染为 CredentialField（value 默认 + 引用高级），非密钥字段（folder_id/base_url 等）不变（tests/integration UI marker）
- [ ] 6.2 Implement: `KBC_FIELDS` 标记密钥字段 + `kbcRenderFields` 对密钥字段用 CredentialField；保存走 secret store + 回填 `*_env`
- [ ] 6.3 Verify green: 跑 UI 测试 + `node --check`

## 7. 「所需密钥」面板降级为只读总览

- [ ] 7.1 Write failing tests: `ag-secrets` 面板不再含 operator/inject 单选与 inject password/保存/清除控件；渲染 env/source/status 只读行；保留复制模板 + 校验缺失；source 提示指向来源字段（tests/integration/test_admin_console_ui.py）
- [ ] 7.2 Implement: 重写 `agSecretSlotHtml` 为只读行；删 `agToggleSecretInput`/`agSetSecret`/`agClearSecret` 的面板入口（写操作移到 CredentialField）
- [ ] 7.3 Verify green: `uv run pytest tests/integration/test_admin_console_ui.py -x -q` + `node --check`

## 8. 质量门 + 浏览器冒烟

- [ ] 8.1 收尾：`uv run ruff format src tests && uv run ruff check src tests`、`uv run mypy src`、`uv run python scripts/check_test_layers.py`、`uv run python scripts/check_module_boundaries.py`
- [ ] 8.2 全量：`uv run pytest -x -q`
- [ ] 8.3 浏览器冒烟（chrome-devtools，本地 8765，admin/admin12345，进程设 `FLEETENT_SECRET_KEY`）：Provider 输值→自动 env 名→agent 面板只读总览显 set；KB token 输值同验；切高级引用→面板显 operator/unset；按 [always-self-test-after-change] 走完整流程再报完成
