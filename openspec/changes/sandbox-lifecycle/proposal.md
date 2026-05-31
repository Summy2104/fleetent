## Why

当前 `run_code` 工具（`tools.py` 行 49-69）每次调用都新建一个 `SandboxClient()`、`create_workspace("run-code")` 执行后立即 `destroy_workspace`：单次调用即建即毁，容器名硬编码为 `sandbox-run-code`，既无法在同一会话内复用容器（每次冷启动、已安装依赖丢失），也无法按 agent 长期保留环境。`SandboxClient` 本身只暴露 `create_workspace(session_id)` / `exec` / `destroy_workspace`，没有「容器存活粒度（scope）」的概念。

`docs/capabilities/sandbox.md` 的「生命周期管理（scope）」要求按配置决定沙箱存活粒度：`session`（默认，会话内复用、会话结束销毁）与 `agent`（每个 agent 独享、跨会话保留、`docker commit` 固化依赖、闲置超时销毁）。本 change（SB2 生命周期）是 SB3（启用控制/上下文通道）与 SB4（资源档位）的**消费方**——它消费 SB3 的 run_code 上下文通道与 `sandbox:` 配置段、消费 SB4 定义的 `SandboxResources`，在其上拥有「scope→资源档位」映射与容器生命周期语义；不自引资源旋钮。实施顺序为 **SB3 → SB4 → SB2**。沙箱后端经评估保留 Docker，本 change 全部基于现有 Docker CLI 封装演进。

## What Changes

- 引入**沙箱生命周期管理层**（建议 `src/fleetent/sandbox_manager.py`）：按 `scope` 决定容器粒度，对外提供「按 (scope, session_id, agent_name) 取得可用 workspace」的统一入口，复用已存在的容器、按需新建、按生命周期销毁。
- 定义两种 scope（来自 sandbox.md）：
  - `session`（默认）：以 session_id 为 key，会话开始时创建、同一会话内多次 `run_code` 复用同一容器、会话结束销毁。
  - `agent`：以 agent_name 为 key，每个 agent 定义独享一个容器、跨会话长期保留；闲置超过 `idle_hours`（默认 2 小时）自动销毁。
- 容器命名规则承载归属信息：`sandbox-{scope}-{key}`（key 经现有 `_SAFE_NAME` 清洗），便于 SB8 按前缀识别归属、便于复用查找。
- `agent` scope 在容器销毁前通过 `docker commit` 把已安装依赖固化为镜像层，下次同 agent 新建容器复用该镜像快速恢复（无需重装依赖）。前提是 agent 容器以**可写 rootfs** 创建（去掉 `--read-only`），site-packages 才能落地并被 commit 捕获。
- **拥有「scope→资源档位」映射策略**：本 change 消费 SB4 定义的 `SandboxResources`（含 `read_only` / `network` 等加固旋钮），并据 scope 选择档位——`session` scope 用 `sandbox.resources`（加固档，`read_only=True` + `network=none`），`agent` scope 用 `sandbox.resources` 叠加 `sandbox.agent_scope` override（`read_only=False` + 可配置 `network`）。本 change 不自引 network/read_only 旋钮，只定义档位映射。
- 改造 `run_code` 工具：不再每次 `SandboxClient()` 即建即毁，改为向生命周期层申请 workspace；执行后**不销毁**（由生命周期层按 scope 决定何时销毁）。
- scope、idle_hours 由 SB3 拥有的 `sandbox:` 配置段提供（本 change 只追加这两个生命周期字段）；资源档位（`sandbox.resources` / `sandbox.agent_scope`）的字段定义属 SB4，本 change 消费之。

## Capabilities

### New Capabilities
- `sandbox-lifecycle`: 沙箱容器生命周期管理——按 `scope`（`session` 默认 / `agent`）决定容器存活粒度与复用边界；`session` scope 会话内复用、会话结束销毁、保持 `--read-only --network none` 全加固；`agent` scope 跨会话保留、以可写 rootfs 创建、`docker commit` 固化依赖、闲置超时销毁；按 scope 消费 SB4 的 `SandboxResources` 选择资源档位；容器命名编码归属信息供复用查找与孤儿识别。

