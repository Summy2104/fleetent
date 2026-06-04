## Why

蓝图迁移序列**第三包**（sandbox✅ → session → **skills** → model → tools → runtime）：把平铺的 `skill_registry.py`、`skill_audit.py` 收进 `skills/` 能力包。audit 只被 registry 引用（包内化），调用方集中在 agent_loop / server / tools / normalizer / skill_admin_api，规模与 session 相当。

## What Changes

- **迁移 2 文件**到 `src/fleetent/skills/`，去冗余前缀（`git mv` 保留 blame）：
  `skill_registry.py`→`registry.py`、`skill_audit.py`→`audit.py`。
- **建 `skills/__init__.py`** re-export 公共 API（`scan`、`match`、`available_skills_prompt`、`collect_disabled_trace` 等，以 src+tests 实际使用为准）。
- **改包内 import**（registry → audit）。
- **旧扁平路径留 re-export shim**（`skill_registry.py`、`skill_audit.py`，不承载逻辑）。
- **改 src 直接调用方**：`agent_loop.py`、`server.py`、`tools.py`（lazy）、`im_gateway/normalizer.py`（lazy）、`platform/skill_management/skill_admin_api.py`（module-style）。
- **迁移直接相关测试的 import 与 monkeypatch 目标**（注意：`agent_loop` 以 `match as match_skill` 显式标注 patch target，patch `fleetent.agent_loop.match_skill` 的测试不受影响；patch `skill_registry` 模块属性的测试必须改 patch `fleetent.skills.registry`）。
- 行为不变、无 schema 变更。

## Capabilities

### Modified Capabilities
- `package-architecture`: 记录 skills 域**已完成包化**——`skills/` 成包、公共 API 收口、旧路径仅 shim、契约/行为不变。

## Impact

- **代码**：新增 `src/fleetent/skills/`（2 模块 + `__init__.py`）；旧 2 文件变 shim；5 处 src 调用方改 import。
- **测试**：patch `skill_registry` 模块级状态（如扫描结果缓存、`FLEETENT_SKILLS_DIR` 相关路径）的测试改 patch 新模块；纯 import 靠 shim 渐进。
- **不受影响**：skill 扫描时机（FastAPI lifespan / CLI per-run）、关键词匹配逻辑、注入审计门、禁用谓词、热重载原子换。
- **依赖**：蓝图 + 前序迁移范式；建议在 session 之后执行（无硬依赖，纯序列约定）。
- **分支**：基于并 PR 合回 `main`。
