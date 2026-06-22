# Tasks

> 每个实现 task 严格 TDD：先写测试跑最窄命令**见红** → 写实现**见绿**。
> 最窄命令：`uv run pytest tests/unit/test_file_sandbox_io.py -x -q`

## 1. 前置核实
- [ ] 1.1 复读 `resolve_host_path`(file_sandbox_io.py:123) + `WORKSPACE` 常量;确认 `send_file`(builtin_tools:1135) / file_tools host backend(file_tools:303) 都经它

## 2. resolve_host_path 接受 /workspace 前缀（TDD：红 → 绿）
- [ ] 2.1 **测试先行**：`tests/unit/test_file_sandbox_io.py` 加：
  - `/workspace/a/b.txt` → `tmp/a/b.txt`
  - `/workspace` → `tmp`
  - `/workspace/../escape.txt` → ValueError
  - `/workspace-evil/x` → ValueError（仿冒回归保护）
  跑最窄命令 **见红**（现状 `/workspace/...` 被判越界）
- [ ] 2.2 **实现**：`resolve_host_path` 在绝对/相对判定前剥 `/workspace`、`/workspace/<rel>` 前缀映射到 root 相对。跑 2.1 **见绿**

## 3. 回归 + lint
- [ ] 3.1 `uv run pytest tests/unit/test_file_sandbox_io.py tests/unit/test_file_tools_backend.py tests/unit/test_file_tools_read.py tests/unit/test_file_tools_write.py -q` 全绿（既有相对/越界/仿冒不回归）
- [ ] 3.2 `uv run ruff check` + `ruff format --check` 受影响文件通过

## 4. spec 同步
- [ ] 4.1 确认 `specs/sandbox-file-send/spec.md` 的 send_file 路径要求 MODIFIED 与实现一致（接受 `/workspace[/<rel>]` 绝对前缀;越界/仿冒仍拒）

## 5. 收尾验证
- [ ] 5.1 `make test-pr`：全绿或仅预先存在且无关失败（判据＝无新增失败）
- [ ] 5.2 模块边界自检通过；无 `fleetent.platform.*` 反向 import
- [ ] 5.3 回归确认（人读）：容器 `resolve_ws_path`、`/exchange`、越界/仿冒拒绝均未变；仅宿主围栏新增「接受 `/workspace` 前缀」
