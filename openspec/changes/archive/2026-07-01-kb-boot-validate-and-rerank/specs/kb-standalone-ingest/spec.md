## MODIFIED Requirements

### Requirement: Boot validation of config and credentials

KB 服务启动 SHALL 校验配置完整性:所有连接器引用的凭据 env/file SHALL 存在——既包括 `credential_ref`,也包括连接器实际声明的**颗粒凭据字段**(`access_token_env` / `refresh_token_env` / `client_id_env` / `client_secret_env` / `token_uri_env` / `username_env` / `api_token_env` 等);以及 embedding / extraction 配置的 `api_key_env`(若设置)、rerank 配置的 `api_key_env`(若启用且设置)所指向的 env/file SHALL 存在;embedding endpoint SHALL 配置。任一缺失 SHALL 启动即失败并指出缺项(不延迟到运行时才炸)。

#### Scenario: 缺凭据启动失败
- **WHEN** 某连接器的 `credential_ref` **或其声明的任一颗粒 `*_env`**,或 embedding / extraction / 启用的 rerank 的 `api_key_env` 所指 env/file 不存在
- **THEN** 服务启动失败并报出缺失的引用

#### Scenario: 颗粒 *_env 缺失被 boot 捕获
- **WHEN** 连接器用颗粒 `*_env`(如 `access_token_env`)而非 `credential_ref`,且该 env 未设置
- **THEN** 启动即失败(不延迟到运行时 sync 才报错)

#### Scenario: 配置齐全启动成功
- **WHEN** 所有引用就位、embedding 已配
- **THEN** 服务正常启动

## ADDED Requirements

### Requirement: Standalone rerank 配置

`kb-service.yaml` MAY 含 `rerank` 段(`backend` / `endpoint` / `model` / `api_key_env`);当 `backend` 非 `disabled` 时,KB 服务进程 SHALL 据此配置 rerank provider,使检索在请求 rerank 时(见 `kb-read-service` 透传)真正经该 provider 重排。默认 `backend: disabled`(未配 rerank 服务时不影响启动与检索)。仓库 example SHALL 预置该段但默认禁用,endpoint 指向自托管 rerank 服务(如 Infinity)的约定地址,运维填端点并启用即生效。

#### Scenario: rerank 默认禁用不影响运行
- **WHEN** `kb-service.yaml` 未配 rerank 或 `backend: disabled`
- **THEN** 服务正常启动与检索,检索不重排(与扩展前一致)

#### Scenario: 启用 rerank 后真重排
- **WHEN** `rerank.backend: http` + 有效 endpoint,且检索请求带 `rerank=true`
- **THEN** 进程的 rerank provider 经该 endpoint 对候选重排
