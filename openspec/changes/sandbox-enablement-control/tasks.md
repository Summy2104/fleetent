## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `tools.py` 中 `run_code` 的注册路径：`@tool` 装饰为 import 副作用（CLAUDE.md Gotchas），确认「不注册」需在 import / 注册时机据 mode 条件化，而非运行期摘除
- [ ] 1.2 核实 `agent_store` 的 `Agent` 数据类字段与建表/读写 SQL（`_init_db` 用 `CREATE TABLE IF NOT EXISTS`），确认旧库需显式 `ALTER TABLE agents ADD COLUMN features TEXT`（已定调，见 design D3），核实幂等迁移写法（`PRAGMA table_info` 查列后缺则 ALTER）
- [ ] 1.3 核实 `tool_registry.dispatch(name, arguments_json, allowed_tools, is_sub_agent)` 与 `run_code(code)` 均不透传 agent/session 上下文（已定调需补通道，见 design D5），确定 agent_loop → dispatch → run_code 的改造点
- [ ] 1.4 确认沙箱 `mode` 配置项写入 `config/settings.yaml` 的 `sandbox:` 段、默认 `all`（参考 `model_router` yaml 加载与 `config.Settings` 惯例），确定可 monkeypatch；**本 change 作为首个落地者建立 `sandbox:` 段骨架**

## 2. 三态判定纯函数（sandbox_enablement.py）

- [ ] 2.1 Write failing tests：`Mode` 枚举含 `off`/`selective`/`all`；`is_code_execution_enabled` 覆盖三态 × {True/False/None}：`off` 恒 False；`selective` 仅 True 为开；`all` 下 None/True 开、False 关。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `Mode`（StrEnum）与 `is_code_execution_enabled`，看到绿
- [ ] 2.3 Write failing tests：`resolve_effective_mode(configured, docker_available)`：`docker_available=False` 一律返回 `off`；为 True 时原样返回 configured。看到红
- [ ] 2.4 Implement `resolve_effective_mode`，看到绿

## 3. Docker 可用性探测（sandbox_client.py）

- [ ] 3.1 Write failing tests：`docker_available()` 探测命令 returncode 为 0 时返回 True；非零或 `FileNotFoundError` 时返回 False 且不抛异常（mock `asyncio.create_subprocess_exec`）。看到红
- [ ] 3.2 Implement `docker_available()`（探测失败 log 警告后返回 False），看到绿

## 4. agent_store features 列（agent_store.py，本 change owner）

- [ ] 4.1 Write failing tests：`Agent` 含 `features` 字段（默认 `{}`）；create + get 往返保留 `features={"code_execution": True}`；读取旧行（无 features 值）回退 `{}`。`monkeypatch DB_PATH` 隔离到 tmp_path。看到红
- [ ] 4.2 Implement：`Agent` 增 `features`；建表/读写 SQL 增 `features` 列（裸 SQL，`json.dumps`/`json.loads`，旧行 `or "{}"` 兜底），看到绿
- [ ] 4.3 Write failing test：对一个**无 features 列的旧库**（先建只含原列的 `agents` 表并插入一行，再调 `_init_db`）执行迁移后，`features` 列存在、旧行读取回退 `{}` 且不抛 `IndexError`。看到红
- [ ] 4.4 Implement：`_init_db` 在建表后做幂等 `ALTER TABLE agents ADD COLUMN features TEXT`（`PRAGMA table_info(agents)` 查列、缺则 ALTER），看到绿

## 4b. run_code 上下文通道（agent_loop → tool_registry → tools，本 change owner）

- [ ] 4b.1 Write failing tests：`dispatch` 增加可选上下文入参（agent 标识 / agent features / session_id），透传给 `run_code`；不需要上下文的既有工具调用不受影响（既有 dispatch 用例不回归）。看到红
- [ ] 4b.2 Implement：`tool_registry.dispatch` 增上下文入参并向下传递；`agent_loop` 调用 `_safe_dispatch`/`dispatch` 处带上当前 agent/session 上下文；`run_code` 据上下文取 features。SB2/SB5 复用此通道。看到绿
- [ ] 4b.3 Write failing test：缺省上下文（无 agent 绑定的直接调用）时 `run_code` 启用判定退回全局 mode 默认、不抛异常。看到红
- [ ] 4b.4 Implement 缺省安全降级，看到绿

## 4c. sandbox: 配置段骨架（config/settings.yaml，本 change owner）

- [ ] 4c.1 Write failing tests：从 `config/settings.yaml` 的 `sandbox:` 段读取 `sandbox.mode`，缺省回退默认 `all`；路径常量可 monkeypatch 到 tmp_path。看到红
- [ ] 4c.2 Implement：建立 `sandbox:` 段加载（首个落地者建段，写入 `sandbox.mode`），看到绿

## 5. 注册点：off/降级不注册 run_code

- [ ] 5.1 Write failing tests：生效 mode 为 `off` 时工具 schema 不含 `run_code`；`selective`/`all` 时含。看到红
- [ ] 5.2 Implement：据 `resolve_effective_mode` 结果在注册时机条件化注册 `run_code`，看到绿

## 6. 调用拒绝点：agent 级开关拦截

- [ ] 6.1 Write failing tests：`selective` 且 agent `code_execution` 非 True 时，`run_code` 调用返回拒绝文本且不进入沙箱执行；`all` 且 agent 显式 `code_execution=False` 时同样拒绝；授权 agent 正常执行。mock SandboxClient/Manager。看到红
- [ ] 6.2 Implement：`run_code` 调用入口经 `is_code_execution_enabled` 判定，未授权返回拒绝文本，看到绿

## 7. 启动期降级接线

- [ ] 7.1 Write failing tests：启动流程探测 Docker 不可用时生效 mode 为 `off` 且记录警告，平台启动不抛异常（mock `docker_available` 返回 False）。看到红
- [ ] 7.2 Implement：server lifespan / CLI run 启动期探测 + `resolve_effective_mode` 接线，看到绿

## 8. 收尾

- [ ] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 8.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 8.3 `uv run mypy src` 无新增错误