### Modified Capabilities
<!-- 不修改既有 spec。既有 sandbox-client 主 spec 为 microsandbox 历史版本，与本 change 引入的 Docker 后端能力无对应需求，故不以 MODIFIED 表达。SandboxClient 的「按归属命名 + 查找已存在容器 + commit 固化」属 Docker 后端新增能力，落在本 change 新 capability `sandbox-lifecycle` 下以 ADDED 表达。 -->

### 依赖

实施顺序：**SB3 → SB4 → SB2**。本 change 是 SB3 + SB4 的消费方。

- **依赖 SB3（sandbox-enablement-control）先落地 run_code 上下文通道与 `sandbox:` 配置段**：`run_code(code)` 当前签名只有 `code`，`tool_registry.dispatch(name, arguments_json, allowed_tools, is_sub_agent)` 不透传 session_id / agent_name / features。session/agent scope 的 `acquire(scope, session_id, agent_name)` 需要这两个上下文值。该「agent/session 上下文经 agent_loop → tool_registry.dispatch → tools.run_code 的传递通道」与 `config/settings.yaml` 的 `sandbox:` 段骨架由 SB3 拥有并实现，本 change 复用该通道与配置段、不自造。
- **依赖 SB4（sandbox-resources）先落地 `SandboxResources`**：SB4 定义 `SandboxResources`（含 `read_only` / `network` / `memory` / `cpus` 等旋钮）及 `sandbox.resources` / `sandbox.agent_scope` 配置字段。本 change 消费该数据类与字段，按 scope 映射档位（session 用加固档，agent 叠加 `read_only=False` + 可配置 network 的 override），并将所选 `resources` 经 `create_workspace(name, resources, image)` 传给 client；本 change 不自引 network/read_only 旋钮。

## Impact

- **代码**：
  - 新增 `src/fleetent/sandbox_manager.py`（`Scope` 枚举 + `SandboxManager`：`acquire(scope, session_id, agent_name)` / `release_session(session_id)` / `sweep_idle()`；持有「scope→`SandboxResources` 档位」映射策略，消费 SB4 的 `SandboxResources`）。
  - 修改 `src/fleetent/sandbox_client.py`：增加 `find_workspace(name)`（按容器名查已存在容器，返回 id 或 None）与 `commit_workspace(workspace_id, image_tag)`（`docker commit`）；`create_workspace` 签名收敛为 `create_workspace(name, resources, image)`——`resources` 为 SB4 的 `SandboxResources`（承载 read_only/network 等），`image` 为基础镜像（agent scope 复用 commit 镜像即把其 tag 当 `image` 传入，不再单列 `base_image` 参数）。
  - 修改 `src/fleetent/tools.py`：`run_code` 通过生命周期层获取 workspace，执行后不再直接 `destroy_workspace`。
- **配置**：向 SB3 拥有的 `sandbox:` 段追加 `scope`（默认 `session`）与 `idle_hours`（默认 2）两个生命周期字段；资源档位字段（`sandbox.resources` / `sandbox.agent_scope`）属 SB4，本 change 消费。
- **测试**：新增 `tests/test_sandbox_manager.py`（含「session 用加固档、agent 叠加 read_only=False override」的档位映射断言）；扩充 `tests/test_sandbox_client.py` 覆盖 `find_workspace` / `commit_workspace` / `create_workspace(name, resources, image)`。Docker CLI 调用全部 mock（`patch asyncio.create_subprocess_exec`），不触碰真实容器。
- **不影响**：SB3 启用控制（mode/agent 开关）、agent_loop 主循环、permission_gate、工具访问控制；不引入新依赖（沿用 `docker` CLI + 既有 `yaml`/`config`）。`SandboxResources` 字段定义不在本 change（属 SB4），本 change 仅消费。
