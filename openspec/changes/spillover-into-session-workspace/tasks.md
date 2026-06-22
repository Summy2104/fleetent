# Tasks

> 每个实现 task 严格 TDD：先写测试跑最窄命令**见红** → 写实现**见绿**。
> 最窄命令：`uv run pytest tests/unit/test_tool_result_truncation_spillover.py -x -q`

## 1. 前置核实
- [ ] 1.1 复读 `truncate_tool_result` / `_spillover`(result_truncation.py) + `SPILLOVER_DIR`;loop.py finalize 调用点(~1060/~2953)与 `scope_key`/`host_workspace_dir` 可得性;确认既有 spillover 测试 monkeypatch `SPILLOVER_DIR` 且不传 workspace_dir

## 2. workspace_dir → workspace 相对溢出（TDD：红 → 绿）
- [ ] 2.1 **测试先行**：`test_tool_result_truncation_spillover.py` 加：
  - `truncate_tool_result(big, workspace_dir=tmp)` → `tmp/.fleetent_spillover/<uuid>.txt` 存在且含完整原文
  - 返回 hint 含相对路径 `.fleetent_spillover/`（且不含 `str(tmp)` 绝对前缀）
  - 既有「不传 workspace_dir → 写 SPILLOVER_DIR」用例仍绿（回归）
  跑最窄命令 **见红**（`workspace_dir` 参数不存在 / 仍写全局）
- [ ] 2.2 **实现**：`truncate_tool_result` 加 `workspace_dir=None`;`_spillover(result,orig,limit,workspace_dir)`:有则写 `<ws>/.fleetent_spillover/`、hint 相对路径;无则旧全局 + 绝对。跑 2.1 **见绿**

## 3. loop.py 接线（wiring）
- [ ] 3.1 两处 finalize：`truncate_tool_result(content, workspace_dir=host_workspace_dir(scope_key) if scope_key else None)`（惰性 import host_workspace_dir）

## 4. 回归 + lint
- [ ] 4.1 `uv run pytest tests/unit/test_tool_result_truncation_spillover.py tests/unit/test_tool_result_truncation.py tests/unit/test_agent_loop.py -q` 全绿（既有全局 spillover / 截断不回归）
- [ ] 4.2 `uv run ruff check` + `ruff format --check` 受影响文件通过

## 5. spec 同步
- [ ] 5.1 确认 `specs/tool-result-truncation/spec.md` 两条溢出要求 MODIFIED 与实现一致（有 workspace 时落 `<ws>/.fleetent_spillover/`、hint 相对路径、read_file 可读；无则回退全局）

## 6. 收尾验证
- [ ] 6.1 `make test-pr`：全绿或仅预先存在且无关失败（判据＝无新增失败）
- [ ] 6.2 模块边界自检通过；无 `fleetent.platform.*` 反向 import
- [ ] 6.3 回归确认（人读）：截断阈值/头尾/self_truncates/多字节/cleanup 未变;无 workspace 时全局回退不变;仅新增「有 workspace 时溢出落 workspace + 相对 hint」
