## 1. 前置核实（无代码改动）

- [x] 1.1 核实 `run_code` 输出组装处（`builtin_tools.py` 返回前的 `truncate_stream` 拼接）与 trace `log_sandbox_exec` 只记大小不记内容；确认脱敏插入点（先脱敏后截断）
- [x] 1.2 核实 `secrets.py` 模块级可扩展模式风格与 `test_tools.py` 的 run_code mock harness（`_make_manager` + `client.exec` 返回 `ExecResult`）

## 2. 脱敏模块（integrations/sandbox/redaction.py）

- [x] 2.1 Write failing tests（`tests/unit/test_sandbox_redaction.py`）：`redact_secrets` 脱敏——PEM 私钥块整段、JWT 三段、厂商前缀（`sk-`/`ghp_`/`AKIA…`）、`scheme://user:pass@host` 的密码段、`Authorization: Bearer X` 的凭证（保留头名）、命名型 `API_KEY=x`/`DB_PASSWORD=x`（保留键名）；**不误伤**普通文本（散文/数字/`AUTHOR=jane`/`MONKEY=1` 不被改）。运行看红
- [x] 2.2 Implement `redaction.py`（模块级 `(pattern, replacement)` 列表 + `redact_secrets`，结构化高精度 + 命名型保守、不含裸 KEY/AUTH），看绿

## 3. 公共 API 导出（integrations/sandbox/__init__.py）

- [x] 3.1 Write failing test：`from fleetent.integrations.sandbox import redact_secrets` 可用。看红
- [x] 3.2 Implement `__init__` 导出 + `__all__`，看绿

## 4. run_code 接线（tools/builtin_tools.py）

- [x] 4.1 Write failing test（`tests/unit/test_tools.py` run_code 段）：`client.exec` 返回 stdout 含 `sk-` key、stderr 含 `Authorization: Bearer …` 的 `ExecResult` → `run_code` 返回值中两者均被占位符替换；普通输出用例仍原样返回。沿用 `_make_manager` + `monkeypatch tl._MANAGER`。看红
- [x] 4.2 Implement：`run_code` 对 stdout/stderr 各自 `truncate_stream(redact_secrets(raw), budget)`；trace 字节大小仍取原始 `result.stdout/stderr`。看绿

## 5. 文档

- [x] 5.1 更新 `docs/capabilities/sandbox-improvements.md` 的 Change 3 段（落地决策与取舍）
- [x] 5.2 更新 `docs/capabilities/sandbox.md`：在密钥过滤项补「出站输出脱敏已实现（`sandbox-output-redaction`）」

## 6. 收尾

- [x] 6.1 `uv run pytest tests/unit/test_sandbox_redaction.py tests/unit/test_tools.py -x -q` 绿
- [x] 6.2 `uv run pytest tests/unit -q` 无新增失败（既有 4 path 族除外）
- [x] 6.3 `uv run ruff format src tests && uv run ruff check`（本 change 文件全绿）
- [x] 6.4 `uv run mypy`（本 change 文件无问题）
- [x] 6.5 `uv run python scripts/check_test_layers.py`（本 change 新增测试无违规）
