## Context

现有三个独立 binary 入口：
- `fleetent`（`src/fleetent/__main__.py`）：已有 `agent init/run/restart/stop` 子命令 + 一次性 fallback
- `fleetent-admin`（`src/fleetent/platform/admin_cli/main.py`）：12 个 CLI 模块，`register/handle` 模式
- `fleetent-node`（`src/fleetent/node/app.py`）：node supervisor 入口

`__main__.py` 的调度逻辑是手写 `argv` 匹配，没有 argparse 框架（`if argv[:2] == ["agent", "run"]:`），现有 `agent` 子命令组就是这种模式。

`fleetent-admin` 的 CLI 模块架构清晰（每个 `register(subparsers)` + `handle(args)` 函数），可以整体移植进新的子命令组而不需要修改各模块内部实现。

`add-platform-admin-apis` 落地后，18 条 B 类命令有 HTTP API 等价路径，可以从 CLI 删除。

## Goals / Non-Goals

**Goals:**
- `fleetent admin <cmd>` 成为 `fleetent-admin <cmd>` 的替代入口，行为等价
- `fleetent node start` 成为 `fleetent-node` 的替代入口
- 删除 18 条 B 类冗余 CLI 命令（HTTP API 已覆盖）
- `fleetent-admin`/`fleetent-node` 降级为 deprecation shim，打印迁移提示后转发

**Non-Goals:**
- 修改任何 CLI 命令的内部实现逻辑（只改命名空间和入口）
- 将 admin CLI 迁移到 argparse 以外的框架
- 修改 HTTP API（由 `add-platform-admin-apis` 处理）
- 删除 `fleetent-tui`（已是独立 PARKED 决策）

## Decisions

### D1：`fleetent admin` 作为整体转发，不逐命令重新注册

`__main__.py` 中检测到 `argv[0] == "admin"` 时，懒加载 `platform.admin_cli.main` 并将 `argv[1:]` 转发给其 `main()` 函数（修改 `sys.argv` 后调用，或直接传参）。**不**把 12 个 CLI 模块逐一在 `__main__.py` 里重新注册——复用整个 admin CLI 的 argparse 树，避免双重维护。

这要求 admin CLI main 支持被调用时接受外部 argv，而不只读 `sys.argv`。改造 `platform/admin_cli/main.py` 的 `main()` 接受可选 `argv: list[str] | None = None` 参数。

### D2：懒加载隔离，避免污染 agent runtime 启动路径

`__main__.py` 顶部只有 `from fleetent.runtime import run_sync`（一次性 fallback 用）。admin 和 node 子命令的 import 全部延迟到进入对应分支时执行（`if argv[0] == "admin": from fleetent.platform.admin_cli import main as admin_main`）。确保 `fleetent agent run` 不触发 platform 代码加载。

### D3：deprecation shim 在 `pyproject.toml` 中保留脚本条目，函数体打印警告后转发

```python
# src/fleetent/_shims.py
def fleetent_admin_shim() -> None:
    import sys, warnings
    warnings.warn(
        "fleetent-admin is deprecated; use: fleetent admin <cmd>",
        DeprecationWarning, stacklevel=1,
    )
    sys.argv = ["fleetent", "admin"] + sys.argv[1:]
    from fleetent.__main__ import main
    main()
```

`pyproject.toml` 中 `fleetent-admin` 指向 `fleetent._shims:fleetent_admin_shim`。`fleetent-node` 同理转发到 `fleetent node start`。

### D4：B 类命令删除方式——只从 `register()` 中移除，不删模块文件

18 条 B 类命令分散在各 CLI 模块（`agents.py`、`users.py`、`nodes.py`、`kb_connectors.py`、`observability.py`、`im.py`）。只在各模块的 `register()` 函数中删掉对应的 `add_parser` 调用和 `handle()` 中对应的分支。模块文件本身保留（其他命令还在）。

例外：`observability.py` 的所有命令均为 B 类，整个模块从 `_COMMAND_MODULES` 列表移除（但文件留着，作为历史参考，不做 shim）。

### D5：`fleetent node` 子命令组，`start` 是主命令

```
fleetent node start      # 启动 node supervisor（等价 fleetent-node）
fleetent node status     # （未来扩展槽位，本 change 暂不实现）
```

本 change 只实现 `fleetent node start`，调用 `node.app.main()`。

## Risks / Trade-offs

- **`fleetent-admin` shim 的 `sys.argv` 替换**：shim 通过修改 `sys.argv` 转发命令，部分极端情况（argparse 读 `sys.argv[0]` 做 prog 名称）可能显示 `fleetent admin` 而非 `fleetent-admin`，属预期行为（就是要引导迁移）。→ 无实质功能影响。
- **B 类删除的时机**：本 change 和 `add-platform-admin-apis` 同步推进，apply 时必须确认前者已落地。tasks.md 中显式标注前置条件。→ apply 提示词里注明。
- **`observability.py` 模块整体移除**：该模块的所有命令均被 HTTP API 覆盖，直接从 `_COMMAND_MODULES` 移除。如果日后新增 observability CLI 操作，需重新加回。→ 文件保留、只移出注册，重新加回成本低。

## Migration Plan

1. 先改 `admin_cli/main.py` 支持外部 argv
2. 再改 `__main__.py` 接入 `admin` / `node` 子命令
3. 再删 B 类命令（各模块 `register`/`handle` 中移除）
4. 再写 shim 函数 + 改 `pyproject.toml`
5. 每步均有对应测试（见 tasks.md）
6. 最终收尾：`make test-pr` + integration 套件无新增失败
