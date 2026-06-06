## Why

`skill_admin_api.py` 中两个关键 engine seam 是 no-op stub：`engine_reload()` 调用破坏原子性的 `scan()` 而非 `reload()`，`engine_audit()` 永远返回 `pass` 而非执行真实的静态注入检测。这使热重载在并发下有空窗期、上传路径的安全审计形同虚设。

## What Changes

- `engine_reload()`：改为调用 `skill_registry.reload()`（原子替换全局 `_index`），而非 `skill_registry.scan()`（破坏性 clear+update）
- `engine_audit(content)`：改为调用 `skill_audit.audit(content)` 执行真实静态规则扫描，而非返回固定 `{"verdict": "pass", "rules": []}`

## Capabilities

### New Capabilities

无新 capability。

### Modified Capabilities

- `skill-hot-reload`：明确要求 `engine_reload()` 调用原子 `reload()` 而非破坏性 `scan()`
- `skill-injection-audit`：明确要求管理台上传/编辑路径必须执行真实 `audit()` 检测

## Impact

- **修改文件**：`src/fleetent/platform/skill_management/skill_admin_api.py`（2 处 seam 实现，各约 1 行）
- **测试**：`tests/unit/`（mock 验证 seam 调用正确的下游函数）
- **无破坏性变更**：`engine_reload` 和 `engine_audit` 的对外签名不变，只有实现替换
