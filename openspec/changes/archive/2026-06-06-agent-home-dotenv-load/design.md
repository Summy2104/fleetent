## Context

`fleetent agent run <id>` 将每个 agent 作为独立 OS 进程启动。进程间 `os.environ` 天然隔离，多 agent 部署的密钥不会互相污染。

当前问题：`boot()` 函数从不加载 agent home 下的 `.env` 文件。`agent_init` 会在 scaffold 时生成 `.env` 存根，模块文档也声称加载 `.env`，但 `boot()` 实际从不读它。操作人员若不在进程外手动 export 变量，所有 `*_env` 引用均解析为空字符串，导致模型 / Slack / MCP 连接静默失败。

`python-dotenv` 已通过 `pydantic-settings` 作为传递依赖安装（`config.py` 中 `Settings` 的 `env_file=".env"` 即依赖它），无需新增依赖。

## Goals / Non-Goals

**Goals:**
- `boot()` 在启动前自动从 `<home_dir>/.env` 加载变量到本进程 `os.environ`
- 已存在的进程环境变量（systemd `EnvironmentFile`、Docker `--env-file`、shell `export`）优先于 `.env`
- `.env` 不存在时静默跳过，不影响现有部署
- 不引入新的直接依赖

**Non-Goals:**
- 平台托管模式（`AgentController.Popen`）的 per-agent 环境隔离——另立 change 处理
- `.env` 热重载（重启进程才生效，符合现有运维预期）
- 加密 `.env`（plain-text 足够，密钥保护由文件系统权限承担）

## Decisions

### D1：在 `boot()` 而非 `scan_home()` 中加载

`scan_home()` 是纯配置索引函数，不应有 `os.environ` 副作用。`boot()` 是 agent 进程的启动入口，拥有 `home_dir` 的完整所有权，是加载的正确位置。

替代方案：在 `scan_home()` 内加载——被否决，`scan_home()` 在测试中频繁被调用，副作用会污染测试环境。

### D2：`load_dotenv(env_path, override=False)`

`override=False`：若变量已在进程环境中存在（由 systemd / Docker / shell 注入），保持不变，`.env` 只补充缺失值。这使 `.env` 成为"本地开发便利层"，而非"生产强制覆盖层"，不破坏任何现有部署模式。

替代方案：`override=True`——被否决，会使 Docker `--env-file` 的值被 `.env` 覆盖，破坏容器部署。

### D3：加载位置：`resolve_home()` 之后、`scan_home()` 之前

`scan_home()` 会触发 `load_agent_file()`，后者解析 `agent.yaml` 后调用各 `*_env` 字段的下游消费者（模型 resolver、embedding、Slack supervisor）。这些消费者在初始化时读取 `os.environ`，因此 `.env` 必须在 `scan_home()` 之前加载完毕。

### D4：懒导入 `from dotenv import load_dotenv`

在函数内部懒导入，不在模块顶层导入，避免增加 `agent_app` 模块的 import 时间，与项目其他懒导入风格（`from fleetent.skills import scan`）保持一致。

### D5：显式声明 `python-dotenv` 直接依赖

当前 `python-dotenv` 是 `pydantic-settings` 的传递依赖。一旦 `pydantic-settings` 将其改为可选 extra，传递依赖可能消失。在 `pyproject.toml` 中显式声明 `python-dotenv` 确保依赖稳定。

## Risks / Trade-offs

**[Risk] `.env` 中的变量覆盖子进程继承的同名变量**
→ `override=False` 已规避：父进程环境变量始终优先。

**[Risk] 测试中意外加载真实 `.env`**
→ 测试通过 `monkeypatch` 注入 `home_dir` 指向 `tmp_path`，`tmp_path` 下不存在 `.env`，`if env_path.exists()` 守卫确保静默跳过。现有测试不受影响。

**[Risk] `python-dotenv` 传递依赖不稳定**
→ D5 已解决：显式加入 `pyproject.toml`。

## Migration Plan

1. `pyproject.toml` 加入 `python-dotenv>=1.0.0`
2. `agent_app.py:boot()` 加入 3 行 dotenv 加载逻辑
3. 更新 `config/agent/.env.standalone.example` 注释（"文件会被自动加载"）
4. 补充单元测试：`.env` 存在时变量被注入；`.env` 不存在时静默跳过；外部注入的变量不被覆盖
5. 无需数据库迁移，无需停机

**回滚**：revert `boot()` 的 3 行改动即可；`.env` 文件继续存在但不再被读取，行为回到当前状态。

## Open Questions

无。依赖已确认，实现路径清晰，范围收窄到 standalone 路径。
