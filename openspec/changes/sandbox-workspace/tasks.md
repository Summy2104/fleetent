## 1. Workspace 路径派生（paths）

- [ ] 1.1 Write failing tests for `paths.workspaces_dir()`: 派生自 `data_dir()/workspaces`、随 `FLEETENT_HOME` 重定向、可 monkeypatch 注入隔离（tests/unit）
- [ ] 1.2 Implement `paths.workspaces_dir()` to pass tests

## 2. Workspace 挂载（client + manager）

- [ ] 2.1 Write failing unit tests: `create_workspace` 在给定 host workspace 路径时拼出 `-v <host>:/workspace` 挂载 flag；`SandboxManager.acquire` 按 scope（session_id / agent_name）解析 workspace 子目录并创建该目录、传入 client（mock docker，tests/unit）
- [ ] 2.2 Implement `client.create_workspace` 挂载参数 + `manager.acquire` 解析并传入 workspace 路径，pass unit tests
- [ ] 2.3 Write failing integration test: 真实 docker 下 session 与 agent 两个 tier 的容器均能写 `/workspace`；容器销毁后宿主 workspace 目录与内容保留；workspace 外宿主路径（如 `/etc/passwd`）读到的非宿主真实文件（tests/integration，无 docker 则 skip）
- [ ] 2.4 Implement 直到 integration 通过（含 workspace 目录创建时对容器运行 uid 的写权限对齐）

## 3. Session snapshot（client.exec 包装）

- [ ] 3.1 Write failing unit tests: 首次 exec 生成 `export -p`/`declare -f`/`alias -p` 捕获脚本到 `/tmp/snap-<session>.sh`；后续命令包装为 `source→cd→eval→重新 dump→打印 cwd marker`；cwd marker 从返回输出中剥离；快照失败降级 `bash -l`（tests/unit，断言命令字符串组装与输出处理）
- [ ] 3.2 Implement `client.exec` 的 snapshot 包装、cwd marker 提取与剥离、失败降级，pass unit tests
- [ ] 3.3 Write failing integration test: 跨 exec 环境连续——`export FOO=bar` 后 `echo $FOO` 得 `bar`；`cd /workspace/sub` 后 `pwd` 在该目录（tests/integration，无 docker 则 skip）
- [ ] 3.4 Implement 直到 integration 通过

## 4. run_code 串接

- [ ] 4.1 Write failing unit tests: run_code 经 `SandboxManager` 取得挂载 workspace 的容器并以 session snapshot 路径执行（tests/unit，mock client）
- [ ] 4.2 Implement run_code 串接 workspace + session，pass unit tests

## 5. 收尾验证

- [ ] 5.1 解耦验证：在无 platform、platform 的 DB 表不存在的环境下 `fleetent agent run` 能正常执行 run_code（含 workspace 写与跨命令连续）
- [ ] 5.2 全量收尾：`uv run pytest -x -q` + `uv run ruff check src tests` + `uv run mypy src` + `uv run python scripts/check_test_layers.py` 全绿
