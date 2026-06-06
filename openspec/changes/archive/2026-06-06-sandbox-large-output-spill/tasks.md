## 1. 前置核实（无代码改动）

- [x] 1.1 核实 `run_code` 输出组装处现为 `truncate_stream(redact_secrets(raw), budget)`（change 3 后）；确认替换点保持 redact 在 spill 之前
- [x] 1.2 核实 `builtin_tools.GENERATED_DIR`/`UPLOADS_DIR` 的注入式 `paths.data_dir()/...` + `uuid4` 约定与 `truncate_stream` 预览签名

## 2. 落盘模块（integrations/sandbox/output_spill.py）

- [x] 2.1 Write failing tests（`tests/unit/test_sandbox_output_spill.py`）：`cap_or_spill` 未超预算→原样返回且不创建文件；超预算→写 `SANDBOX_OUTPUT_DIR/{uuid}.txt`（内容=完整输入）、返回含文件路径 + 原始字节数 + `read_file` 提示 + head/tail 预览。`monkeypatch SANDBOX_OUTPUT_DIR` 到 tmp_path。运行看红
- [x] 2.2 Implement `output_spill.py`（`SANDBOX_OUTPUT_DIR` 注入常量 + `cap_or_spill` + `_write_spill`，预览复用 `truncate_stream`），看绿
- [x] 2.3 Write failing tests：保留期清理——写新文件时删除 mtime 早于保留期的旧 `*.txt`（用 `os.utime` 回拨旧文件 mtime）、保留期内文件保留。看红
- [x] 2.4 Implement 写入时机会式 `_cleanup_expired`（扫描 `*.txt`、删 mtime 过期者、失败仅记录），看绿

## 3. 公共 API 导出（integrations/sandbox/__init__.py）

- [x] 3.1 Write failing test：`from fleetent.integrations.sandbox import cap_or_spill` 可用。看红
- [x] 3.2 Implement `__init__` 导出 + `__all__`，看绿

## 4. run_code 接线（tools/builtin_tools.py）

- [x] 4.1 Write failing test（`tests/unit/test_tools.py` run_code 段）：`client.exec` 返回超 `MAX_STDOUT_BYTES` 的 stdout（且含一个密钥）→ `run_code` 返回值包含落盘引用（路径 + `read_file`），预览中不含密钥；落盘文件存在且其内容不含原始密钥（先脱敏后落盘）。`monkeypatch` `output_spill.SANDBOX_OUTPUT_DIR` 到 tmp_path。看红
- [x] 4.2 Implement：`run_code` 两处流处理由 `truncate_stream(redact_secrets(raw), budget)` 改为 `cap_or_spill(redact_secrets(raw), budget, label=...)`（redact 仍在前），看绿

## 5. 文档

- [x] 5.1 更新 `docs/capabilities/sandbox-improvements.md` 的 Change 4 段（落地决策与取舍）+ 批次收尾小结
- [x] 5.2 更新 `docs/capabilities/sandbox.md`：输出截断项补「超限中段已改为落盘 + 引用（`sandbox-large-output-spill`）」

## 6. 收尾

- [x] 6.1 `uv run pytest tests/unit/test_sandbox_output_spill.py tests/unit/test_tools.py -x -q` 绿
- [x] 6.2 `uv run pytest tests/unit -q` 无新增失败（既有 4 path 族除外）
- [x] 6.3 `uv run ruff format src tests && uv run ruff check`（本 change 文件全绿）
- [x] 6.4 `uv run mypy`（本 change 文件无问题）
- [x] 6.5 `uv run python scripts/check_test_layers.py`（本 change 新增测试无违规）
