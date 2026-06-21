# Design — translate-workspace-relative-paths-for-stdio-mcp-args

## 问题精确化（端到端实测取证）

本次 live run 的 `email__send_email` pending tool_args（session meta）：
```json
"attachments": ["generated/5f5b0f1c97c4446c9cb3edd15bad92e5.png"]
```
文件真实存在于 `host_workspace_dir/generated/5f5b0f1c…png`（928KB）。但 `_translate_workspace_arg` 对它 no-op（实测 `翻译了吗? False`）——它只认 `/workspace` 绝对前缀。模型这次没加 `/workspace/` 前缀（image-gen 返回的就是相对 `generated/<uuid>.png`），于是落进缺口。

## 决策

### D1. 相对路径用「存在性 + containment」消歧，只翻译真实 workspace 文件
绝对前缀 `/workspace/...` 是确定性信号，直接翻译；相对路径无前缀、语义模糊（可能是路径，也可能是普通文本）。安全做法：仅当相对值解析到 **workspace 内真实文件** 时才翻译。

```python
def _translate_workspace_arg(value: str, host_dir: Path) -> str:
    if value == _WORKSPACE_PREFIX:
        return str(host_dir)
    if value.startswith(_WORKSPACE_PREFIX + "/"):
        return str(host_dir / value[len(_WORKSPACE_PREFIX) + 1 :])
    # workspace-relative ref (e.g. image-gen "generated/<uuid>.png") the model passes
    # verbatim. Translate ONLY when it resolves to a real file inside the workspace —
    # existence + containment disambiguate from ordinary string args.
    if value and not value.startswith("/") and "\n" not in value:
        base = os.path.normpath(str(host_dir))
        candidate = os.path.normpath(os.path.join(base, value))
        if (candidate == base or candidate.startswith(base + os.sep)) and os.path.isfile(candidate):
            return candidate
    return value
```

- **消歧**：`可爱小狗` / 多行正文 / `dev-intern` 等都不是 workspace 下的真实文件 → 不翻译。换行值直接短路（路径不含换行）。
- **防穿越**：`os.path.normpath` 归一后必须仍在 `host_dir` 内（`== base` 或 `base + sep` 前缀），否则不翻译（挡 `../../etc/passwd`）。
- **不碰绝对非 workspace**：`/etc/hosts` 以 `/` 开头且非 `/workspace`，走不到相对分支，原样保留。
- 用 `os.path`（不 `Path.resolve()`）避免跟随符号链接带来的逃逸面，且与既有 `artifact_exchange.resolve` 的 normpath 风格一致。

### D2. 仅扩 `_translate_workspace_arg`，不动调用方
chokepoint 已对 stdio + scope_key 调 `_translate_workspace_args(args, host_workspace_dir(scope_key))`（#280/#282）。本 change 只改叶子翻译函数,递归遍历、stdio/http 门控、scope_key 解析全不变。

## 测试策略（unit，扩 test_mcp_exchange_injection.py）

`host_dir=tmp_path`，在其下真实建文件后断言：
1. `generated/x.png` 存在 → 翻译为 `str(tmp/generated/x.png)`。
2. 相对但**不存在**的 `nope.png` → 原样不变。
3. 普通文本 `可爱小狗` / 多行 `"Hi,\n\n…"` → 原样不变。
4. `../escape.png`（即便构造一个 tmp 外的真实文件）→ 不翻译（containment 拒绝）。
5. `/workspace/a.png` 绝对前缀仍翻译（回归 #280）；`/etc/hosts` 原样。
6. `_translate_workspace_args` 递归：dict/list 内的相对真实文件被翻译,其余不动。

均纯函数 + tmp 文件,无 DB/HTTP,合 unit 边界。

## 可观测信号
修复后：模型传相对 `generated/<uuid>.png` 时,email server 收到 `host_workspace_dir/generated/<uuid>.png`（真实可读）→ 附件成功；不再因相对路径 no-op 而 `Attachment file not found`。绝对路径行为不变。
