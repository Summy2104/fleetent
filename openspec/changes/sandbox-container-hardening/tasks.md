## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `SandboxResources` 现字段（`config.py`）、`_resource_flags` 现产出（`client.py`）、`build_resources_by_scope` 现 agent 覆盖逻辑（`read_only=False`），确定加固字段挂载点
- [x] 1.2 核实 `tests/unit/test_sandbox_client.py` / `test_sandbox_config.py` 现有断言中哪些会因默认命令变更而需更新（如「不传配置退回默认 = 现状等价」处）

## 2. SandboxResources 加固字段与默认值（config.py）

- [x] 2.1 Write failing tests：`SandboxResources` 新增 `pids_limit=256` / `tmpfs_size_mb=64` / `cap_drop_all=True` / `cap_add=()` / `no_new_privileges=True` / `init=True` / `run_as_user="65534:65534"` 默认值。运行 `uv run pytest tests/unit/test_sandbox_config.py -x -q` 看到红
- [x] 2.2 Implement 上述字段（dataclass 默认值即最严 session 档单一事实源），看到绿

## 3. 加固字段加载与校验（config.py）

- [x] 3.1 Write failing tests：`load_sandbox_resources` 读 `sandbox.resources` 覆盖各加固字段；缺字段逐项回退默认；非法 `pids_limit` / `tmpfs_size_mb`（<=0 或非整数）记录后回退默认；bool 字段非 bool 回退；`run_as_user` 接受字符串、`null`→None。`monkeypatch SETTINGS_PATH` 到 tmp_path。看到红
- [x] 3.2 Implement 加载 + 逐字段校验（沿用 `_load_positive_int` / `_load_read_only` 模式，新增 `run_as_user` 加载），看到绿
- [x] 3.3 Write failing tests：`build_resources_by_scope` 的 **agent 档**覆盖 `cap_add=(CHOWN,DAC_OVERRIDE,FOWNER,SETUID,SETGID)` 与 `run_as_user=None`；**session 档**保持最严默认（`cap_add=()`、`run_as_user="65534:65534"`）；`sandbox.agent_scope` 可覆盖加固字段。看到红
- [x] 3.4 Implement agent 档覆盖（在既有 `replace(base, ...)` 上追加加固覆盖），看到绿

## 4. 加固标志映射到 docker run（client.py）

- [x] 4.1 Write failing tests：`create_workspace` 产出 `--pids-limit 256`、`--tmpfs /tmp:rw,nosuid,size=64m`、`--cap-drop ALL`、`--security-opt no-new-privileges`、`--init`；`run_as_user` 非空→含 `--user <val>`、为 None→不含 `--user`；`cap_add` 每项→一个 `--cap-add X`。捕获 `asyncio.create_subprocess_exec` 参数断言。看到红
- [x] 4.2 Implement `_resource_flags` 追加加固标志，`--tmpfs /tmp` 升级为带 `nosuid,size=` 选项，看到绿
- [x] 4.3 Write failing tests：单项关闭——`cap_drop_all=False` 无 `--cap-drop`、`no_new_privileges=False` 无该 `--security-opt`、`init=False` 无 `--init`。看到红/绿
- [x] 4.4 更新 `test_sandbox_client.py` 既有断言以匹配新默认命令（替换「现状等价」旧期望），全文件绿、无回归

## 5. 文档

- [x] 5.1 新建 `docs/capabilities/sandbox-improvements.md`：四参考项目（hermes-agent / claude-code / openclaw / opencode）sandbox 对比结论 + 本批 4 个 change 的决策与取舍记录（供 review）
- [x] 5.2 校正 `docs/capabilities/sandbox.md`：将已实现项（资源限制可配置、生命周期 scope、密钥过滤、输出截断、exec 超时、孤儿清理、trace）由「规划中 [ ]」更新为现状；补本 change 的容器加固现状

## 6. 收尾

> 既有 debt（与本批无关，已用 `git stash` + main checkout 复核确认，不在本 change 修，详见 `docs/capabilities/sandbox-improvements.md`）：`tests/unit` 4 个 path 族失败（本机环境，CI 纯净容器不复现）、`ruff check` 9 个（全在 `tools/file_tools.py`）、`mypy src` 7 个（非 sandbox 文件）、`check_test_layers` 1 处（`test_config.py`）。

- [x] 6.1 sandbox 单测全绿：`tests/unit/test_sandbox_config.py`+`test_sandbox_client.py` = 79 passed
- [x] 6.2 全量 `uv run pytest tests/unit` 无新增失败（1901 passed，4 既有失败已复核与本改动无关）
- [x] 6.3 `uv run ruff format src tests` + `ruff check`（本 change 文件全绿；9 个既有错误在 `tools/file_tools.py`，非本 change）
- [x] 6.4 `uv run mypy`（本 change 的 config.py / client.py 无问题；7 个既有错误在非 sandbox 文件）
- [x] 6.5 `uv run python scripts/check_test_layers.py`（本 change 新增测试无违规；1 处既有违规在 `test_config.py`）
