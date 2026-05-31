## ADDED Requirements

### Requirement: 从 YAML 文件加载路由表

`model_router` SHALL 从 `ROUTES_PATH` 指向的 YAML 文件加载模型路由表，每个顶层 key 为一个 `task_type`，其 value 提供 `base_url` / `model` / `api_key_env` / `max_tokens` / `fallbacks` / `params` 字段并构造为 `RouteConfig`。路由表的来源 MUST 从硬编码常量改为该文件加载结果。

#### Scenario: 合法文件提供的路由被加载
- **WHEN** `ROUTES_PATH` 指向一个合法 YAML，其中定义了某 `task_type` 的完整路由字段
- **THEN** `get_client_and_config` / `get_async_client_and_config` 在该 `task_type` 下返回的 `RouteConfig` 字段值与文件一致

#### Scenario: task_type 未命中时回落 default
- **WHEN** 请求一个文件与内置默认均未定义的 `task_type`
- **THEN** 返回 `default` 路由，行为与现状一致

### Requirement: 内置默认兜底与文件缺失降级

`model_router` SHALL 内置 `DEFAULT_ROUTES`（含现有 `default` / `memory_extraction` 两条）作为兜底。当 `ROUTES_PATH` 指向的文件不存在时，加载 MUST 返回内置默认且视为正常，不得报错。

#### Scenario: 文件缺失时使用内置默认
- **WHEN** `ROUTES_PATH` 指向的文件不存在
- **THEN** 路由表为内置 `DEFAULT_ROUTES`，加载不报错，`default` / `memory_extraction` 可正常取用

#### Scenario: 文件部分定义时合并内置默认
- **WHEN** 文件只定义了部分 route，未覆盖某个内置 key
- **THEN** 文件定义的 key 覆盖同名内置 key，文件未提供的内置 key 仍保留可用

### Requirement: 文件损坏或字段非法时明确报错

当 `ROUTES_PATH` 指向的文件存在但 YAML 损坏、顶层不是 mapping、或某条 route 缺必填字段 / 字段类型非法时，加载 MUST 明确报错（fail loud），不得静默回落到内置默认。

#### Scenario: 文件损坏时报错
- **WHEN** 文件存在但 YAML 无法解析或顶层不是 mapping
- **THEN** 加载抛出错误，错误信息指向该文件，不静默使用内置默认

#### Scenario: 字段非法时报错
- **WHEN** 文件中某条 route 缺少必填字段或字段类型非法
- **THEN** 加载抛出错误并指明问题 route，不静默使用内置默认

### Requirement: 密钥仅以环境变量名引用

路由 YAML MUST 仅以 `api_key_env`（环境变量名）引用密钥，绝不内联 api key 本身。密钥解析 SHALL 仍由 `get_(async_)client_and_config` 在运行时用 `api_key_env` 从环境变量读取，解析路径与现状一致。

#### Scenario: 经 api_key_env 从环境变量解析密钥
- **WHEN** 某 route 的 `api_key_env` 指向一个已设置的环境变量
- **THEN** `get_client_and_config` 用该环境变量的值构造 client，且 `RouteConfig` 中不含 api key 明文

#### Scenario: 同步路径缺失密钥时报错
- **WHEN** `get_client_and_config` 所需的 `api_key_env` 环境变量未设置
- **THEN** 抛出 `RuntimeError` 指明缺失的环境变量名，行为与现状一致

### Requirement: 路由文件路径可注入且不热加载

路由文件路径 SHALL 是模块级常量 `ROUTES_PATH`，可经 `monkeypatch` 注入以隔离测试，不得引入全局可变状态。加载 MUST 在启动 / 首次取用时进行，不监听文件变更、不热加载。

#### Scenario: 注入路径以隔离测试
- **WHEN** 测试 `monkeypatch.setattr(model_router, "ROUTES_PATH", tmp_path / "routes.yaml")`
- **THEN** 加载读取该临时文件，不触碰真实 `config/` 目录

#### Scenario: 运行中改文件不自动生效
- **WHEN** 进程运行期间修改了路由文件内容
- **THEN** 已加载的路由表不因此自动更新，变更需重启进程才生效

### Requirement: get_client_and_config 对外行为不变

`get_client_and_config` 与 `get_async_client_and_config` 的对外签名（`task_type: str = "default"`）、返回类型与按 `task_type` 查路由的行为 MUST 保持不变，唯一变化是路由表来源由硬编码常量改为 YAML 加载结果。

#### Scenario: 默认 task_type 行为不变
- **WHEN** 不传 `task_type` 调用 `get_async_client_and_config`
- **THEN** 返回 `default` 路由对应的 client 与 `RouteConfig`，调用方无需感知路由来源的变化
