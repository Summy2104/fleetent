## Context

蓝图已确立目标结构；sandbox / session 范式在前。现状：`skill_registry.py`（扫描/索引/匹配/禁用/热重载/prompt 注入，约 460 行）+ `skill_audit.py`（注入审计规则，仅被 registry 引用）平铺。

src 直接调用方（已扫描）：
- `agent_loop.py`：`available_skills_prompt, collect_disabled_trace` + `match as match_skill`（noqa 标注 **patch target**）+ `scan as scan_skills`
- `server.py`：`scan as scan_skills`
- `tools.py`：lazy `from fleetent import skill_registry`
- `im_gateway/normalizer.py`：lazy `from fleetent.skill_registry import available_skills_prompt, collect_disabled_trace`
- `platform/skill_management/skill_admin_api.py`：`from fleetent import auth, skill_registry, user_store`（module-style，且测试 patch `skill_admin_api.skill_registry._parse_frontmatter`）

## Goals / Non-Goals

**Goals**：2 文件迁入 `skills/`、去前缀、`__init__` 收口、调用方改新路径、shim 兜底、全量绿、行为不变。
**Non-Goals**：不改扫描/匹配/审计逻辑；不动 `builtin_skills/` 目录（registry 内 `BUILTIN_SKILLS_DIR` 相对路径需验证仍正确）；不动 skill_management 平台模块的归属。

## Decisions

### D1 — 文件映射（去前缀）
```
skill_registry.py → skills/registry.py
skill_audit.py    → skills/audit.py
```
`git mv` 保留历史。

### D2 — 公共 API 收口 `skills/__init__.py`
`scan, reload, match, load, list_skills, load_errors, available_skills_prompt, collect_disabled_trace, SkillEntry, SkillIndex` + `audit` 域的 `audit, has_severe, Hit`（若外部用到）。`__all__` 显式。`_parse_frontmatter` 等私有名不导出——module-style 调用方（skill_admin_api）改 `from fleetent.skills import registry as skill_registry` 后私有名仍可达。

### D3 — module-style 调用方改法
`skill_admin_api.py` 改 `from fleetent.skills import registry as skill_registry`，函数体与测试 patch 路径（`skill_admin_api.skill_registry...`）零改动。`tools.py` / `normalizer.py` 的 lazy import 同样改别名形式。

### D4 — 旧路径 shim
`skill_registry.py` / `skill_audit.py` 改为 re-export shim + `__all__`，不承载逻辑。

### D5 — BUILTIN_SKILLS_DIR 相对路径校验
`BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin_skills"` 在文件移动后会指向 `skills/builtin_skills`（不存在）。**必须改为指向 `src/fleetent/builtin_skills/`**（如 `Path(__file__).parent.parent / "builtin_skills"`），并有测试覆盖该路径解析。这是本包唯一的"非纯搬迁"必要修正。

### D6 — patch 目标随迁
- patch `fleetent.agent_loop.match_skill` / `scan_skills` 的测试不受影响（patch 的是 agent_loop 命名空间）。
- patch `skill_registry` 模块全局（索引缓存 `_INDEX` 之类）的测试改 patch `fleetent.skills.registry`。
- `skill_admin_api.skill_registry` 形式的 patch 因 D3 别名改法零改动。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| `__file__` 相对路径断（builtin_skills） | D5 显式修正 + import 后 `BUILTIN_SKILLS_DIR.exists()` 自检 |
| 模块级可变状态（扫描索引缓存）patch 漂移 | D6 全量 grep 核对 patch 目标 |
| lazy import 改漏 | shim 兜底 + 全量 pytest |
| 热重载原子换引用旧模块对象 | reload 逻辑随文件整体迁移，引用关系不变 |

## 验收

- `skills/` 成包，`__init__.py` 收口公共 API，`__all__` 显式。
- 旧 2 文件仅 re-export（无逻辑）。
- 5 处 src 调用方从 `fleetent.skills` 导入；`BUILTIN_SKILLS_DIR` 指向正确且有自检。
- 全量 pytest 绿；ruff 干净；mypy 不新增错误模式。
- 自检：`from fleetent.skills import scan, match`、旧路径 `from fleetent.skill_registry import scan` 均成功。
