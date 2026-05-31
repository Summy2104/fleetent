## Why

`SandboxClient.create_workspace`（`sandbox_client.py` 行 27-38）的 `docker run` 不传任何 `-e` 环境变量，容器内是一个干净的环境——但这也意味着**两个相反的缺口**：

1. **无法注入合法密钥**：当代码确实需要某个凭据（如调用内网服务的 token）时，没有受控的注入通道。
2. **一旦未来注入，缺乏过滤会泄漏宿主机敏感变量**：宿主机进程环境里有 `ANTHROPIC_API_KEY` 等敏感变量，若用 `--env-file` 或透传宿主环境，会把这些密钥泄漏进容器（容器内代码可 `os.environ` 读到）。

`docs/capabilities/sandbox.md` 的「密钥过滤（三层环境变量过滤）」要求：Docker 无原生 Secret，改为在启动容器时**按名称过滤**——变量名含 `TOKEN` / `KEY` / `SECRET`（大小写不敏感）一律不传入容器；三层指宿主机进程环境、agent 配置注入的变量、运行时显式传入的变量，均经同一过滤规则。本 change 建立「受控注入 + 统一名称过滤」的环境变量边界。沙箱后端保留 Docker（占位符级 Secret 非 Docker 原生，留作后续探索）。

## What Changes

- 引入**统一环境变量过滤规则** `is_sensitive_name(name) -> bool`：变量名（大小写不敏感）含 `TOKEN` / `KEY` / `SECRET` 子串即判定为敏感、不得传入容器。
- 引入**三层环境变量合并 + 过滤管线** `build_sandbox_env(...)`：按优先级合并三类来源——
  1. 宿主机进程环境（`os.environ`，默认**不**整体透传，仅在显式选择透传时参与，且必经过滤）；
  2. agent 配置注入的变量（agent 定义中声明的沙箱环境变量）；
  3. 运行时显式传入的变量；
  三类合并后**统一**经 `is_sensitive_name` 过滤，敏感名一律剔除。
- `SandboxClient.create_workspace` 接收过滤后的 env 映射，转为 `docker run -e KEY=VALUE`（仅非敏感、已批准的变量进入容器）。
- 明确：**宿主机敏感变量绝不进入容器**——即便某来源显式写入 `ANTHROPIC_API_KEY`，过滤规则也会剔除（名称含 `KEY`）。

## Capabilities

### New Capabilities
- `sandbox-secret-injection`: 沙箱环境变量的受控注入与统一名称过滤——三层来源（宿主进程环境 / agent 注入 / 运行时传入）合并后，名称含 `TOKEN`/`KEY`/`SECRET`（大小写不敏感）的变量一律不传入容器；通过过滤的变量经 `docker run -e` 注入；宿主机敏感变量绝不泄漏进沙箱。

### Modified Capabilities
<!-- 不修改既有 spec。既有 sandbox-client 主 spec 为 microsandbox 历史版本，与本 change 引入的 Docker 后端能力无对应需求，故不以 MODIFIED 表达。`create_workspace` 接收已过滤 env 并 `-e` 注入属 Docker 后端新增能力，落在本 change 新 capability `sandbox-secret-injection` 下以 ADDED 表达。 -->

### 共享资源引用（依赖 SB3）
- **agent 注入变量承载位 = SB3 的 `features.sandbox_env`**：SB3 已在 `agent_store` 引入 `features` JSON 列（owner），本 change 复用同一列下的 `sandbox_env` 键承载 agent 配置注入变量，**不重复加列**。
- **run_code 上下文通道 owner = SB3**：取 agent 的 `features.sandbox_env` 作为 `agent_env` 传入 `build_sandbox_env`，经 SB3 拥有的 run_code 上下文通道（agent_loop → dispatch → run_code）获取，**不自造**。故实施依赖 SB3 先落地 features 列与上下文通道。

## Impact

- **代码**：
  - 新增 `src/fleetent/sandbox_secrets.py`（`SENSITIVE_TOKENS` 常量 + `is_sensitive_name()` + `build_sandbox_env()` 三层合并过滤管线）。
  - 修改 `src/fleetent/sandbox_client.py`：`create_workspace` 接收 `env: dict[str, str] | None`，转为 `docker run -e` 参数（None/空时与现状等价）。
- **配置**：agent 定义的沙箱注入变量来源（可与 SB3 的 `features` 同处 agent 配置，或独立 `sandbox_env` 段，design 中定）；过滤规则的敏感子串为模块级可注入常量。
- **测试**：新增 `tests/test_sandbox_secrets.py`（名称过滤大小写不敏感、三层合并优先级、敏感名剔除）；扩充 `tests/test_sandbox_client.py` 断言 `-e` 仅含非敏感变量、敏感变量不出现在 docker 命令。Docker CLI 全部 mock；`os.environ` 用 `monkeypatch.setenv` 隔离。
- **不影响**：SB2 scope、SB3 mode、SB4 资源配置、agent_loop、permission_gate；不引入新依赖。占位符级 Secret 不在本 change 范围。
