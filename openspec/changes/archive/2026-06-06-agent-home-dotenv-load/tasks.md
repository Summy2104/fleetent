## 1. 依赖声明

- [x] 1.1 Write failing test: `pyproject.toml` 中存在 `python-dotenv` 直接依赖
- [x] 1.2 在 `pyproject.toml` 的 `dependencies` 中显式添加 `python-dotenv>=1.0.0`，运行 `uv sync`

## 2. 核心实现

- [x] 2.1 Write failing tests for `boot()` `.env` 加载行为（见下方测试说明）
- [x] 2.2 在 `agent_app.py:boot()` 中，`resolve_home()` 之后、`scan_home()` 之前加入 `.env` 加载逻辑：
  ```python
  env_path = home_dir / ".env"
  if env_path.exists():
      from dotenv import load_dotenv
      load_dotenv(env_path, override=False)
  ```

## 3. 测试补全

- [x] 3.1 Write failing test: `.env` 存在时变量被注入 `os.environ`（在 `tests/unit/test_agent_run_cli.py`）
- [x] 3.2 Write failing test: `.env` 不存在时 `boot()` 静默跳过，不抛异常
- [x] 3.3 Write failing test: 进程环境变量已存在时 `.env` 中的同名变量不覆盖（`override=False` 验证）
- [x] 3.4 实现使上述测试通过（task 2.2 完成后应已绿，此步确认）
- [x] 3.5 运行 `uv run pytest tests/unit/test_agent_run_cli.py -x -q` 全绿
- [x] 3.6 运行 `uv run pytest -x -q` 全套通过

## 4. 文档更新

- [x] 4.1 更新 `config/agent/.env.standalone.example` 头部注释：将"此文件不会被自动加载"改为"此文件在 `boot()` 时自动加载"，并保留 systemd / Docker 注入优先的说明
- [x] 4.2 运行 `uv run python scripts/check_test_layers.py` 确认测试层级无违规
