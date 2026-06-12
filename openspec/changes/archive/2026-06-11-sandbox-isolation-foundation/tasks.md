## 1. 无碰撞 key 派生（容器名 + workspace 目录）

- [x] 1.1 写 unit 测试:key 派生函数对两个仅在 >48 字符前缀之后不同的 key 产出不同结果，锁定无碰撞（先见红）
- [x] 1.2 在 `integrations/sandbox/manager.py` 实现"可读前缀 + 完整未截断 key 的 sha256 后缀"派生函数（总长压在 docker 63 / 文件系统目录名上限内），收口 `_sanitise` 用途，使 `_container_name` 与 `workspace_host_path` 共用同一函数（见绿）
- [x] 1.3 写 integration 测试:同前缀双 session key 经 `acquire` 取得名称不同、相互隔离的容器，且 `workspace_host_path` 返回不同子目录，一方写入 `/workspace` 对另一方容器不可见
- [x] 1.4 跑通 1.3，必要时调派生长度预算；确认 `sandbox-orphan-cleanup` 仍能识别新命名容器

## 2. 运行时封闭性门控（sandbox_capable）

- [x] 2.1 写 unit 测试:`runtime_sandbox_capable(tool, effective_mode, backend_caps)` —— `effective_mode=OFF` 或后端无 `workspace_mount` → False；容器内执行 → True（先见红）
- [x] 2.2 实现该 helper，在 `runtime/loop.py` `_plan_run_slots` 用它替换 `sandbox_capable=is_sandbox_backed(name)`；`effective_mode` 经 `get_effective_mode()` 每 run 取一次并缓存传入（见绿）
- [x] 2.3 写 integration 测试:`effective_mode=OFF` 时被配置为 `sandbox` mode 的 medium 操作经 action gate 升 `APPROVAL`；封闭成立时按 `SANDBOX` 直跑不审批
- [x] 2.4 跑通 2.3，覆盖 microsandbox/无 mount 后端分支；确认未改 `action_gate.resolve_action_mode` 契约（仅改喂入真值）

## 3. workspace GC（按 scope 回收）

- [x] 3.1 写 unit 测试:GC 纯逻辑 —— scope 分派（session 整删 / agent 按 mtime）、`is_blocked_mount` + realpath 越界/敏感路径拦截拒删（先见红）
- [x] 3.2 在 `integrations/sandbox` 维护路径实现 workspace GC 入口:session 整目录 `rmtree`（先经既有释放路径销活跃容器）、agent 按 mtime 目录内清理、删除前双护栏（`is_blocked_mount` + realpath 落在 `workspaces` 根内），暴露 public API（见绿）
- [x] 3.3 写 integration 测试:会话 TTL 过期触发其 `session` scope workspace 整目录回收（含 uploads/产物）；`agent` scope 仅清理超保留期文件、保留近期内容与目录本身；未过期会话目录不动
- [x] 3.4 在既有会话过期点（`session-ttl-cleanup` / `internal-session-maintenance`）与 idle sweep 经 sandbox **public API** 接入 GC，跑通 3.3；确认 `session/` 不 import sandbox internal

## 4. 边界与收尾

- [x] 4.1 跑 `scripts/check_module_boundaries.py` 无新增跨包 internal import；冒烟:agent 在无 platform、platform 表不存在环境下 `fleetent agent run` 仍可完成一轮对话
- [x] 4.2 `ruff format` + `ruff check` 改动文件、`mypy src` 通过
- [x] 4.3 `make test-pr` 全绿（对照 main 基线无新增失败）+ `uv run pytest tests/integration -q` 无新增失败
- [x] 4.4 `openspec validate sandbox-isolation-foundation --strict` 通过
