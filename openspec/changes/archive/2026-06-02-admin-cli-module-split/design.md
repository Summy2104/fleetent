## Context

当前 `fleetent-admin` console script 指向：

```toml
fleetent-admin = "fleetent.admin:main"
```

`fleetent.admin.main()` 在一个文件里完成所有 parser 构造、命令执行和 helper 定义。当前测试集中在
`tests/integration/test_admin.py`，覆盖用户、IM、schedule、agent/channel、KB connector、diagnostics 和
observability CLI 行为。

本 change 的目标是降低文件冲突和维护成本，不改变产品语义。

## Target Structure

目标结构：

```text
src/fleetent/platform/
  __init__.py
  admin_cli/
    __init__.py
    main.py
    common.py
    users.py
    im.py
    agents.py
    schedules.py
    kb_connectors.py
    diagnostics.py
    observability.py

src/fleetent/admin.py
```

`src/fleetent/admin.py` 只保留：

```python
from fleetent.platform.admin_cli.main import main

__all__ = ["main"]
```

## Command Module Contract

每个命令域模块提供两个函数：

```python
def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register commands owned by this domain."""


def handle(args: argparse.Namespace) -> bool:
    """Handle args if this module owns the command; return True when handled."""
```

`main.py` 负责：

1. 创建 root parser。
2. 调用各模块 `register()`。
3. 解析 args。
4. 依次调用各模块 `handle(args)`。
5. 如果没有模块处理，调用 parser error 或返回非 0。

为了避免过度抽象，第一版可以使用简单 if 分发。重点是文件拆分，不是构建 CLI framework。

## Shared Helpers

`common.py` 放共享 helper：

- `sanitize_cli_value(value)`
- `summary_line(summary)`
- `parse_iso_time(value, flag)`
- `format_optional(value)`
- `payload_keys(payload)`

共享 helper 不访问数据库、不读配置、不调用业务 API。

## Domain Ownership

| Module | Commands |
| --- | --- |
| `users.py` | `create-user`、`list-users`、`rotate-key`、`seed-builtin-admin` |
| `im.py` | `list-pending`、`approve-user`、`block-user` |
| `agents.py` | `assign-channel`、`unassign-channel`、`set-default-agent` |
| `schedules.py` | `list-schedules`、`add-schedule`、`remove-schedule` |
| `kb_connectors.py` | `kb connectors list/check/status/sync` |
| `diagnostics.py` | `diagnostics export`、`diagnostics retention dry-run/apply` |
| `observability.py` | `observability traces/usage/performance` |

## Compatibility

必须保持：

- `uv run fleetent-admin ...` 行为不变。
- `from fleetent.admin import main` 可用。
- 测试中 monkeypatch `fleetent.admin._SETTINGS_YAML` 的旧路径需要迁移到新模块路径。

对于 `_SETTINGS_YAML`，建议：

- 实际变量移动到 `platform.admin_cli.agents._SETTINGS_YAML`。
- `_SETTINGS_YAML` 不作为 public API 保留在 `fleetent.admin` shim 中。
- 测试同步更新到新路径，避免 shim 承载可变状态。

## Testing

TDD 顺序：

1. 先写失败测试，证明新 package entrypoint 可 import。
2. 先写失败测试，证明 `fleetent.admin.main` 仍指向新入口。
3. 先写失败测试，证明旧 CLI 行为仍通过现有 `run_admin()` helper。
4. 迁移文件。
5. 跑 `tests/integration/test_admin.py`。
6. 跑完整测试。

迁移过程中不要修改输出文案，除非现有测试明确要求。

## Non-Goals

本 change 不解决：

- admin CLI 权限模型。
- Admin Web UI。
- JSON output mode。
- shell completion。
- 统一 command registry 框架。
- 用户 / agent / schedule store 迁移。
