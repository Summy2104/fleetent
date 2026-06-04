## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `agent_loop.run()`（`agent_loop.py:346-347`）与 `run_stream()`（`584-586`）已在按 `allowed_tools` 经 `check_tool_access` 做 per-agent schema 过滤——确认两个 gate（`off` / agent 级 `code_execution=false`）应在此同处追加过滤（不进 schema），而非条件化注册或调用入口拒绝；并核实 `run_code` 仍按 import 副作用全局注册（不改注册路径）
- [x] 1.2 核实 `agent_store` 的 `Agent` 数据类字段与建表/读写 SQL（`_init_db` 用 `CREATE TABLE IF NOT EXISTS`），确认旧库需显式 `ALTER TABLE agents ADD COLUMN features TEXT`（已定调，见 design D3），核实幂等迁移写法（`PRAGMA table_info` 查列后缺则 ALTER）
- [x] 1.3 核实 `tool_registry.dispatch(name, arguments_json, allowed_tools, is_sub_agent)` 与 `run_code(code)` 均不透传 agent/session 上下文（已定调需补通道，见 design D5——通道为执行期 SB2/SB5 需求而建，非启用 gate），确定 agent_loop → dispatch → run_code 的改造点；并核实 `_safe_dispatch`（`agent_loop.py:62-76`）调 `dispatch` 时未传 `allowed_tools` → `dispatch` 内 `check_tool_access` 在主循环是死代码（见 design Risk，本 change 不修）
- [x] 1.4 确认沙箱 `mode` 配置项写入 `config/settings.yaml` 的 `sandbox:` 段、默认 `all`（参考 `model_router` yaml 加载与 `config.Settings` 惯例），确定可 monkeypatch；**本 change 作为首个落地者建立 `sandbox:` 段骨架**

## 2. 三态判定纯函数（sandbox_enablement.py）

- [x] 2.1 Write failing tests：`Mode` 枚举含 `off`/`selective`/`all`；`is_code_execution_enabled` 覆盖三态 × {True/False/None}：`off` 恒 False；`selective` 仅 True 为开；`all` 下 None/True 开、False 关。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `Mode`（StrEnum）与 `is_code_execution_enabled`，看到绿
- [x] 2.3 Write failing tests：`resolve_effective_mode(configured, docker_available)`：`docker_available=False` 一律返回 `off`；为 True 时原样返回 configured。看到红
- [x] 2.4 Implement `resolve_effective_mode`，看到绿

## 3. Docker 可用性探测（sandbox_client.py）

- [x] 3.1 Write failing tests：`docker_available()` 探测命令 returncode 为 0 时返回 True；非零或 `FileNotFoundError` 时返回 False 且不抛异常（mock `asyncio.create_subprocess_exec`）。看到红
- [x] 3.2 Implement `docker_available()`（探测失败 log 警告后返回 False），看到绿

## 4. agent_store features 列（agent_store.py，本 change owner）

- [x] 4.1 Write failing tests：`Agent` 含 `features` 字段（默认 `{}`）；create + get 往返保留 `features={"code_execution": True}`；读取旧行（无 features 值）回退 `{}`。`monkeypatch DB_PATH` 隔离到 tmp_path。看到红
- [x] 4.2 Implement：`Agent` 增 `features`；建表/读写 SQL 增 `features` 列（裸 SQL，`json.dumps`/`json.loads`，旧行 `or "{}"` 兜底），看到绿
- [x] 4.3 **【按 zy 指示覆盖：改用 alembic 迁移，非运行时 ALTER】** 旧库迁移由新增 alembic 迁移 `migrations/versions/002_add_agent_features.py` 承接（`revision="002"`/`down_revision="001"`，`op.add_column`/`op.drop_column`）。Write failing test：对一个**无 features 列的旧库**先建只含原列的 `agents` 表，再驱动 002 `upgrade()` → `features` 列存在，`downgrade()` → 移除（`MigrationContext`+`Operations` 绑定真实 sqlite）；另测 `_init_db` 的 CREATE TABLE 直接含 features 列、旧行 NULL 值读取回退 `{}` 不抛 `IndexError`。看到红
- [x] 4.4 **【按 zy 指示覆盖：改用 alembic 迁移，非运行时 ALTER】** Implement：`_init_db` 的 `CREATE TABLE IF NOT EXISTS agents (...)` **直接包含 `features TEXT`**（新库/测试 tmp_path 天然有列，**不**做 `PRAGMA table_info`+运行时 ALTER）；现有生产库由 alembic 002 `op.add_column` 升级；读取统一 `json.loads(row[...] or "{}")` 兜底旧行 NULL。**需张亮复核 002 迁移**（agent_store/agents 表撞车风险）。看到绿

