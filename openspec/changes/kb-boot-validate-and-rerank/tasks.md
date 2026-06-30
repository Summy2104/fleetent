## 边界（先读）
只动 `knowledge_base/service_config.py`、`kb-service.yaml.example`。
**严禁碰**(D1 地盘）：`serve.py`、`worker.py`、`operations.py`、`kb_ingest_jobs.py`、`standalone_sweep.py`。

## 1. boot 校验覆盖颗粒 *_env（TDD）

- [ ] 1.1 测试先行：连接器用颗粒 `*_env`(如 `access_token_env`)且该 env 未设 → `validate_kb_service_boot` 启动即失败并指出缺项;设了则通过。见红
- [ ] 1.2 实现：`service_config.py` 的 `validate_kb_service_boot` 扩展——遍历每个连接器实际声明的颗粒 `*_env` 字段(access_token_env/refresh_token_env/client_id_env/client_secret_env/token_uri_env/username_env/api_token_env),校验所指 env/file 存在,与既有 `credential_ref`/`api_key_env` 校验并列。见绿

## 2. rerank 配置段 + 接入 provider（TDD）

- [ ] 2.1 测试先行：`KBServiceConfig` 含可选 `rerank` 段(`KBRerankSection`: backend/endpoint/model/api_key_env,默认 backend=disabled);解析正确。见红
- [ ] 2.2 实现：`service_config.py` 加 `KBRerankSection` + `KBServiceConfig.rerank`
- [ ] 2.3 测试先行：`backend != disabled` 时,`configure_process_runtime` 把 rerank 配置接入进程 `RerankSettings`(disabled 时不配，检索不重排）。见红
- [ ] 2.4 实现：`configure_process_runtime` 据 rerank 段配置 standalone 进程的 rerank provider
- [ ] 2.5 boot 校验:rerank 启用且配了 `api_key_env` 时纳入 §1 的缺失校验

## 3. example 预置 rerank（默认禁用）

- [ ] 3.1 `kb-service.yaml.example` 加 `rerank` 段:`backend: disabled`、endpoint 注释指向 `http://127.0.0.1:7997/rerank`(Infinity)、model 占位;更新相关断言测试

## 4. 收尾门禁

- [ ] 4.1 `openspec validate kb-boot-validate-and-rerank --strict`
- [ ] 4.2 `make test-pr` + `make test-integration-ci` 全绿
- [ ] 4.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（未碰 platform）
- [ ] 4.4 `git diff --name-only main` 自查：只出现 service_config.py / kb-service.yaml.example（+ 本 change spec）—— 不出现 D1 的文件
- [ ] 4.5 功能分支 `openspec archive kb-boot-validate-and-rerank`（同步 kb-standalone-ingest spec）
- [ ] 4.6 所有 checkbox 标 `[x]`
