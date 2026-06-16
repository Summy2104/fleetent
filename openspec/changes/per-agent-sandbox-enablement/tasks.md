# Tasks

> 前置：建立在 `per-agent-sandbox-resources`（Change 1）之上——Change 1 先合，本 change 收口"整体零读"护栏。

## 1. Mode 收敛 + 启用判定（测试先行）

- [ ] 1.1 写 unit：`is_code_execution_enabled(Mode.OFF, *)→False`；`is_code_execution_enabled(Mode.ON, None/True)→True`、`(Mode.ON, False)→False`（保留 all 语义、删 selective）。先见红。
- [ ] 1.2 写 unit：`get_effective_mode(backend)` —— 后端 `available()=True→Mode.ON`、`False→Mode.OFF`，全程**不读 platform.yaml**（monkeypatch `paths.platform_yaml_path` 指向探测路径，断言未触达）。先见红。
- [ ] 1.3 实现：`Mode` 去 `SELECTIVE`/`ALL`、保留 `OFF`、加 `ON`；`is_code_execution_enabled` 改 `mode is not OFF and code_execution is not False`；`get_effective_mode` 改只依 `backend.available()`；删 `load_sandbox_mode`/`_read_raw_mode`/`SETTINGS_PATH`（及 `resolve_effective_mode` 对 configured mode 的依赖）。跑 1.1/1.2 见绿。

## 2. 调用方适配（测试先行）

- [ ] 2.1 写/改 unit：`runtime/loop.py` schema 过滤点在 Mode.ON+code_execution 组合下的 run_code 可见性（替代原 selective/all 用例）；`agent_app.py` `mode is not OFF` 的 wiring 判定不变。先见红（若原用例引用 SELECTIVE/ALL 则失败）。
- [ ] 2.2 实现：清理 `runtime/loop.py`、`tools/file_tools.py`、`im_gateway/normalizer.py`、`server.py` 中 `Mode.ALL/SELECTIVE` 引用为 ON/OFF 模型；server admin 展示 sandbox_mode 改 ON/OFF。`uv run mypy src` 确保无残留 `Mode.ALL/SELECTIVE`。跑 2.1 见绿。
- [ ] 2.3 核对 approval-minimization：确认 `action_gate` 的 `sandbox_capable` 计算只依赖运行时能力（ON/OFF）+ agent code_execution，不依赖被删的 configured mode；如有依赖则同步适配并补测。

## 3. 收口零读护栏（测试先行）

- [ ] 3.1 写 unit guardrail：`integrations/sandbox` 各模块 AST 不出现对 `paths.platform_yaml_path` 的引用 / 不读 platform.yaml（叠加 Change 1 后整体零读）。先见红（enablement.py 仍引用时失败）。
- [ ] 3.2 实现/收尾：确保 enablement 改造后该护栏转绿（Change 1 已移除 config.py 的读取）。跑 3.1 见绿。

## 4. shipped platform.yaml 清理 + 迁移文档

- [ ] 4.1 从仓库 shipped platform.yaml 示例/模板删除 `sandbox.mode`。
- [ ] 4.2 迁移文档（docs/）：`mode:off`→所有 agent `features.code_execution:false`；`mode:selective`→仅授权 agent `code_execution:true`；`mode:all`→不声明（默认开）；说明 medium 免审批改以运行时 `sandbox_capable` 表述。

## 5. 收尾验证

- [ ] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q` 对照 main 无新增失败；`uv run mypy src` 净；改动文件 ruff 净。
- [ ] 5.2 `fleetent agent run`（无 platform.yaml）实测/集成：sandbox 启用仅由 `features.code_execution`+Docker 可用性决定，启动不读 platform.yaml。
- [ ] 5.3 标记所有 checkbox 为 `[x]`，准备 archive。
