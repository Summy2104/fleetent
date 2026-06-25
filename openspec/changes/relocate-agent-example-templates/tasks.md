# Tasks

## 1. 测试锚点（红）

- [x] 1.1 更新 `tests/unit/test_agent_config.py::test_repo_agent_yaml_example_loads_as_single_agent_file`：把 `repo/"agents"/"default"/"agent.yaml.example"` 改为 `repo/"agent.yaml.example"`，断言信息同步。先跑 `uv run pytest tests/unit/test_agent_config.py -x -q` 见红（模板尚未移动）。
- [x] 1.2 更新 `tests/integration/test_deployment_docs.py` 全部旧路径断言：`agents/default/.env.example`→`agent.env.example`、`agents/default/agent.yaml.example`→`agent.yaml.example`；Dockerfile `COPY` 断言改为新的合并 COPY 行并删除 `COPY agents/default/` 断言；变体非存在性断言 re-path 到根并加 `not Path("agents/default").exists()`。先跑见红。
- [x] 1.3 更新 `tests/integration/test_env_template_boundaries.py::test_agent_env_template_contains_complete_empty_agent_refs_not_platform_vars`：agent env 模板路径 `ROOT/"agents"/"default"/".env.example"` → `ROOT/"agent.env.example"`（Path 组件式引用，初次 grep 漏检，全量 integration 逮到）。

## 2. 实现（绿）

- [x] 2.1 `git mv agents/default/agent.yaml.example agent.yaml.example`、`git mv agents/default/.env.example agent.env.example`，删除随之变空的 `agents/` 目录。
- [x] 2.2 修两个模板文件内部自引用注释：`agent.yaml.example` 头注释里 `FLEETENT_HOME/agents/default/agent.yaml` → `FLEETENT_HOME/tenants/default/agents/<id>/agent.yaml`；`agent.env.example` 里 `agents/default/agent.yaml.example` → `agent.yaml.example`。
- [x] 2.3 `Dockerfile`：把 `agent.yaml.example agent.env.example` 加入既有 `COPY ... ./`，删除 `COPY agents/default/ ./agents/default/` 与 `mkdir` 中的 `agents/default`。
- [x] 2.4 `README.md`：模板路径段（30-33）改为根目录 `agent.yaml.example` / `agent.env.example`；`agent init` 示例（43-44、59-60）路径补 `tenants/default/`；配置/ MCP 段（134、206）`agents/<agent-id>/agent.yaml` → `tenants/default/agents/<agent-id>/agent.yaml`。
- [x] 2.5 跑 `uv run pytest tests/unit/test_agent_config.py tests/integration/test_deployment_docs.py -q` 见全绿。

## 3. 根目录清理（独立 chore）

- [x] 3.1 `.gitignore` 补 `.pytest_cache/`、`.ruff_cache/`；删除 `data/.gitkeep`（`data/` 整目录已被 ignore）。

## 4. 收尾验证

- [x] 4.1 全仓 grep 旧模板路径（排除 `openspec/changes/archive/` 与 `/admin/agents/default` API 路由），确认无遗漏 live 引用。
- [x] 4.2 `make test-pr` 全绿（3666 passed）+ `uv run pytest tests/integration -q`：2070 passed，仅余 1 个预存基线失败 `test_capability_docs::test_capability_docs_describe_shared_memory_scope`（在干净 main 上同样失败，shared_memory→agent_memory 文档改名遗留，owner 非本 change），无新增失败。
- [ ] 4.3 spec delta 由 `opsx:archive` 应用到 `openspec/specs/`（configuration / file-agent-runtime / install-bootstrap），不手改 live spec。