## 4b. run_code 上下文通道（agent_loop → tool_registry → tools，本 change owner，为执行期 SB2/SB5 需求而建）

> 论证依据更新（见 design D5）：本通道**不**用作启用 gate（gate 已在 §5 schema 过滤点完成），而是为 SB2 scope（需 session_id/agent_name）与 SB5 env 注入（需 agent features）的执行期需求建立；任务仍由本 change owner 实现。

- [x] 4b.1 Write failing tests：`dispatch` 增加可选上下文入参（agent 标识 / agent features / session_id），透传给 `run_code`；不需要上下文的既有工具调用不受影响（既有 dispatch 用例不回归）。看到红
- [x] 4b.2 Implement：`tool_registry.dispatch` 增上下文入参并向下传递；`agent_loop` 调用 `_safe_dispatch`/`dispatch` 处带上当前 agent/session 上下文；`run_code` 据上下文取 session_id/agent_name/features 供执行期使用。SB2/SB5 复用此通道。看到绿
- [x] 4b.3 Write failing test：缺省上下文（无 agent 绑定的直接调用）时 `run_code` 以缺省上下文执行、不抛异常。看到红
- [x] 4b.4 Implement 缺省安全降级，看到绿

## 4c. sandbox: 配置段骨架（config/settings.yaml，本 change owner）

- [x] 4c.1 Write failing tests：从 `config/settings.yaml` 的 `sandbox:` 段读取 `sandbox.mode`，缺省回退默认 `all`；路径常量可 monkeypatch 到 tmp_path。看到红
- [x] 4c.2 Implement：建立 `sandbox:` 段加载（首个落地者建段，写入 `sandbox.mode`），看到绿

## 5. 统一生效点：schema 过滤剔除 run_code（off + agent 级开关）

- [x] 5.1 Write failing tests：在 `agent_loop` 现有 `allowed_tools` schema 过滤处追加代码执行过滤——生效 mode `off` 时任何 agent 的 schema 都不含 `run_code`；`selective` 下仅 `code_execution=True` 的 agent 的 schema 含、未声明/`False` 的不含；`all` 下未声明/`True` 含、显式 `False` 不含。`run()` 与 `run_stream()` 经新增入参接收生效 mode + agent features。mock `get_schemas` 含 `run_code`。看到红
- [x] 5.2 Implement：`run()`/`run_stream()` 增生效 mode + agent features 入参，在现有 `check_tool_access` 过滤同处追加 `is_code_execution_enabled` 过滤（不可用则剔除 `run_code`）；不改注册路径、不条件化注册。看到绿

## 6. agent features 传入与缺省语义（schema 过滤入参）

- [x] 6.1 Write failing tests：调用方（CLI run / server）从 agent 定义取 `features` 并连同生效 mode 传入 `run()`/`run_stream()`；无 agent 绑定（features 缺省）时按全局 mode 默认决定 `run_code` 是否进 schema（`all` 进、`selective`/`off` 不进），不抛异常。看到红
- [x] 6.2 Implement：调用方组装 (effective_mode, agent_features) 入参；缺省 features 安全降级到全局 mode 默认。看到绿

## 7. 启动期降级接线 + 降级态暴露

- [x] 7.1 Write failing tests：启动流程探测 Docker 不可用时生效 mode 为 `off` 且记录警告，平台启动不抛异常（mock `docker_available` 返回 False）。看到红
- [x] 7.2 Implement：server lifespan / CLI run 启动期探测 + `resolve_effective_mode` 接线，看到绿
- [x] 7.3 Write failing tests：启动日志输出生效 mode（降级时含 `sandbox mode=off (docker unavailable)`）；`GET /health` 响应体暴露生效 sandbox mode 字段（Docker 不可用为 `off` 并标注降级原因）。mock `docker_available` 覆盖可用/不可用两路。看到红
- [x] 7.4 Implement：启动日志打印生效 mode + 降级原因；`/health` 处理器加入 sandbox mode 字段，看到绿

## 8. 收尾

- [x] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 8.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 8.3 `uv run mypy src` 无新增错误
