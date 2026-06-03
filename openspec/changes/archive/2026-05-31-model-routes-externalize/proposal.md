## Why

`model_router.py` 的 `ROUTES` 是硬编码在源码里的 `dict[str, RouteConfig]`（当前仅 `default` / `memory_extraction` 两条）。on-premises 客户要把模型路由切到自托管 vLLM、私有 OpenAI-compatible 网关或更换模型/`max_tokens`，必须改源码、重新打包部署——这与「面向企业部署、配置随环境而非随代码」的定位相悖。路由是部署级配置，应当外部化为运维可改的文件，而非硬编码常量。

本 change 把路由表外部化为 YAML 配置文件，同时保留内置默认作为兜底，密钥继续走环境变量、绝不落盘。

## What Changes

- 将 `model_router.ROUTES` 的来源从**硬编码 dict** 改为**从 YAML 文件加载**（如 `config/routes.yaml`）；每条 route 含 `base_url` / `model` / `api_key_env` / `max_tokens` / `fallbacks` / `params`。
- 内置 `DEFAULT_ROUTES`（即现有硬编码的 `default` / `memory_extraction`）作为**兜底默认**：配置文件缺失时使用内置默认、不报错；文件存在但损坏或字段非法时**明确报错（fail loud）**，不静默掩盖误配置。
- 配置文件路径为**模块级常量 `ROUTES_PATH`，可 monkeypatch 注入**（不引入全局可变状态）；加载在启动 / 首次取用时进行，**不做热加载**。
- 密钥**仍走环境变量**：YAML 只写 `api_key_env`（环境变量名），**绝不写 api key 本身**，维持数据主权与密钥卫生。
- `get_client_and_config` / `get_async_client_and_config` 的**对外签名与行为不变**（仍按 `task_type` 查路由），仅路由来源从硬编码改为「YAML 覆盖 / 合并内置默认」。

## Capabilities

### New Capabilities
- `model-routes-externalize`: 模型路由表的外部化配置——从 YAML 文件加载 routes、内置默认兜底、文件缺失正常降级 / 损坏明确报错、密钥仅以 env 变量名引用；`get_(async_)client_and_config` 对外行为不变。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。get_(async_)client_and_config 对外签名/行为不变；路由来源的外部化收口在新 capability model-routes-externalize 内。 -->

## Impact

- **依赖**：本 change **依赖 `model-parameter-config`** ——`RouteConfig` 须已含 `params: dict` 字段，YAML 才能携带 `params`。必须排在 `model-parameter-config` 之后实施。
- **代码**：
  - 修改 `src/fleetent/model_router.py`：新增模块级 `ROUTES_PATH` 常量、内置 `DEFAULT_ROUTES`、`_load_routes()`（读 YAML、校验、合并内置默认）；`get_client_and_config` / `get_async_client_and_config` 改为经 `_load_routes()` 取路由表，签名与对外行为不变。
- **配置**：新增可选的 `config/routes.yaml`（运维维护，gitignored，仓库可提供示例）；缺失时走内置默认。
- **测试**：`tests/test_model_router.py` 用 `tmp_path` 写临时 YAML + `monkeypatch ROUTES_PATH` 隔离，不碰真实 `config/`；覆盖缺失降级、损坏报错、字段非法报错、覆盖 / 合并内置默认、`api_key_env` 经 env 解析。
- **不引入新依赖**：`pyyaml` 已是项目依赖（`webhook_router` 等已用 `yaml.safe_load`），零新增。
- **不影响**：model fallback 解析、`RouteConfig` / `RouteOverride` 字段（`params` 由前置 change 提供）、密钥的 env 解析路径。
