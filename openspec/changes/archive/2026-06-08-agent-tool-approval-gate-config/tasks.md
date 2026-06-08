## 1. permission_gate.py — 支持 timeout override

- [x] 1.1 Write failing test: `PermissionGate.request_approval()` 传入 `medium_timeout=1` 时，1 秒后
  自动 reject（mock `reply_func`，`asyncio.wait_for` 超时路径）
- [x] 1.2 Run test → 确认红（当前 `request_approval` 不接受 timeout override）
- [x] 1.3 在 `PermissionGate.request_approval()` 中新增可选参数
  `medium_timeout: float | None = None` / `high_timeout: float | None = None`；
  若传入则覆盖 `self._medium_timeout` / `self._high_timeout`
- [x] 1.4 Run test → 确认绿；运行 `uv run pytest tests/unit -x -q`
- [x] 1.5 Commit: `feat(permission-gate): add per-call timeout override to request_approval`

## 2. agent_config.py — 新增 permission_gate_enabled 字段

- [x] 2.1 Write failing test: `AgentFile` 加载含 `permission_gate_enabled: false` 的 yaml 后，
  `agent.permission_gate_enabled` 为 `False`；不含该字段时默认 `True`
- [x] 2.2 Run test → 确认红（字段不存在）
- [x] 2.3 在 `AgentFile` 的 permission gate 字段区块（`permission_gate_medium_timeout_seconds`
  旁）添加 `permission_gate_enabled: bool = True`
- [x] 2.4 Run test → 确认绿；运行 `uv run pytest tests/unit -x -q`
- [x] 2.5 Commit: `feat(agent-config): add permission_gate_enabled field to AgentFile`

## 3. loop.py — 透传 gate 开关和 timeout

- [x] 3.1 Write failing test: `loop.run()` 传入 `permission_gate_enabled=False` 时，medium-risk
  工具被调用后直接返回结果，不调用 `_default_gate.request_approval`（mock gate + reply_func）
- [x] 3.2 Run test → 确认红（loop 不接受该参数）
- [x] 3.3 在 `loop.run()` 签名中添加 `permission_gate_enabled: bool = True`，
  `permission_gate_medium_timeout: int | None = None`，
  `permission_gate_high_timeout: int | None = None`；
  传给 `_plan_tool_slots()` 的调用处
- [x] 3.4 在 `_plan_tool_slots()` 签名中添加对应参数；
  gate 条件改为：
  `if (risk in ("medium", "high") or force_ask) and reply_func is not None and permission_gate_enabled:`；
  调用 `_default_gate.request_approval()` 时传入 timeout override
- [x] 3.5 Run test → 确认绿；运行 `uv run pytest tests/unit -x -q`
- [x] 3.6 Write test: 传入 `permission_gate_medium_timeout=1` 时，gate request_approval 收到对应
  override（验证参数透传，mock gate）
- [x] 3.7 Run test → 确认绿
- [x] 3.8 Commit: `feat(loop): add permission_gate_enabled and timeout params to run()`

## 4. normalizer.py + agent_app.py — 读配置并传参

- [x] 4.1 Write failing test（unit）: `normalizer.route()` 转发含 `permission_gate_enabled=False`
  的 agent 时，`loop.run()` 收到 `permission_gate_enabled=False`（mock loop.run）
- [x] 4.2 Run test → 确认红
- [x] 4.3 在 `normalizer.route()` 中从 `agent` 读取 `permission_gate_enabled`、
  `permission_gate_medium_timeout_seconds`、`permission_gate_high_timeout_seconds`，
  传入 `agent_loop.run()` 调用
- [x] 4.4 Run test → 确认绿；运行 `uv run pytest tests/unit -x -q`
- [x] 4.5 Write failing test（unit）: `agent_app.py` `/chat` 路由读取 agent
  `permission_gate_enabled=False` 并传给 `run_stream()`（或 `run()`）——
  注：`run_stream` 无 gate，若 `/chat` 走 `run_stream`，此步骤验证字段读取即可
- [x] 4.6 Run test → 确认绿；运行 `uv run pytest tests/unit -x -q`
- [x] 4.7 Commit: `feat(normalizer,agent-app): propagate permission_gate config from agent.yaml`

## 5. agent.yaml.example 补充注释

- [x] 5.1 在 `agents/default/agent.yaml.example` 的 permission gate 区块（
  `permission_gate_medium_timeout_seconds` 附近）补充 `permission_gate_enabled: true` 示例行
  及注释（说明 false 时跳过审批）
- [x] 5.2 Commit: `docs(example): add permission_gate_enabled to agent.yaml.example`

## 6. 验收与收尾

- [x] 6.1 运行 `uv run pytest -x -q` 全量测试通过
- [x] 6.2 运行 `uv run python scripts/check_test_layers.py` 确认测试分层合规
- [x] 6.3 运行 `uv run ruff format src tests && uv run ruff check src tests` lint 通过
- [x] 6.4 运行 `uv run mypy src` 类型检查通过
