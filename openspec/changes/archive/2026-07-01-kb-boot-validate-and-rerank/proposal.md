## Why

两个 KB 配置缺口:

1. **boot 校验对颗粒 `*_env` 形同虚设**:`validate_kb_service_boot` 只校验连接器的 `credential_ref` + embedding/extraction 的 `api_key_env`,**不校验**连接器声明的颗粒字段(`access_token_env`/`refresh_token_env`/`client_id_env`/`client_secret_env`/`token_uri_env`/`username_env`/`api_token_env`)。而 example 连接器恰恰用颗粒 `*_env`(非 credential_ref)→ 缺凭据**不在 boot 报错,延迟到运行时 sync 才炸**,正是 spec 要避免的(spec drift)。
2. **rerank 无 provider 可用**:C(`kb-http-quality-passthrough`)让 agent 能请求 rerank、kb-serve 能透传,但 **kb-serve 进程没有配置 rerank provider**(`RerankSettings.backend` 默认 `disabled`)→ 即便请求 rerank 也不会真重排。需要把 rerank 端点配进 kb-service 并接入进程的 rerank provider。

## What Changes

- **#2 boot 校验覆盖颗粒 `*_env`**:扩展 `validate_kb_service_boot`——对每个连接器,校验它实际声明的颗粒 `*_env` 字段所指 env 存在(在 `credential_ref` 之外);任一缺失则启动即失败并指出缺项。修 spec drift。
- **#3 rerank 接 Infinity**:
  - `kb-service.yaml` 增 `rerank` 段(`backend` / `endpoint` / `model` / `api_key_env`);`KBServiceConfig` 加 `KBRerankSection`。
  - `configure_process_runtime`(service_config.py)把该 rerank 配置接入进程的 rerank provider(`RerankSettings`),使 kb-serve 在 agent 请求 rerank 时真有 provider 可用。
  - `kb-service.yaml.example` **预置 rerank 段但默认 `backend: disabled`**,endpoint 注释指向 Infinity 的 `http://127.0.0.1:7997/rerank`——运维填端点 + 改 backend 即生效(**默认关,避免没起 Infinity 时炸**)。

## 边界(与并行的 D1 `kb-ops-status-and-sweep` 划清)

只动:`knowledge_base/service_config.py`(boot 校验 + rerank section + configure_process_runtime 接线)、`kb-service.yaml.example`。
**严禁碰**(D1 的地盘):`serve.py`、`worker.py`、`operations.py`、`kb_ingest_jobs.py`、`standalone_sweep.py`。两包代码文件完全不相交。
(注:本包与 D1 都 MODIFY `kb-standalone-ingest` spec,但**不同 requirement**——本包 = Boot validation;D1 = sweep——archive 时按 requirement 合,不冲突。)

## Capabilities

### Modified Capabilities
- `kb-standalone-ingest`:boot 校验覆盖连接器颗粒 `*_env`(缺则启动即失败);新增 standalone rerank 配置段 + 接入进程 rerank provider(默认禁用、example 指向 Infinity)。

## Impact

- **owning area**:`knowledge_base/service_config.py`(boot 校验 + KBRerankSection + configure_process_runtime)、`kb-service.yaml.example`。**不碰 platform、不碰 D1 文件、不碰 serve.py**。
- **public surface**:`kb-service.yaml` 增可选 `rerank` 段(默认 disabled,向后兼容);boot 校验更严(缺颗粒 `*_env` 从运行时报错提前到启动报错)。
- **owned tables / 迁移**:无。
- **行为变更**:连接器缺颗粒凭据 → **启动即失败**(原为运行时);rerank 配好端点+开启后,kb-serve 在 agent 请求 rerank 时真重排。
- **cross-module / 解耦**:不新增依赖;不碰 platform。
- **依赖**:rerank 端到端 = C(透传)+ 本包(provider 配置)+ 运维起 Infinity;本包只负责"provider 可配可用",是否启用由配置定。
- **测试**:boot 校验缺颗粒 `*_env` 失败的单测;rerank section 解析 + 接入 provider 的单测;`make test-pr` + `make test-integration-ci` 全绿。
