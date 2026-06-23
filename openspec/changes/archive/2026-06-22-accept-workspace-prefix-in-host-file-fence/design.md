# Design — accept-workspace-prefix-in-host-file-fence

## 问题
`resolve_host_path(root, path)`(file_sandbox_io.py:123）：
```python
base = os.path.normpath(str(root))
candidate = os.path.normpath(path) if os.path.isabs(path) else os.path.normpath(os.path.join(base, path))
if candidate != base and not candidate.startswith(base + os.sep):
    raise ValueError(f"path escapes workspace: {path!r}")
```
`/workspace/outbound/x.png` 是绝对路径 → candidate=`/workspace/outbound/x.png` → 不以 host `base` 开头 → 拒。但模型在容器单根 `/workspace` 世界里产出该路径是合理的(playwright/run_code 都这么报路径)。

## 决策

### D1. 剥 `/workspace` 前缀后按 root 相对解析
在绝对/相对判定**之前**插入前缀映射：
```python
base = os.path.normpath(str(root))
if path == WORKSPACE:
    path = ""
elif path.startswith(WORKSPACE + "/"):
    path = path[len(WORKSPACE) + 1 :]
candidate = os.path.normpath(path) if (path and os.path.isabs(path)) else os.path.normpath(os.path.join(base, path))
if candidate != base and not candidate.startswith(base + os.sep):
    raise ValueError(f"path escapes workspace: {path!r}")
return Path(candidate)
```
- `/workspace/outbound/x.png` → `path="outbound/x.png"` → join(base,...) → `<root>/outbound/x.png` ✅
- `/workspace` → `path=""` → join(base,"")=base → 返回 root ✅
- `/workspace/../etc` → `path="../etc"` → join → normpath 逃出 base → **拒**（`..` 仍挡）
- `/workspace-evil/x` → 不匹配 `/workspace/` 前缀 → 走绝对分支 → 不在 base → **拒**（仿冒仍挡）
- `/etc/passwd` → 不匹配前缀 → 绝对 → 拒 ✅
- 相对 `a/b.txt` / `.` → 行为不变 ✅

只动宿主侧；容器侧 `resolve_ws_path` 已接受 `/workspace/` 前缀,不改。

### D2. 围栏不放松
唯一新增的「接受」是确切的 `/workspace` 挂载点前缀映射到本 session 的 root；任何 `..` 归一化逃逸、非 `/workspace/` 的绝对路径、`/workspace` 仿冒前缀仍按原逻辑拒绝。

## 测试策略（unit，扩 test_file_sandbox_io.py）
- `resolve_host_path(tmp, "/workspace/a/b.txt") == tmp/a/b.txt`
- `resolve_host_path(tmp, "/workspace") == tmp`
- `/workspace/../escape.txt` → ValueError（越界）
- `/workspace-evil/x` → ValueError（仿冒，回归保护）
- 既有相对/`.`/`/etc/passwd`/`..` 用例不回归。

## 可观测信号
send_file / read_file / write_file 收到 `/workspace/<rel>` 时按宿主 root 正确解析,不再 `path escapes workspace`;越界/仿冒仍拒。
