## 1. 测试（先写，必须见红）

- [x] 1.1 `tests/unit/`：`init_sandbox_manager(agent, agent_skills_root=<path>)` 在 agent 的 `sandbox.skill_mount.source` 为 None 时，构造出的 `manager.skill_mount.source == <path>`（per-agent 根作默认）。当前实现未消费该入参/默认 None，预期红。
- [x] 1.2 `tests/unit/`：当 agent 的 `sandbox.skill_mount.source` 被显式配置时，`init_sandbox_manager(agent, agent_skills_root=<path>)` 产出的 `manager.skill_mount.source == 显式值`（显式优先于 per-agent 默认）。
- [x] 1.3 `tests/unit/`：不传 `agent_skills_root`（旧调用）时行为不变——`manager.skill_mount.source` 仍为 agent 配置值（None 即 None），退化为既有全局回退，保证向后兼容。
- [x] 1.4 `tests/unit/`：`boot`/`_start_infra` 接线测试——patch `init_sandbox_manager`，断言其被以 `agent_skills_root == home_dir/"skills"`（与 `scan_skills` 同一个值）调用，钉住「挂载根与扫描根同源」。

## 2. 实现

- [x] 2.1 `tools/builtin_tools.py`：`init_sandbox_manager` 新增可选入参 `agent_skills_root: str | Path | None = None`；当 agent 的 `sandbox.skill_mount.source` 为 None 且该入参非 None 时，用它作为 `SkillMountConfig.source` 默认；显式 source 仍优先。跑 1.1/1.2/1.3 转绿。
- [x] 2.2 `runtime/agent_app.py`：`boot` 计算一次 per-agent skills 根（复用喂给 `scan_skills` 的 `home_dir/"skills"`），经 `_start_infra` 传至 `init_sandbox_manager(agent, agent_skills_root=...)`。跑 1.4 转绿。
- [x] 2.3 复核 `_resolve_skill_mount` / `materialize_builtin_skills` 在新 source 下行为正确（builtin 物化进 per-agent 根、ro/config_hash/is_blocked_mount 不变），必要时补断言。复核结论：`effective_skill_root(source)` 对非 None source 直接返回，materialize/is_blocked_mount/config_hash 均对任意 source 通用，既有 18 项 skill_mount 单测无回归，无需补码。

## 3. 收尾

- [x] 3.1 受影响层测试：`uv run pytest tests/unit -q`（本 change 相关无新增失败）。
- [x] 3.2 `make test-pr`：3161 passed，仅 1 个预存在失败 `test_intelligence_directory_shim_removed`（stash 本改动后仍失败，与本 change 无关）；本 change 零新增失败、改动文件 ruff 干净。
- [x] 3.3 完整 `tests/integration`：2075 passed，仅 2 个预存在失败 `test_deployment_docs.py`（断言本地 `config/` 目录不存在，环境相关，与 skill mount 无关）；本 change 零新增失败。
