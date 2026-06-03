## Context

`model_router.py` 当前把路由表硬编码为模块级常量 `ROUTES: dict[str, RouteConfig]`（行 22-38），含 `default` / `memory_extraction` 两条。`RouteConfig` 是 `frozen` dataclass，字段 `base_url` / `model` / `api_key_env` / `max_tokens` / `fallbacks`。`get_client_and_config`（同步）与 `get_async_client_and_config`（异步）均按 `task_type` 从 `ROUTES` 取配置、用 `api_key_env` 从 `os.environ` 取密钥构造 OpenAI client。

本 change **依赖 `model-parameter-config`**：该前置 change 给 `RouteConfig` 增加 `params: dict` 字段（携带 `temperature` 等模型参数）。本次外部化的 YAML 必须能写入 `params`，故必须排在其后实施——`RouteConfig` 字段以前置 change 为准，本次不改 `RouteConfig` / `RouteOverride` 字段。

项目实际配置机制是 pydantic-settings 读 `.env`（无 `settings.yaml`）；但 `webhook_router` / `server` / `cron_scheduler` / `admin` 已用 `yaml.safe_load` 加载各自的 YAML 配置文件，`pyyaml` 已是依赖。路由表属于「随部署环境而变」的配置，与 webhook 来源、cron 任务定义同类，宜走 YAML 文件而非 env 标量。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（`ROUTES_PATH` 必须可 monkeypatch 注入）；新模块结构为 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试用 `tmp_path` + `monkeypatch` 隔离，不碰真实 `config/`，LLM 调用 mock 不发真实请求。

## Goals / Non-Goals

**Goals:**
- 路由表来源从硬编码 `ROUTES` dict 改为 YAML 文件加载，运维可改无需改源码。
- 内置 `DEFAULT_ROUTES` 兜底：文件缺失 → 用内置默认（正常降级，不报错）；文件损坏 / 字段非法 → 明确报错（fail loud）。
- 密钥仅以 `api_key_env`（环境变量名）出现在 YAML，api key 本身绝不落盘。
- `ROUTES_PATH` 为可 monkeypatch 注入的模块级常量。
- `get_client_and_config` / `get_async_client_and_config` 对外签名与行为不变。
- 零新增依赖（复用已有 `pyyaml`）。

**Non-Goals:**
- 不做热加载（运行时改文件不自动生效；标注为 Non-Goal）。
- 不把 api key 本身放进文件（仅 env 变量名）。
- 不改 `RouteConfig` / `RouteOverride` 字段（`params` 字段由前置 change `model-parameter-config` 提供）。
- 不引入新依赖（不引 settings.yaml 机制、不引新 YAML 库）。
- 不改 model fallback 解析、密钥 env 解析、OpenAI client 构造方式。

## Decisions

### D1：从 YAML 文件加载 routes（复用 pyyaml，零新依赖）
新增 `_load_routes() -> dict[str, RouteConfig]`：读 `ROUTES_PATH` 指向的 YAML（`yaml.safe_load`，同 `webhook_router` 第 28 行），将每个顶层 key 映射为一个 route，value 含 `base_url` / `model` / `api_key_env` / `max_tokens` / `fallbacks` / `params`，构造为 `RouteConfig`。`get_client_and_config` / `get_async_client_and_config` 改为调用 `_load_routes()` 取表后按 `task_type` 查找（`.get(task_type, routes["default"])`，沿用现状回落语义）。
**为何**：路由是部署级配置；`pyyaml` 已是依赖，与 webhook / cron 配置文件同构，零新依赖。
**Alternatives**：①每条 route 拆成一组 env 标量（如 `ROUTE_DEFAULT_MODEL`）——被否，多条 route × 多字段会使 env 爆炸且 `fallbacks` / `params` 这类结构化值难表达；②引入 settings.yaml 全量配置机制——被否，项目无此机制、超出本 change 范围。

### D2：密钥仍走 env，YAML 只写 `api_key_env`
YAML 中每条 route 写 `api_key_env: ANTHROPIC_API_KEY`（环境变量名），**不写** api key 本身。密钥解析路径不变：仍由 `get_(async_)client_and_config` 用 `os.environ.get(route.api_key_env)` 取值（同步路径缺失则 `raise RuntimeError`，沿用现状）。
**为何**：数据主权与密钥卫生——配置文件可能进版本库 / 备份 / 日志，密钥绝不能落盘。`RouteConfig.api_key_env` 字段本就为此设计。
**Alternatives**：在 YAML 内联 `api_key`——被否，违反密钥卫生，与项目「数据不出内网、密钥不落盘」原则冲突。

