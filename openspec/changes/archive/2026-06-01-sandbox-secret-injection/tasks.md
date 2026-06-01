## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `SandboxClient.create_workspace`（sandbox_client.py 行 27-38）当前不带任何 `-e`（干净环境），确认增加 env 注入不影响现状默认行为
- [x] 1.2 核实宿主机敏感变量来源（`config.Settings.anthropic_api_key` 等经 `os.environ` 的 `ANTHROPIC_API_KEY` 等），确认名称含 `KEY` 会被过滤规则命中
- [x] 1.3 核实 agent 注入变量承载位 = SB3 的 `features.sandbox_env`（SB3 owner，已定调），且经 SB3 的 run_code 上下文通道取 `agent_env`；确认 SB3 的 features 列与上下文通道已就位（依赖前置）

## 2. 名称过滤规则（sandbox_secrets.py）

- [x] 2.1 Write failing tests：`is_sensitive_name` 对 `API_TOKEN`/`token`/`MyKey`/`db_secret` 等大小写各异、含 `TOKEN`/`KEY`/`SECRET` 子串的名称返回 True；对**新增子串**也命中——`DB_PASSWORD`/`MYSQL_PASSWD`/`AWS_CREDENTIAL`/`PRIVATE_PEM`/`BASIC_AUTH`（含 `PASSWORD`/`PASSWD`/`CREDENTIAL`/`PRIVATE`/`AUTH`）返回 True；对 `PATH`/`HOME`/`LANG` 返回 False。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `SENSITIVE_TOKENS` 常量（`TOKEN`/`KEY`/`SECRET`/`PASSWORD`/`PASSWD`/`CREDENTIAL`/`PRIVATE`/`AUTH`，可扩展的最小集）与 `is_sensitive_name`（`upper()` 子串匹配），看到绿

## 3. 三层合并过滤管线（sandbox_secrets.py）

- [x] 3.1 Write failing tests：`build_sandbox_env` 优先级 runtime > agent > host；默认 `include_host=False` 不纳入宿主环境；`include_host=True` 时纳入但仍过滤；合并后含 `KEY`/`TOKEN`/`SECRET` 的键被剔除——即便由 agent_env 或 runtime_env 显式写入也剔除。`monkeypatch.setenv` 隔离 `os.environ`。看到红
- [x] 3.2 Implement `build_sandbox_env`（合并后统一过滤），看到绿
- [x] 3.3 Write failing test：显式把 `ANTHROPIC_API_KEY` 写入任一来源，输出映射中不含该键（宿主敏感变量绝不泄漏）。看到红
- [x] 3.4 Implement 确保该守卫通过，看到绿

## 4. create_workspace 注入与防御性二次过滤（sandbox_client.py）

- [x] 4.1 Write failing tests：`create_workspace(name, resources, image, env={"DATA_DIR": "/x"})`（env 与 resources/image 同属 per-create 参数）在 docker run 中出现 `-e DATA_DIR=/x`；`env=None`/空时无 `-e`（与现状等价）；防御性：即便误传含 `KEY`/`PASSWORD` 的键，docker 命令中不出现该键。捕获 `asyncio.create_subprocess_exec` 参数断言。看到红
- [x] 4.2 Implement：`create_workspace(name, resources, image, env)` 接收 `env`，按项转 `-e`，注入前再跑 `is_sensitive_name` 兜底剔除，看到绿

## 5. 收尾

- [x] 5.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 5.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 5.3 `uv run mypy src` 无新增错误
