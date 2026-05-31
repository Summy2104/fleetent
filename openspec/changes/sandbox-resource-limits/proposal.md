## Why

`SandboxClient.create_workspace`（`sandbox_client.py` 行 27-38）把资源限制硬编码进 `docker run`：`--network none --memory 256m --cpus 0.5 --read-only --tmpfs /tmp`。运维无法在不改代码的前提下调整内存、CPU、网络策略或单次执行超时——不同部署环境（数据分析 agent 需要更大内存、内网部署需要 `public_only` 网络）只能改源码重新发布。

`docs/capabilities/sandbox.md` 的「资源限制可配置」要求通过 `settings.yaml` 声明，未配置时使用安全默认值：

```yaml
sandbox:
  resources:
    memory: 256       # MB
    cpus: 0.5
    network: "none"   # none / public_only / allow_all
    exec_timeout: 30  # 单次执行超时（秒）
```

本 change 把硬编码资源限制外置为配置，沿用项目既有的 yaml 加载惯例（`model_router.ROUTES_PATH` + `yaml.safe_load`）。沙箱后端保留 Docker，所有资源参数映射到 Docker `run` 标志。

## What Changes

- 引入**沙箱资源配置**数据结构 `SandboxResources`：`memory`（MB）/ `cpus` / `network`（`none`/`public_only`/`allow_all`）/ `exec_timeout`（秒）。
- 从配置加载（建议 `config/settings.yaml` 的 `sandbox.resources` 段，或 `config.Settings` 的对应字段，与既有惯例对齐）；**未配置时使用安全默认值**（`memory=256`、`cpus=0.5`、`network=none`、`exec_timeout=30`），且 `network=none` 为默认推荐值。
- `network` 三态映射到 Docker：`none → --network none`；`public_only` 与 `allow_all` 的具体网络后端映射在 design 中确定（默认与推荐仍是 `none`）。
- `SandboxClient.create_workspace` 不再硬编码资源标志，改为接收 `SandboxResources` 并据此构造 `docker run` 参数。
- `exec_timeout` 字段本 change 仅**承载并传递**（写入配置 → 传入 client），实际「超时强制终止」是波次 3（依赖 cancel token）范围，本 change 不实现 `docker kill` 终止逻辑。

## Capabilities

### New Capabilities
- `sandbox-resource-limits`: 沙箱资源限制可配置——`memory` / `cpus` / `network`（三态）/ `exec_timeout` 经配置声明，未配置时回退安全默认值（`network=none` 为默认推荐）；配置值正确映射到 `docker run` 标志，不再硬编码。

### Modified Capabilities
<!-- 不修改既有 spec。既有 sandbox-client 主 spec 为 microsandbox 历史版本，与本 change 引入的 Docker 后端能力无对应需求，故不以 MODIFIED 表达。`create_workspace` 据资源配置构造命令属 Docker 后端新增能力，落在本 change 新 capability `sandbox-resource-limits` 下以 ADDED 表达。 -->

### 共享资源引用
- **`config/settings.yaml` 的 `sandbox:` 段 owner = SB3**：本 change 仅向该段**追加** `resources`（`memory`/`cpus`/`network`/`exec_timeout`）子段，不建段；`sandbox.mode`（SB3）与 `sandbox.scope`/`idle_hours`（SB2）共处同段。

## Impact

- **代码**：
  - 新增/扩展配置：`SandboxResources` 数据结构 + 加载逻辑（建议 `src/fleetent/sandbox_config.py`，或并入 `config.py` 的 Settings 与 yaml 加载，按既有惯例定）。
  - 修改 `src/fleetent/sandbox_client.py`：`SandboxClient.__init__` 或 `create_workspace` 接收 `SandboxResources`；`docker run` 参数据其构造；缺省回退默认值。
- **配置**：新增 `sandbox.resources`（`memory` / `cpus` / `network` / `exec_timeout`）配置段，全部可选，缺省用安全默认值。
- **测试**：新增 `tests/test_sandbox_config.py`（加载 + 默认值 + 校验）；扩充 `tests/test_sandbox_client.py` 断言配置值正确出现在 `docker run` 参数、未配置时为默认值。Docker CLI 全部 mock，yaml 路径 `monkeypatch` 到 tmp_path。
- **不影响**：SB2 生命周期 scope、SB3 启用 mode、agent_loop、permission_gate；不引入新依赖（`yaml` 已在用）。