### D3：内置 `DEFAULT_ROUTES` 兜底 + 缺失降级 / 损坏报错
- 保留现有 `default` / `memory_extraction` 两条为模块级内置 `DEFAULT_ROUTES: dict[str, RouteConfig]`（即现状 `ROUTES` 的内容）。
- 文件**缺失**（`ROUTES_PATH` 不存在）→ 返回 `DEFAULT_ROUTES`，**视为正常**，不报错（开箱即用）。
- 文件**存在但损坏**（YAML 解析失败 / 顶层非 mapping）或**字段非法**（缺必填字段、类型错误）→ **明确报错（fail loud）**，不静默回落默认（避免误配置被默认掩盖、跑到错误的模型 / 端点）。
- 文件存在且合法 → 以文件内容**覆盖 / 合并**内置默认（文件中定义的 key 覆盖同名内置 key，文件未提供的内置 key 保留）。
**为何**：缺失是合法状态（客户用默认即可）；存在即意味着运维有意配置，损坏 / 非法属误配置，必须立刻暴露而非悄悄跑默认。
**Alternatives**：①缺失也报错强制要求文件——被否，破坏开箱即用；②损坏静默回落默认——被否，掩盖误配置、production 静默跑错模型风险高。

### D4：`ROUTES_PATH` 为可注入的模块级常量，不做热加载
- 模块级 `ROUTES_PATH: Path`（默认指向 `config/routes.yaml`），测试 `monkeypatch.setattr(model_router, "ROUTES_PATH", tmp_path / "routes.yaml")` 隔离，绝不触碰真实 `config/`。
- 加载发生在启动 / 首次取用时，**不监听文件变更、不热加载**（Non-Goal）；改配置需重启进程生效。
**为何**：CLAUDE.md 禁全局可变状态，路径必须可 monkeypatch；热加载引入文件监听 / 缓存失效复杂度，不在本次价值范围。
**Alternatives**：把路径写死为不可注入常量——被否，违反测试隔离与「禁全局可变状态」；做热加载——被否，超范围、增复杂度。

### D5：`get_(async_)client_and_config` 对外签名与行为不变
两函数签名（`task_type: str = "default"`）、返回类型（`tuple[OpenAI|AsyncOpenAI, RouteConfig]`）、`task_type` 未命中回落 `default`、`api_key_env` 经 env 解析、同步路径缺 key 抛 `RuntimeError`——**全部不变**。唯一变化：内部路由表来源从模块常量 `ROUTES` 改为 `_load_routes()` 返回值。
**为何**：外部化是实现细节，调用方（agent_loop / memory_layer 等）不应感知；最小化爆炸半径。
**Alternatives**：改签名让调用方传入路由表——被否，污染所有调用点，违背「对外行为不变」。

## Risks / Trade-offs

- [每次取用都读盘解析 YAML 的开销] → 路由表小、取用频率有限；如成热点可在不破坏「无全局可变状态」前提下加可注入缓存，本次先求正确，标注为后续优化点。
- [文件存在但仅定义部分 route，遗漏内置 key] → D3 采用「合并」语义，文件未提供的内置 key 保留，避免运维只想加一条 route 却丢掉默认。
- [损坏报错可能在启动 / 首次取用才暴露] → 不做热加载，错误在首次取用即抛出且信息明确（指出文件路径与失败字段），便于运维定位。
- [依赖前置 change 的 `params` 字段未就位] → 实施前确认 `model-parameter-config` 已合入、`RouteConfig` 含 `params`；本 change 不自行新增该字段。

## Open Questions

- `config/routes.yaml` 的最终默认路径与是否在仓库提供 `routes.yaml.example` 示例——实现时与运维约定（默认 `config/routes.yaml`，gitignored）。
- `_load_routes()` 是否需要可注入缓存以避免每次读盘——本次先无缓存求正确，性能评估后再定（须保持可 monkeypatch、无全局可变状态）。
