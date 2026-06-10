# sandbox-memory-hard-limit — Tasks

> 每个实现 task 严格 TDD：先写测试见红（`uv run pytest <file>::<test> -x -q`）→ 写实现见绿 → 可选 refactor 保持绿。
> unit 层测纯函数（`_resource_flags` / config 载入），integration 层测真实 Docker（沿用 `test_sandbox_workspace.py` 的 docker-availability skip guard）。

## 1. SandboxResources 字段 + flag 生成

- [ ] 1.1 写失败测试（unit）：默认 `SandboxResources()` 经 `_resource_flags` 产出含 `--memory-swap 256m`（等于 memory）；`memory=512` 时为 `--memory-swap 512m`——当前实现无该 flag，必须红
- [ ] 1.2 写失败测试（unit）：`memory_swap_mb=512, memory=256` 产出 `--memory-swap 512m`；`memory_swap_mb=256, memory=512` 钳制为 `--memory-swap 512m` 且 log warning（capsys/caplog 断言）
- [ ] 1.3 实现：`SandboxResources` 加 `memory_swap_mb: int | None = None`；`_resource_flags` 紧随 `--memory` 追加 `--memory-swap {max(memory_swap_mb or memory, memory)}m`，钳制生效时 `_logger.warn`；跑绿 1.1、1.2

## 2. 配置载入与校验

- [ ] 2.1 写失败测试（unit）：`sandbox.resources.memory_swap_mb: 512` 被载入；`0`/负数/字符串/bool 回退 None 并 log（对齐 `_load_positive_int` 既有行为模式）；字段缺失回退 None
- [ ] 2.2 写失败测试（unit）：`build_resources_by_scope`——`agent_scope.memory_swap_mb` override 生效；agent_scope 仅 override `memory=1024`（base 无 swap 配置）时 agent tier flags 含 `--memory-swap 1024m`（None 跟随语义）
- [ ] 2.3 实现：`_resources_from_section` 与 `build_resources_by_scope` 的 agent override 各自读取/校验 `memory_swap_mb`（可空正整数，复用 `_load_positive_int` 加 None 分支或新 helper）；跑绿 2.1、2.2

## 3. 真实 Docker 行为验证

- [ ] 3.1 写失败/确认测试（integration，docker skip guard）：默认资源（memory=256, 禁 swap）容器内 `python3 -c "bytearray(400*1024*1024)"` 退出码非 0（OOM 137）——在 main 基线上该分配会成功，本测试在新实现前红、后绿
- [ ] 3.2 实现/确认：跑绿 3.1（实现已在 1.3 完成，此 task 为真实后端行为闭环）

## 4. 收尾

- [ ] 4.1 确认 `config_hash` 随新字段自然变化（无需豁免逻辑）；proposal 声明的一次性容器重建无需额外代码
- [ ] 4.2 `make test-pr` 全绿 + `uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 4.3 `openspec validate sandbox-memory-hard-limit --strict` 通过
