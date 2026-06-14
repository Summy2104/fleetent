## 1. 冒号安全的 mount 装配

- [ ] 1.1 [test] `tests/unit/test_sandbox_exchange_mount.py`：`_exchange_flags` 装配为 `--mount type=bind,source=…,target=/exchange,readonly`;**新增回归**：含冒号的视图路径（`.../.views/slack:dm:U1:1781…`）装配出的 flag 不含会被 docker 误切的裸 `-v <冒号路径>`，且 source 为完整原路径。先见红。
- [ ] 1.2 [impl] `DockerBackend._exchange_flags` 改用 `--mount type=bind,source=<view>,target=/exchange,readonly`;None→`[]`。见绿。
- [ ] 1.3 [test] `tests/unit/test_sandbox_skill_mount_flags.py`：`_skill_mount_flags` 改断言 `--mount`（readonly 默认 / 可写 / None）。先见红。
- [ ] 1.4 [impl] `_skill_mount_flags` 改 `--mount type=bind,source=…,target=/workspace/skills[,readonly]`。见绿。
- [ ] 1.5 [test] `tests/unit/test_sandbox_client.py`：workspace 挂载断言改 `--mount`（含/不含路径两种）。先见红。
- [ ] 1.6 [impl] `_workspace_flags` 改 `--mount type=bind,source=…,target=/workspace`;None→`[]`。见绿。

## 2. create_workspace 组装回归

- [ ] 2.1 [test] `test_sandbox_exchange_mount.py` 的 `create_workspace` 用例：断言 args 含 `--mount` 的 exchange ro 规格、无能力时不含;**新增**：传含冒号的 `exchange_view_path` 时组装出的命令无 "too many colons" 隐患（无裸 `-v <冒号路径>`）。先见红→改实现后见绿（随 1.2 落地）。

## 3. 收尾

- [ ] 3.1 [gate] `make test-pr` 全绿;`uv run pytest tests/integration -q` 无新增失败。
- [ ] 3.2 [gate] `uv run mypy src`（≤基线）+ 改动文件 `ruff check/format` 净。
