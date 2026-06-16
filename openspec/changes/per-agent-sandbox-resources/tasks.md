# Tasks

## 1. agent.yaml schema：sandbox.resources（测试先行）

- [ ] 1.1 写 unit：`agent_config` 解析含 `sandbox.resources`（network/memory/cpus/read_only/exec_timeout/memory_swap_mb/pids_limit/tmpfs_size_mb/cap_drop_all/cap_add/no_new_privileges/init/run_as_user）+ `idle_hours` 的 agent.yaml → `SandboxSettings.resources` 各字段就位；缺字段为 None/默认；非法 sandbox key 仍因 `extra=forbid` 报错。先跑见红。
- [ ] 1.2 实现：`agent_config.py` 加 `SandboxResourcesSettings` 子模型 + `SandboxSettings.resources` / `idle_hours`。跑 1.1 见绿。

## 2. 从 agent 配置构建 SandboxResources（测试先行）

- [ ] 2.1 写 unit：`resources_from_agent_settings(agent_sandbox)` —— 全缺省→等于 `SandboxResources()`；逐字段覆盖生效；非法值（memory=0 / network 未知 / pids_limit 负 / exec_timeout 越界）记录并回退该字段默认（不静默接受、exec_timeout clamp [1,600]）。先见红。
- [ ] 2.2 实现：在 `integrations/sandbox/config.py` 增 `resources_from_agent_settings`，复用既有字段级校验/clamp/枚举回退。跑 2.1 见绿。

## 3. 接线 init_sandbox_manager 注入 + manager 停读 platform.yaml（测试先行）

- [ ] 3.1 写 unit/integration：`init_sandbox_manager(agent)` 用 `agent.SandboxSettings.resources` 构建 `SandboxResources` 并注入 `SandboxManager.resources_by_scope`（SESSION/AGENT 同档）与 `idle_hours`；两个不同 `resources.network` 的 agent → 各自容器创建参数独立。先见红。
- [ ] 3.2 实现：`tools/builtin_tools.py` 的 `init_sandbox_manager` 构建并注入 resources/idle_hours；`manager.__post_init__` 删除对 `build_resources_by_scope()`/`load_sandbox_lifecycle()`/`load_skill_mount_config()` 的 platform.yaml 回落（改为注入恒满或新默认构造）。跑 3.1 见绿。

## 4. 停读 platform.yaml + 塌缩 agent_scope（测试先行）

- [ ] 4.1 写 unit：解析某 agent 沙箱资源/硬化/lifecycle/skill_mount 全过程不调用 `paths.platform_yaml_path()`、不读 platform.yaml 的 `sandbox.resources`/`agent_scope`/`workspace_scope`/`idle_hours`/`skill_mount`（monkeypatch platform_yaml_path 指向会抛错/被探测的路径，断言未触达）；standalone 无 platform.yaml 时按 agent.yaml+默认解析成功。先见红。
- [ ] 4.2 实现：移除 `config.py` 中 resources/lifecycle/skill_mount 读 platform.yaml 的路径与 `agent_scope` 双档逻辑（`build_resources_by_scope` 退化/删除、swap 的 agent_scope 跟随删除）；`SETTINGS_PATH` 仅留给 `mode`（Change 2 处理）。跑 4.1 见绿。

## 5. shipped platform.yaml 清理 + 迁移文档

- [ ] 5.1 从仓库 shipped 的 platform.yaml 示例/模板删除 `sandbox.resources`/`agent_scope`/`workspace_scope`/`idle_hours`/`skill_mount`（保留 `sandbox.mode` 等其余）。
- [ ] 5.2 写迁移文档（docs/）：platform.yaml 旧 sandbox 资源/lifecycle/skill_mount → 各 agent.yaml `sandbox.resources`/`workspace_scope`/`idle_hours`/`skill_mount` 的字段对照与示例。

## 6. 既有测试迁移 + 收尾验证

- [ ] 6.1 迁移现有直接调 `load_sandbox_resources`/`build_resources_by_scope`/写临时 platform.yaml 验资源的 unit/integration → 走 `resources_from_agent_settings` / agent.yaml 注入路径；清理引用 `sandbox.agent_scope` 的用例。
- [ ] 6.2 `make test-pr` 全绿；`uv run pytest tests/integration -q` 对照 main 无新增失败；`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过；改动文件 ruff/mypy 净。
- [ ] 6.3 标记所有 checkbox 为 `[x]`，准备 archive。
