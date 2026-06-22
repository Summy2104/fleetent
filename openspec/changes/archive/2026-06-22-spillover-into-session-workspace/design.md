# Design — spillover-into-session-workspace

## 问题
`_spillover` 写 `SPILLOVER_DIR = data_dir()/tool_spillover/<uuid>.txt`(workspace 外),hint 给该**绝对路径**让 `read_file` 读 → 围栏拒(`path escapes workspace`)。容器模式 read_file 在 `/workspace` 里跑,宿主绝对路径更不可达。

## 决策

### D1. 溢出落 session workspace,hint 用 workspace 相对路径
- 主循环 finalize 持有 `scope_key`(`resolve_scope_key`)→ `host_workspace_dir(scope_key)` 得 session 宿主 workspace 目录,作为 `workspace_dir` 传入。
- `_spillover` 写 `<workspace_dir>/.fleetent_spillover/<uuid>.txt`;hint 路径用 **workspace 相对** `.fleetent_spillover/<uuid>.txt`。
  - 容器模式:`read_file` 经 `resolve_ws_path` 把相对路径 join 到 `/workspace` → `/workspace/.fleetent_spillover/<uuid>.txt`(bind-mount 同文件)→ 可读。
  - 宿主降级:经 `resolve_host_path` join 到 workspace root → 可读。
  - 相对路径对两种模式都对,避免硬编码 `/workspace` 或宿主绝对。

### D2. 无 workspace_dir 回退全局（向后兼容）
`workspace_dir is None`(无 scope_key 边角 / 既有测试不传)→ 用全局 `SPILLOVER_DIR` + 绝对路径(旧行为)。既有测试 monkeypatch `SPILLOVER_DIR` 且不传 `workspace_dir` → 行为不变、不回归。

```python
def truncate_tool_result(result, max_bytes=None, self_truncates=False, workspace_dir=None):
    ...
    if self_truncates: return _head_tail_breadcrumb(...)
    return _spillover(result, orig, limit, workspace_dir)

_SPILLOVER_SUBDIR = ".fleetent_spillover"
def _spillover(result, orig, limit, workspace_dir):
    if workspace_dir is not None:
        out_dir = Path(workspace_dir) / _SPILLOVER_SUBDIR
        hint_path = f"{_SPILLOVER_SUBDIR}/{name}"     # workspace-relative
    else:
        out_dir = SPILLOVER_DIR
        hint_path = str(out_dir / name)               # legacy absolute
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / name).write_text(result, "utf-8")
    ... hint.format(path=hint_path, ...) ...
```

### D3. loop.py 接线
两处 finalize（sync ~1060 / stream ~2953）：
```python
_ws = host_workspace_dir(scope_key) if scope_key else None   # 惰性 import
tool_content = content if is_self_truncating(slot.name) else truncate_tool_result(content, workspace_dir=_ws)
```
`host_workspace_dir` 纯计算(不 mkdir);`_spillover` 的 mkdir(parents=True) 兜底建目录。

## 测试策略（unit）

`tests/unit/test_tool_result_truncation_spillover.py` 新增（既有全局用例**不动**）：
- `truncate_tool_result(big, workspace_dir=tmp)` → 在 `tmp/.fleetent_spillover/` 下建 `<uuid>.txt`，内容为完整原文；
- 返回 hint 含 **相对路径** `.fleetent_spillover/<uuid>.txt`（不含 `tmp` 绝对前缀、不含 `data_dir`）；
- preview 前 100 行仍在；
- 不传 workspace_dir 时仍写 `SPILLOVER_DIR`（既有行为，回归）。

## 可观测信号
大 MCP 结果溢出后,hint 给的是 `.fleetent_spillover/<uuid>.txt`,agent `read_file` 能读回完整内容,不再 `path escapes workspace`;无 session 的路径回退旧全局行为。
