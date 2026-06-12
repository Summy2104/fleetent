## 1. bash_exec 默认移除（opt-in 化）

- [x] 1.1 写 unit 测试（先见红）：工具面解析在空 `allowed_tools`（allow-all / `None`）与 `["*"]` 下**不**暴露 `bash_exec`、但暴露其余非 opt-in 工具；`allowed_tools` 显式具名命中 `bash_exec`（字面或能覆盖它的显式模式）时暴露；schema 可见性与 dispatch 放行判定一致（同一逻辑源）
- [x] 1.2 实现 opt-in 集合（初始 `{"bash_exec"}`，内聚在 governance/tools 工具面解析处，可注入便于测试）；在 per-agent 工具面解析（`check_tool_access` 调用上下文 / loop schema 组装 + dispatch 前过滤）对空 allow-all / `*` 收窄 opt-in 工具，保留"空 allow-all → `allowed_tools=None`"语义不变（见绿）
- [x] 1.3 写 integration 测试：普通 agent（`allowed_tools: []`）的 `get_schemas()` 不含 `bash_exec`、含其余工具；运维 agent（`allowed_tools` 显式列 `bash_exec`）的 `get_schemas()` 含 `bash_exec`；dispatch `bash_exec` 在前者被 `check_tool_access` 拒、在后者放行
- [x] 1.4 跑通 1.3；确认未改 `bash_exec` 执行体 / `builtin-shell-tool` 契约（执行/审批/超时/工作目录不变），仅改其默认可见性

## 2. 免审批兑现（封闭 medium → sandbox 直跑）

- [x] 2.1 写 unit 测试（先见红或锁定既有契约）：`resolve_action_mode(risk="medium", medium_mode="sandbox", sandbox_capable=True, ...)` 解析为 `ActionMode.SANDBOX`；`sandbox_capable=False` 时升 `APPROVAL`；`risk="high"` 在 `high_mode="approval"` 下仍 `APPROVAL`（验证免审批兑现完全是既有 resolver + 地基 containment 行为，不改 resolver）
- [x] 2.2 兑现"封闭即免审批"配置默认与文档（不改 `action_gate.py` / `loop.py` 机制）：更新 `agents/default/agent.yaml.example` 中 `action_gate_medium_mode` 注释为"封闭可信部署推荐 `sandbox`：容器内 medium 操作免审批，未封闭自动升审批"、`action_gate_high_mode` 注释明确"高危默认保持 approval，不随 medium 放松"；`docs/capabilities/governance.md` 补"封闭即免审批（正当性绑运行时封闭性，未封闭 fail-closed）"说明（见绿/文档落地）
- [x] 2.3 写 integration 测试：agent 配 `action_gate_medium_mode: sandbox`，运行时封闭（`sandbox_capable=True`）时某 medium 操作经 action gate 直跑不审批；`effective_mode=OFF`（无 docker）时同一操作经 fail-closed 升 `APPROVAL`（对接地基 `sandbox-containment-gating`，不改 resolver 契约）
- [x] 2.4 跑通 2.3；确认 registry risk 常量 / `is_sandbox_backed` / `SANDBOX_BACKED_TOOLS` / `resolve_action_mode` 签名与契约均未改

## 3. sandbox mode 选型指引（文档）

- [x] 3.1 在 `docs/capabilities/governance.md`（或部署文档）补"部署 mode 推荐选型"指引：封闭可信内网 + medium 免审批 → `all` + `action_gate_medium_mode: sandbox`；最小暴露 → `selective`；禁用代码执行 → `off`；明确免审批仅在封闭成立时生效、`off` 形态 medium 仍走审批
- [x] 3.2 在 `agents/default/agent.yaml.example` / platform 侧 sandbox 注释补 mode 选型指引与"封闭即免审批"交叉引用；确认未改三态语义、默认值与 `available()` 降级行为

## 4. 边界与收尾

- [x] 4.1 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 无新增跨包 internal import；冒烟：agent 在无 platform、platform 表不存在环境下 `fleetent agent run` 仍可完成一轮对话（普通 agent 默认无 `bash_exec`，容器内 medium 按配置直跑或 fail-closed）
- [x] 4.2 `uv run ruff format src tests` + `uv run ruff check src tests` 改动文件、`uv run mypy src` 通过
- [x] 4.3 `make test-pr` 全绿（对照 main 基线无新增失败）+ `uv run pytest tests/integration -q` 无新增失败
- [x] 4.4 `openspec validate sandbox-approval-relaxation --strict` 通过
