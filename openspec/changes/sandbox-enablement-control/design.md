## Context

代码执行能力当前无任何开关：`run_code` 在 `tools.py` 以 `@tool(risk_level="medium")` 装饰，import `tools.py` 即注册（注册是 import 副作用，见 CLAUDE.md Gotchas），`get_schemas()` 对所有 agent 一律暴露。`agent_store.Agent` 数据类目前只有 `id` / `name` / `system_prompt` / `allowed_tools`（无 `features`）；建表 SQL 也无 features 列。`SandboxClient` 无 Docker 可用性探测，Docker 缺失时 `create_workspace` 抛 `RuntimeError("docker run failed")`，但工具仍然注册并暴露给 AI。

`docs/capabilities/sandbox.md` 的 enable 子图把启用控制定为「每次调用检查」：全局 `mode` 先判，`selective` 再查 agent 的 `code_execution`，Docker 不可用降级为 `off`。本 change 把这套判定从「无」变为可治理的双层开关。

**既有 spec 归属说明**：现有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本，属既有技术债，不在本 change 范围。本 change 引入的全部能力（含 SandboxClient 的 Docker 可用性探测）均为新增，以新 capability `sandbox-enablement-control` 下的 ADDED 表达，不对 sandbox-client 主 spec 做 MODIFIED（否则 archive sync 找不到同名既有需求）。

**本 change 是三项共享资源的 owner**（在 SB 治理轨内统一供其余 change 复用）：
- **`agent_store.features` JSON 列**：本 change 引入并迁移；SB5 复用同一列放 `sandbox_env`，不重复加列。
- **`config/settings.yaml` 的 `sandbox:` 段骨架**：本 change 首个落地者建段并写 `sandbox.mode`；SB2 追加 `scope`/`idle_hours`，SB4 追加 `resources`。
- **run_code 上下文通道**：本 change 拥有「agent/session 上下文经 agent_loop → tool_registry.dispatch → tools.run_code 的传递通道」实现任务；SB2/SB5 复用。

**依赖/归档顺序**：本 change 是 SB2（scope `acquire` 需 session_id/agent_name）与 SB5（agent_env 注入）的前置——三项共享资源在本 change 落地后，SB2/SB5 方可基于其上实现。建议归档顺序 SB3 在 SB2/SB5 之前。

约束（CLAUDE.md）：禁止 ORM（agent_store 用 aiosqlite 裸 SQL）；禁止全局可变状态（mode/DB 路径常量可 monkeypatch）；判定逻辑做成纯函数易单测；新模块 import → 常量 → 数据类 → 函数；mypy strict；TDD Hard Gate；测试 mock Docker CLI、隔离 SQLite 到 tmp_path；不吞异常（探测失败要 log）。

## Goals / Non-Goals

**Goals:**
- 定义三态 `Mode`（`off`/`selective`/`all`，默认 `all`）与 agent 级 `features.code_execution`（`True`/`False`/未声明）。
- 纯函数 `is_code_execution_enabled(mode, agent_features) -> bool` 覆盖三态 × agent 开关全部组合。
- `off`/降级时 `run_code` 不注册（AI 不可见）；`selective`/`all` 注册后在调用入口按 agent 开关拒绝。
- Docker 不可用时启动期把生效 mode 降级为 `off`，记录警告，平台正常启动。
- `agent_store` 增 `features` 列，旧行向后兼容默认 `{}`。

**Non-Goals:**
- 不实现 scope/生命周期（SB2）、不实现资源配置（SB4）、不实现密钥过滤（SB5）、不实现孤儿清理（SB8）、不实现 trace（SB9）。
- 不改 `run_code` 的执行语义、不改 permission_gate（`run_code` 仍是 medium 风险，审批门不变）。
- 不引入新依赖。

## Decisions

### D1：三态判定为纯函数，与「注册」「调用拒绝」两个生效点分离
新增 `src/fleetent/sandbox_enablement.py`：
- `Mode`：`str` 枚举，`OFF="off"` / `SELECTIVE="selective"` / `ALL="all"`。
- `resolve_effective_mode(configured: Mode, docker_available: bool) -> Mode`：`docker_available=False` 一律返回 `OFF`，否则返回 configured。
- `is_code_execution_enabled(mode: Mode, code_execution: bool | None) -> bool`：
  - `OFF` → False；
  - `SELECTIVE` → `code_execution is True`；
  - `ALL` → `code_execution is not False`（None 或 True 都开，显式 False 才关）。

**两个生效点**：
1. **注册点**（启动期/CLI run 时）：生效 mode 为 `OFF` → 不注册 `run_code`（AI 不可见，对应 sandbox.md「完全不知道能力存在」）。
2. **调用拒绝点**（`run_code` 调用入口，已注册前提下）：按当前 agent 的 `features.code_execution` 经 `is_code_execution_enabled` 判定，不可用则返回拒绝文本而不执行。

**为何**：`off` 的语义是「AI 看不见」，只能在注册层实现（不注册即不进 schema）；而 `selective`/`all` 下工具已注册，agent 级开关只能在调用入口拦截。两点对应 sandbox.md 两层控制，分离后判定逻辑收敛到一个纯函数，两个生效点都只读它。
**Alternatives**：①只在调用入口统一拦截、`off` 也注册但拒绝——被否，违反「AI 完全不知道能力存在」（schema 里仍会出现 run_code）；②每个 agent 动态构建独立 schema——被否，注册是全局 import 副作用，per-agent schema 改造范围过大，agent 级控制用调用入口拦截已足够。

