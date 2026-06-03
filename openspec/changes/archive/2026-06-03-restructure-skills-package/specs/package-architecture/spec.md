## ADDED Requirements

### Requirement: skills 域已迁入 skills/

skills 能力域 SHALL 组织为 `skills/` package：公共 API 收口于其 `__init__.py`；原 `src/fleetent/skill_registry.py`、`skill_audit.py` 平铺路径 SHALL 仅保留为不承载逻辑的 re-export shim；`BUILTIN_SKILLS_DIR` SHALL 在迁移后仍指向真实的 `builtin_skills/` 目录；迁移 SHALL 不改变扫描、匹配、审计或热重载行为。

#### Scenario: skills 成包且公共 API 收口
- **WHEN** 查看 `src/fleetent/skills/`
- **THEN** 它含 `__init__.py` + `registry.py` + `audit.py`，且 `__init__.py` 导出 `scan`、`match`、`available_skills_prompt`、`SkillIndex` 等公共符号

#### Scenario: 旧扁平路径仅为 shim
- **WHEN** 查看 `src/fleetent/skill_registry.py` 或 `skill_audit.py`
- **THEN** 它只从 `fleetent.skills.*` re-export，不含函数/类定义

#### Scenario: builtin_skills 路径解析正确
- **WHEN** import `fleetent.skills.registry`
- **THEN** `BUILTIN_SKILLS_DIR.exists()` 为真（指向 `src/fleetent/builtin_skills/`）

#### Scenario: 行为不变
- **WHEN** 完成迁移
- **THEN** 全量测试（`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`）通过，且无 schema 变更
