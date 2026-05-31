## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 确认前置 change `model-parameter-config` 已合入、`RouteConfig` 已含 `params` 字段；本 change 不自行新增该字段
- [ ] 1.2 核实 `pyyaml` 已是依赖（`pyproject.toml` 已列 `pyyaml` / `types-pyyaml`），加载沿用 `webhook_router` 的 `yaml.safe_load` 模式，零新依赖
- [ ] 1.3 核对 `get_client_and_config` / `get_async_client_and_config` 现状签名与 `task_type` 未命中回落 `default`、同步路径缺 key 抛 `RuntimeError` 的语义，明确本次仅改路由来源、对外行为不变

## 2. 内置默认与可注入路径

- [ ] 2.1 Write failing tests：`model_router` 暴露模块级 `DEFAULT_ROUTES`（含 `default` / `memory_extraction`）与可 monkeypatch 的 `ROUTES_PATH` 常量。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：将现有硬编码 `ROUTES` 内容提为模块级 `DEFAULT_ROUTES: dict[str, RouteConfig]`，新增 `ROUTES_PATH: Path`（默认 `config/routes.yaml`）。看到绿

## 3. 加载与合并：_load_routes()

- [ ] 3.1 Write failing tests（`tmp_path` 写临时 YAML + `monkeypatch ROUTES_PATH`，不碰真实 `config/`）：`_load_routes()` 在文件合法时返回含文件定义 route 的表，字段值与 YAML 一致（含 `fallbacks` / `params`）。看到红
- [ ] 3.2 Implement `_load_routes() -> dict[str, RouteConfig]`：`yaml.safe_load` 读 `ROUTES_PATH`，将每个顶层 key 构造为 `RouteConfig`。看到绿

## 4. 文件缺失降级与合并内置默认

- [ ] 4.1 Write failing tests：`ROUTES_PATH` 不存在时 `_load_routes()` 返回内置 `DEFAULT_ROUTES` 且不报错；文件只定义部分 route 时，文件 key 覆盖同名内置 key、未提供的内置 key 保留。看到红
- [ ] 4.2 Implement：文件不存在 → 返回 `DEFAULT_ROUTES`；文件合法 → 以内置默认为基础合并文件内容。看到绿

## 5. 损坏 / 字段非法明确报错（fail loud）

- [ ] 5.1 Write failing tests：YAML 损坏 / 顶层非 mapping → 抛错且信息指向该文件；某 route 缺必填字段 / 类型非法 → 抛错并指明问题 route；两种情形均**不**回落内置默认。看到红
- [ ] 5.2 Implement：解析失败 / 顶层非 mapping / 字段校验失败均 `raise`（明确异常 + 文件路径 + 问题 route），不静默回落。看到绿

## 6. 密钥仅以 api_key_env 引用

- [ ] 6.1 Write failing tests（LLM 调用 mock，不发真实请求）：route 的 `api_key_env` 指向已设置的 env 时，`get_client_and_config` 用该 env 值构造 client 且 `RouteConfig` 不含明文 key；env 缺失时同步路径抛 `RuntimeError` 指明变量名。看到红
- [ ] 6.2 Implement：保持 `os.environ.get(route.api_key_env)` 解析路径不变，确认 YAML 不接受内联 api key。看到绿

## 7. get_(async_)client_and_config 接入外部化（对外行为不变）

- [ ] 7.1 Write failing tests：`get_client_and_config` / `get_async_client_and_config` 改经 `_load_routes()` 取表后按 `task_type` 查找；默认 `task_type` 与未命中回落 `default` 行为与现状一致（用 `monkeypatch ROUTES_PATH` 指向临时 YAML 验证文件 route 生效）。看到红
- [ ] 7.2 Implement：两函数内部路由来源由模块常量改为 `_load_routes()` 返回值，签名 / 返回类型 / 回落语义不变。看到绿

## 8. 不热加载守卫

- [ ] 8.1 Write failing tests：标注 / 验证 `ROUTES_PATH` 是模块级可注入常量，加载不监听文件变更（不实现热加载）。看到红
- [ ] 8.2 Implement / 确认：无文件监听逻辑，运行中改文件不自动生效。看到绿

## 9. 收尾

- [ ] 9.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 9.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 未新增 mypy 错误模式
- [ ] 9.3 确认测试全程仅用 `tmp_path` + `monkeypatch ROUTES_PATH`，未触碰真实 `config/`；LLM 调用全程 mock，无真实 API 请求