### D2：Docker 可用性探测放在 SandboxClient，启动期调用一次
`SandboxClient.docker_available() -> bool`：执行轻量探测（`docker version` 或 `docker info`，仅看 returncode），任何异常（FileNotFoundError / 非零退出）返回 False 并 log 警告，不抛。启动期（server lifespan / CLI run）先探测，再 `resolve_effective_mode`。
**为何**：探测是 Docker CLI 交互，归属 `SandboxClient` 职责；启动期一次性探测避免每次调用都探测的开销，且 sandbox.md 的降级是「平台启动」事件。
**Alternatives**：每次 `run_code` 探测——被否，开销大且 sandbox.md 把降级定为启动期决策。**Trade-off**：启动后 Docker 才挂掉不会动态再降级（仍会在 `create_workspace` 抛错）——接受，属运行期故障，由执行错误路径处理（未来 SB 错误分类承接）。

### D3：agent_store 增 `features` JSON 列，向后兼容
`Agent` 数据类增 `features: dict[str, Any]`（默认 `{}`）；建表 SQL 增 `features TEXT`；读取时 `json.loads(row[...] or "{}")`，旧行（无该列值）回退 `{}`。沿用既有 `allowed_tools` 用 `json.dumps`/`json.loads` 存取的同款模式（裸 SQL，无 ORM）。
**为何**：`features` 是可扩展的 agent 能力开关容器（当前只放 `code_execution`，未来可放别的特性，SB5 复用放 `sandbox_env`），用 JSON 列避免每加一个特性就 ALTER 一列。与现有 `allowed_tools` 列的存取惯例一致。
**Alternatives**：单列 `code_execution BOOLEAN`——被否，未来每个特性都要加列、迁移成本高；features JSON 列更契合「features.*」的命名空间语义。

**Decision（旧库迁移，已定调，不再是 Open Question）**：核实确认 `agent_store._init_db` 用 `CREATE TABLE IF NOT EXISTS agents (...)`——对已存在的旧表**不会**新增列，旧库直接读 `row[features]` 会越界（IndexError）。因此**必须显式 ALTER 迁移**：`_init_db` 在建表后执行 `ALTER TABLE agents ADD COLUMN features TEXT`（包在「列已存在则忽略」的幂等判断里，如先 `PRAGMA table_info(agents)` 查列、缺则 ALTER）；读取统一 `json.loads(row[...] or "{}")` 兜底旧行。这是本 change 的明确 tasks（见 tasks.md 4.x），不留作 OQ。

### D4：mode 配置项与默认值
新增沙箱 `mode` 配置（默认 `all`，与 sandbox.md 默认一致），经既有配置加载（参考 `model_router` 的 yaml 加载与 `config.Settings` 惯例）读入，路径/默认值常量可 monkeypatch。
**为何**：默认 `all` 保持现状「所有 agent 可用」的可观察行为不变（叠加 Docker 探测降级作为安全兜底）。`sandbox.mode` 写入 `config/settings.yaml` 的 `sandbox:` 段——**本 change 作为首个落地者建立该 `sandbox:` 段骨架**，SB2 追加 `scope`/`idle_hours`、SB4 追加 `resources`，三方共用同一段。

### D5：run_code 上下文通道由本 change 拥有并实现（已定调，非 Open Question）
核实确认 `tool_registry.dispatch(name, arguments_json, allowed_tools, is_sub_agent)` 与 `run_code(code)` 当前都**不**透传 agent/session 上下文——调用拒绝点要按当前 agent 的 `features.code_execution` 判定，必须有一条上下文通道。本 change **确定需补该通道**并拥有其实现：
- 改造范围（写入 Impact）：`agent_loop.py`（调用 `_safe_dispatch`/`dispatch` 处带上当前 agent 标识、agent features、session_id）→ `tool_registry.dispatch`（增加上下文入参并向被调工具传递，对不需要上下文的工具透明）→ `tools.run_code`（据上下文取 features 做启用判定）。
- 缺省上下文（无 agent 绑定的直接调用）安全降级为全局 mode 默认，不抛异常。

**为何**：启用判定的「调用拒绝点」依赖 agent features，没有上下文通道就无法实现 agent 级开关。该通道是 SB 治理轨多个 change 的共享改造（SB2 的 scope `acquire` 需 session_id/agent_name，SB5 的 agent_env 需 agent features），由本 change 统一拥有、单点改造，SB2/SB5 复用，避免各自重造 dispatch 签名。
**Alternatives**：每个 change 各改 dispatch——被否，dispatch 签名是单点，多方各改会冲突；用模块级全局存当前 agent——被否，违反 CLAUDE.md「禁止全局可变状态」且并发不安全（per-session 上下文）。

## Risks / Trade-offs

- [默认 `all` + Docker 不可用降级，可能让原本期望「报错」的部署变成「AI 看不见 run_code」] → 这正是 sandbox.md 期望的优雅降级；启动时 log 警告，运维可见。
- [agent_store 加列对旧库的兼容] → 读取统一 `or "{}"` 回退；建表用 `IF NOT EXISTS` + 迁移核实（Open Question）；扩充 test_agent_store 覆盖旧行读取。
- [注册点降级判定与运行期 Docker 故障不一致] → 启动期降级为主路径；运行期故障走执行错误路径，本 change 不承接（未来错误分类）。
- [`is_code_execution_enabled` 的 None 语义（ALL 下 None 视为开）易被误读] → spec 用独立 scenario 钉死「未声明在 all 下默认开、在 selective 下默认关」，并加单测覆盖三态 × {True/False/None}。

## Open Questions

- `off` 降级后是否需要在 `/health` 或启动日志显式暴露「sandbox mode=off (docker unavailable)」供运维探活？（建议是，待确认 health 输出格式）

> 已定调（不再是 OQ）：① 旧库 schema 迁移——确认需显式 `ALTER TABLE ADD COLUMN`（D3）；② run_code 上下文通道——确认需补，本 change 拥有并实现（D5）。
