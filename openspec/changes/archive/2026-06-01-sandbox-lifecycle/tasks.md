## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `tools.py::run_code`（行 49-69）现状：每次 `SandboxClient()` + `create_workspace("run-code")` 即建即毁，确认改为向生命周期层 `acquire` 后行为兼容（执行结果格式不变）
- [x] 1.2 核实 `SandboxClient`（sandbox_client.py）的 `create_workspace` / `exec` / `destroy_workspace` 签名与 `_SAFE_NAME` 清洗逻辑，确认把 create 签名收敛为 `create_workspace(name, resources, image)`（`base_image` 并入 `image`）并扩展 `find_workspace` / `commit_workspace` 不破坏既有调用与既有测试
- [x] 1.3 核实 SB4 的 `SandboxResources` 数据类（含 `read_only` / `network` 等）与 `sandbox.resources` / `sandbox.agent_scope` 配置字段已落地，确认本 change 可消费；确认 SB3 拥有的 `sandbox:` 段已可追加 `scope`（默认 `session`）/ `idle_hours`（默认 2），加载方式与既有 Settings/yaml 惯例一致（参考 `model_router.ROUTES_PATH` 的 yaml 加载模式），确定可 monkeypatch 注入

## 2. SandboxClient 扩展（sandbox_client.py）

- [x] 2.1 Write failing tests：`find_workspace(name)` 命中已存在容器返回 id、不存在返回 None（mock `docker ps` 子进程）；`commit_workspace(ws_id, tag)` 调用 `docker commit ws_id tag`（mock 子进程，断言命令参数）；`create_workspace(name, resources, image)` 用传入 name 而非派生名，且 `resources`（SB4 `SandboxResources`）的 `read_only=False` 时不带 `--read-only`、`read_only=True` 时带 `--read-only`，`image` 直接作为基础镜像传入 `docker run`。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `find_workspace` / `commit_workspace`，并把 `create_workspace` 签名收敛为 `(name, resources, image)`——`resources` 渲染为 `docker run` 旗标（read_only/network/memory/cpus 等来自 SB4 `SandboxResources`），`image` 取代旧 `base_image`（既有可观察创建行为以加固档 + 默认镜像保持），看到绿
- [x] 2.3 Write failing test：既有 `test_sandbox_client.py` 全部用例仍通过（无回归断言：以加固档 + 默认镜像调用时 create 命令与现状一致）。看到红/绿确认兼容
- [x] 2.4 Implement 调整使既有用例与新用例同时绿

## 3. Scope 与 SandboxManager 骨架（sandbox_manager.py）

- [x] 3.1 Write failing tests：`Scope` 枚举含 `SESSION="session"` / `AGENT="agent"`；`SandboxManager` 可注入 `SandboxClient`、`scope`、`idle_hours` 与「scope→`SandboxResources` 档位」映射（消费 SB4 的 `sandbox.resources` / `sandbox.agent_scope`）构造。看到红
- [x] 3.2 Implement `Scope`（StrEnum）与 `SandboxManager.__init__`（实例持登记表 + scope→档位映射，无模块全局），看到绿

## 4. acquire：命名、新建、复用

- [x] 4.1 Write failing tests：`acquire(SESSION, session_id, ...)` 容器名为 `sandbox-session-{清洗后 session_id}`、传给 `create_workspace` 的 `resources` 为加固档（`read_only=True` + `network=none`）；`acquire(AGENT, _, agent_name)` 名为 `sandbox-agent-{清洗后 agent_name}`、`resources` 为叠加 `agent_scope` override 后的档位（`read_only=False` + 配置的 network）；首次 `acquire` 调 `create_workspace(name=..., resources=..., image=...)`；再次同 key `acquire` 命中 `find_workspace` 复用不新建并刷新 last_used；不同 key 互相隔离（不同容器名）。mock SandboxClient。看到红
- [x] 4.2 Implement `acquire`（算名 + 按 scope 选档位 → find 复用 / `create_workspace(name, resources, image)` 新建 → 登记/刷新），看到绿

## 5. release_session 与 sweep_idle

- [x] 5.1 Write failing tests：`release_session(session_id)` 销毁该 session 的 `session` scope 容器并从登记表移除，不动其它容器；`sweep_idle()` 对 `agent` scope 且超 `idle_hours` 的容器先 `commit_workspace` 再 `destroy_workspace`，未超时的不动；`session` scope 不参与闲置回收。mock SandboxClient + 注入可控时钟。看到红
- [x] 5.2 Implement `release_session` / `sweep_idle`（含 commit-then-destroy 顺序），看到绿

## 6. agent scope 依赖固化与基镜像复用

- [x] 6.1 Write failing test：`agent` scope 容器以可写 rootfs（`read_only=False`）创建，故 `sweep_idle` commit 能固化已装依赖，commit 出 `fleetent-sandbox-agent-{key}:latest`；下次 `acquire(AGENT, ...)` 在该镜像存在时把其 tag 作为 `create_workspace` 的 `image` 传入新建，不存在回退默认 `python:3.12-slim`。mock SandboxClient（`find_workspace`/`commit`/`create` 序列）。看到红
- [x] 6.2 Implement 镜像复用逻辑（commit tag 作为下次 `image` 入参，回退默认镜像），看到绿

## 7. 接入 run_code 工具（tools.py）

- [x] 7.1 Write failing tests：`run_code` 经生命周期层 `acquire` 取 workspace，执行后**不**直接 `destroy_workspace`；返回结果格式与现状一致（stdout/stderr/exit）。mock SandboxManager/SandboxClient。看到红
- [x] 7.2 Implement：`run_code` 改用生命周期层，移除即建即毁，看到绿

## 8. 收尾

- [x] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 8.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 8.3 `uv run mypy src` 无新增错误
