## Why

`fleetent agent run` 的模块文档声称加载 `agent.yaml + .env`，但 `boot()` 从未调用 `load_dotenv()`——`.env` 文件只是一个文档性存根，进程实际上不读它。在单台服务器运行多个 agent 实例的场景下，每个 agent 进程需要各自独立的密钥集（不同 Slack token、不同模型 API key），依赖 shell `export` 会让所有进程共享同一套环境变量，无法实现 per-agent 隔离。

## What Changes

- `agent_app.boot()` 在 `scan_home()` 之前加载 `<home_dir>/.env`，使用 `load_dotenv(override=False)` 注入本进程 `os.environ`
- `override=False`：已在进程环境中设好的变量（systemd `EnvironmentFile` / Docker `--env-file`）优先，`.env` 只填补缺失值
- 无新依赖：`python-dotenv` 已作为 `pydantic-settings` 的传递依赖安装

## Capabilities

### New Capabilities

无新 capability——这是对现有 `agent-runtime-cli` spec 中"loads `.env`"承诺的落地实现。

### Modified Capabilities

- `agent-runtime-cli`：补充"agent home `.env` 自动加载"要求：`boot()` 在启动前加载 `<home>/.env`，`override=False`，`.env` 不存在时跳过。

## Impact

- **修改文件**：`src/fleetent/runtime/agent_app.py`（`boot()` 函数，约 3 行）
- **测试**：`tests/unit/test_agent_run_cli.py`（已有 boot 相关测试，补充 `.env` 加载场景）
- **文档**：`config/agent/.env.standalone.example` 头部注释更新（`.env` 现在会被自动加载）
- **无破坏性变更**：未设 `.env` 的现有部署行为不变；已通过外部注入密钥的部署因 `override=False` 也不受影响
