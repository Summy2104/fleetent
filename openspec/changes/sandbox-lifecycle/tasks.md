## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `tools.py::run_code`（行 49-69）现状：每次 `SandboxClient()` + `create_workspace("run-code")` 即建即毁，确认改为向生命周期层 `acquire` 后行为兼容（执行结果格式不变）
- [ ] 1.2 核实 `SandboxClient`（sandbox_client.py）的 `create_workspace` / `exec` / `destroy_workspace` 签名与 `_SAFE_NAME` 清洗逻辑，确认扩展 `find_workspace` / `commit_workspace` / 带 name 的 create 不破坏既有调用与既有测试
- [ ] 1.3 确认 `config` 引入 `scope`（默认 `session`）/ `idle_hours`（默认 2）的方式与既有 Settings/yaml 加载惯例一致（参考 `model_router.ROUTES_PATH` 的 yaml 加载模式），确定可 monkeypatch 注入

## 2. SandboxClient 扩展（sandbox_client.py）

- [ ] 2.1 Write failing tests：`find_workspace(name)` 命中已存在容器返回 id、不存在返回 None（mock `docker ps` 子进程）；`commit_workspace(ws_id, tag)` 调用 `docker commit ws_id tag`（mock 子进程，断言命令参数）；`create_workspace(name=...)` 用传入 name 而非派生名。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `find_workspace` / `commit_workspace`，并为 `create_workspace` 增加可选 `name` / `image` / `base_image` 入参（默认保持现状），看到绿
- [ ] 2.3 Write failing test：既有 `test_sandbox_client.py` 全部用例仍通过（无回归断言：默认 create 命令未变）。看到红/绿确认兼容
- [ ] 2.4 Implement 调整使既有用例与新用例同时绿

## 3. Scope 与 SandboxManager 骨架（sandbox_manager.py）

- [ ] 3.1 Write failing tests：`Scope` 枚举含 `SESSION="session"` / `AGENT="agent"`；`SandboxManager` 可注入 `SandboxClient`、`scope`、`idle_hours` 构造。看到红
- [ ] 3.2 Implement `Scope`（StrEnum）与 `SandboxManager.__init__`（实例持登记表，无模块全局），看到绿

## 4. acquire：命名、新建、复用

- [ ] 4.1 Write failing tests：`acquire(SESSION, session_id, ...)` 容器名为 `sandbox-session-{清洗后 session_id}`；`acquire(AGENT, _, agent_name)` 名为 `sandbox-agent-{清洗后 agent_name}`；首次 `acquire` 调 `create_workspace(name=...)`；再次同 key `acquire` 命中 `find_workspace` 复用不新建并刷新 last_used；不同 key 互相隔离（不同容器名）。mock SandboxClient。看到红
- [ ] 4.2 Implement `acquire`（算名 → find 复用 / create 新建 → 登记/刷新），看到绿

## 5. release_session 与 sweep_idle

- [ ] 5.1 Write failing tests：`release_session(session_id)` 销毁该 session 的 `session` scope 容器并从登记表移除，不动其它容器；`sweep_idle()` 对 `agent` scope 且超 `idle_hours` 的容器先 `commit_workspace` 再 `destroy_workspace`，未超时的不动；`session` scope 不参与闲置回收。mock SandboxClient + 注入可控时钟。看到红
- [ ] 5.2 Implement `release_session` / `sweep_idle`（含 commit-then-destroy 顺序），看到绿

## 6. agent scope 依赖固化与基镜像复用

- [ ] 6.1 Write failing test：`agent` scope 容器经 `sweep_idle` commit 出 `fleetent-sandbox-agent-{key}:latest`；下次 `acquire(AGENT, ...)` 在该镜像存在时以其为 `base_image` 新建，不存在回退默认镜像。mock SandboxClient（`find_workspace`/`commit`/`create` 序列）。看到红
- [ ] 6.2 Implement 基镜像复用逻辑，看到绿

## 7. 接入 run_code 工具（tools.py）

- [ ] 7.1 Write failing tests：`run_code` 经生命周期层 `acquire` 取 workspace，执行后**不**直接 `destroy_workspace`；返回结果格式与现状一致（stdout/stderr/exit）。mock SandboxManager/SandboxClient。看到红
- [ ] 7.2 Implement：`run_code` 改用生命周期层，移除即建即毁，看到绿

## 8. 收尾

- [ ] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 8.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 8.3 `uv run mypy src` 无新增错误
