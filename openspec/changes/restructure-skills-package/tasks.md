> 纯结构重构（含一处必要路径修正 D5）：用既有全量测试套件作为回归安全网，每步后保持绿。

## 1. 基线

- [ ] 1.1 记录基线：`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 全绿；`mypy src` 现有错误数

## 2. 移文件 + 建包

- [ ] 2.1 `git mv` `skill_registry.py`→`skills/registry.py`、`skill_audit.py`→`skills/audit.py`
- [ ] 2.2 改包内 import（registry 引用 audit）；**修正 `BUILTIN_SKILLS_DIR` 相对路径**指向 `src/fleetent/builtin_skills/`，并加 `BUILTIN_SKILLS_DIR.exists()` 断言到现有相关测试
- [ ] 2.3 建 `skills/__init__.py`：re-export 公共 API + 显式 `__all__`（scan/reload/match/load/list_skills/load_errors/available_skills_prompt/collect_disabled_trace/SkillEntry/SkillIndex 等）；`from fleetent.skills import scan, match` 自检通过

## 3. 旧路径 shim

- [ ] 3.1 旧 `skill_registry.py`、`skill_audit.py` 改为 shim（re-export + `__all__`，不含逻辑）；`uv run python -c "from fleetent.skill_registry import scan, match"` 旧路径自检通过

## 4. 改 src 调用方到新公共 API

- [ ] 4.1 `agent_loop.py`（保留 `match as match_skill` patch-target 别名）、`server.py`、`tools.py`（lazy）、`im_gateway/normalizer.py`（lazy）、`platform/skill_management/skill_admin_api.py`（改 `from fleetent.skills import registry as skill_registry`）；`uv run python -c "import fleetent.server, fleetent.agent_loop"` 导入成功

## 5. 测试 import + patch 目标随迁

- [ ] 5.1 `grep -rn "skill_registry\|skill_audit" tests` 全量核对：patch 模块全局状态的测试改 patch `fleetent.skills.registry`；`test_skill_registry.py` 等直接测试 import 改新路径；patch `agent_loop.match_skill` / `skill_admin_api.skill_registry` 形式的不动
- [ ] 5.2 跑 skills 相关测试子集绿（含 builtin_skills 扫描路径用例）

## 6. 全量门禁 + 文档

- [ ] 6.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 绿（与基线一致）
- [ ] 6.2 `uv run ruff format` 本 change 文件 + `ruff check src tests` 干净；`mypy src` 不新增错误模式
- [ ] 6.3 更新 `docs/architecture.md`：skills 从平铺改记为 `skills/`
