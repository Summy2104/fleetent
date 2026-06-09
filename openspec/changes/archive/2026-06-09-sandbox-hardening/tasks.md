## 1. env 注入白名单

- [x] 1.1 Write failing unit tests `tests/unit/test_sandbox_env_allowlist.py`：`build_sandbox_env(agent_env=..., allowlist={"FOO"})` 只保留 FOO；allowlist=None 保持现状（全部非 sensitive 通过）；白名单内但 sensitive 的名字仍被剔除（双过滤）（tests/unit）
- [x] 1.2 Implement `build_sandbox_env` 增可选 `allowlist` 参数，pass unit tests

## 2. workspace 挂载路径黑名单

- [x] 2.1 Write failing unit tests `tests/unit/test_sandbox_mount_blocklist.py`：`is_blocked_mount("~/.ssh/...")`/`/etc/...`/`/root` 为真；正常 `data/workspaces/x` 为假；`manager.workspace_host_path` 当派生路径落在黑名单内时 raise（monkeypatch `paths.workspaces_dir` 到敏感根）（tests/unit）
- [x] 2.2 Implement `is_blocked_mount` + `BLOCKED_MOUNT_SUBPATHS` + manager.workspace_host_path 校验，pass unit tests

## 3. config-hash 容器复用失效

- [x] 3.1 Write failing unit tests `tests/unit/test_sandbox_config_hash.py`：`config_hash` 对相同输入稳定、对 image/资源/env keys/ws_path 任一变化敏感、对 env **值** 变化不敏感（只取 keys）（tests/unit）
- [x] 3.2 Implement `config_hash` 纯函数 + `create_workspace` 打 `--label fleetent.confighash` + `client.inspect_config_hash`，pass unit tests（mock subprocess）
- [x] 3.3 Write failing unit tests `tests/unit/test_sandbox_manager_config_hash.py`：re-adopt 时 actual≠desired→销毁重建（mock find_workspace 命中 + inspect 返回旧 hash，断言 destroy_workspace 被调 + create_workspace 被调）；actual==desired→复用不重建；actual=None（旧容器）→保守复用不重建（tests/unit，mock client）
- [x] 3.4 Implement acquire re-adopt 的 config-hash 比对 + 不一致销毁重建，pass unit tests

## 4. 收尾验证

- [x] 4.1 解耦验证：改动零 platform import；模块依赖护栏通过；既有 sandbox manager/client/secrets 单测不回归
- [x] 4.2 全量收尾：`make test-pr` 全绿（仅 4 个 paths-wiring 基线）＋ ruff/mypy 改动文件 + integration 对照 main 基线无新增失败 + 单 alembic head（推前 merge 最新 main）
