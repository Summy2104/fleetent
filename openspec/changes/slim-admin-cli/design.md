## Context

三个独立 binary 入口：
- `fleetent`（`src/fleetent/__main__.py`）：手写 argv 匹配（`if argv[:2] == ["agent","run"]`），已有 `agent init/run/restart/stop` + 一次性 fallback。`main()` 签名 `def main() -> None`，内部读 `sys.argv[1:]`。
- `fleetent-admin`（`platform/admin_cli/main.py`）：`main() -> None`，内部 `parser.parse_args()`（读 sys.argv），`prog="fleetent-admin"`；12 个 CLI 模块走 `register/handle` 模式。
- `fleetent-node`（`node/app.py`）：`main() -> None`，**无 argparse、无命令行参数**，全部配置经环境变量（`FLEETENT_NODE_*`）。

前置 change `complete-admin-api-coverage` 落地后，18 条命令全部有 HTTP 等价路径。

审查（2026-06-18）发现的下游引用与陷阱已并入 tasks，本节只记关键技术决策。

## Goals / Non-Goals

**Goals:**
- `fleetent admin <cmd>` / `fleetent node start` 成为统一入口，行为等价旧 binary。
- 删 18 条冗余命令，同步全仓下游引用（测试/specs/docs/脚本）使门禁与 `opsx:verify` 全绿。
- 旧入口 shim 化，迁移提示对用户可见。

**Non-Goals:**
- 改任何保留命令的内部逻辑。
- 删 `fleetent-tui`（独立 PARKED 决策）。
- 删仍 CLI-only 保留的管理/维护命令（tenants/node/memory-shared/kb-extract/diagnostics/maintenance）。

## Decisions

### D1：`fleetent admin` 整体转发 + admin main 参数化

`__main__.py` 检测 `argv[0] == "admin"` 时懒加载 `platform.admin_cli.main`，调用 `admin_main.main(argv[1:])`。`admin_cli/main.py` 的 `main()` 改签名 `def main(argv: list[str] | None = None)`，`None` 时 fallback `sys.argv[1:]`，并把 `argv` 传给 `parser.parse_args(argv)`。复用整棵 admin argparse 树，不在 `__main__.py` 重新注册 12 个模块。

**prog 名修正**：`admin_cli/main.py` 的 `ArgumentParser(prog=...)` 改为可参数化（`main(argv=None, prog="fleetent admin")`）。否则 `fleetent admin --help` 的 usage 行会显示 `fleetent-admin`，与新命名空间自相矛盾。shim 调用时传 `prog="fleetent-admin"` 保持旧提示。

### D2：懒加载隔离 agent runtime 启动路径

admin / node 子命令的 import 全部延迟到进入对应分支（`if argv[0]=="admin": from fleetent.platform.admin_cli import main as admin_main`）。`fleetent agent run` 不得触发 platform import。

**测试写法（明确指定，避免 flaky）**：`test_agent_run_does_not_import_platform` 用**同进程**：测试内先 `sys.modules.pop("fleetent.platform.admin_cli", None)`，`monkeypatch` 掉 `agent_app.serve`（避免真启动），调度到 `agent run` 分支后断言 `"fleetent.platform.admin_cli" not in sys.modules`。不要用子进程（属 integration 且慢），也不要裸断言（其他测试可能已污染 sys.modules）。与既有护栏 `test_module_dependency_guardrails.py` 互补（后者管 import 静态依赖，本测试管运行时懒加载时机）。

### D3：deprecation shim 用 stderr print，不用 warnings.warn

```python
# src/fleetent/_shims.py
import sys

def fleetent_admin_shim() -> None:
    print("Deprecated: 'fleetent-admin' → use 'fleetent admin'.", file=sys.stderr)
    sys.argv = ["fleetent", "admin", *sys.argv[1:]]
    from fleetent.__main__ import main
    main()

def fleetent_node_shim() -> None:
    print("Deprecated: 'fleetent-node' → use 'fleetent node start'.", file=sys.stderr)
    sys.argv = ["fleetent", "node", "start", *sys.argv[1:]]
    from fleetent.__main__ import main
    main()
```

**关键**：Python 默认过滤 `DeprecationWarning`（除非 `-W` 或在 `__main__`），`warnings.warn(...)` **不保证打到 stderr**。spec 验收要求"stderr 打印提示"，故用 `print(file=sys.stderr)`。`pyproject.toml` 的 `fleetent-admin`/`fleetent-node` 指向这两个 shim。

### D4：删 B 类命令——只动 register/handle，保留模块文件

18 条命令分散在 `users.py`/`agents.py`/`kb_connectors.py`/`observability.py`。只删各模块 `register()` 的 `add_parser` 和 `handle()` 对应分支。`observability.py` 全部命令是 B 类 → 从 `_COMMAND_MODULES` 移除该模块（文件保留）。`kb_connectors.py` 保留 `extract-entities`，只删 `connectors` 子命令。

### D5：`fleetent node start` 直调 node.app.main()

`node/app.py` 无命令行参数（全环境变量），`fleetent node start` 直接 `node_app.main()` 即可。`fleetent node` 不带 `start` 或带多余参数时报用法错误。**不**预留 `node status` 槽位（node app 无此能力，避免臆想接口）。

## Risks / Trade-offs

- **[下游 242 处引用]** 本 change 真正的重头是同步测试/specs/docs/脚本，而非入口改造。tasks 已逐类列出；漏改任一类会导致 `make test-pr`（unit 硬断言）、`opsx:verify`（specs 不符）或文档测试红。→ tasks 分组覆盖，收尾跑 integration 对照基线。
- **[AGENTS.md 并发编辑]** `AGENTS.md` 是项目指令文件，apply 在 worktree 改它时主会话不得同时改，否则 merge 冲突。→ apply 提示词里点明该文件只由执行会话改。
- **[shim sys.argv 替换]** shim 改 `sys.argv` 后 argparse 的 prog 可能显示 `fleetent`——可接受（就是引导迁移）。
- **[entry-point 改动需 uv sync]** `pyproject.toml` 改 scripts 后需 `uv sync` 才让 shell 命令生效；shim 函数本身可单测，端到端命令需手动验证（tasks 标注）。

## Migration Plan

1. 确认前置 `complete-admin-api-coverage` 已在 main
2. admin main 参数化 + prog 修正 → `__main__.py` 接 admin/node 子命令
3. 删 18 条命令 → 同步 specs delta
4. shim（stderr）+ pyproject + uv sync
5. 同步下游：entry-point 测试、integration 测试、文档测试、文档、Makefile、install 脚本
6. 收尾：`make test-pr` + `make test-unit-ci` + integration 对照基线 + `opsx:verify`
