## Why

`skill_registry.scan()`（行 15）当前从环境变量读取 skills 目录：

```python
skills_dir = os.environ.get("MINI_AGENT_SKILLS_DIR", "skills")
```

变量名 `MINI_AGENT_SKILLS_DIR` 是项目改名（mini-agent → fleetent）前的遗留前缀。CLAUDE.md「环境变量」一节与 docs/capabilities/skill.md 均规定正确名称为 `FLEETENT_SKILLS_DIR`，文档与实现已不一致——按文档配置 `FLEETENT_SKILLS_DIR` 的运维不会生效，是隐性配置陷阱。

> 现状核实：仓库实现代码实际使用的仍是旧名 `MINI_AGENT_SKILLS_DIR`（skill_registry.py 行 15），并非已更名。故本 change 是一次**真实的重命名**，范围非「仅确认/补测试」。

## What Changes

- 将 `scan()` 读取的环境变量名从 `MINI_AGENT_SKILLS_DIR` 更正为 `FLEETENT_SKILLS_DIR`，与 CLAUDE.md 及 docs/capabilities/skill.md 对齐。
- 默认值保持 `"skills"`（未设置环境变量时行为不变）。
- 不保留旧名兼容别名：旧前缀属内部遗留、项目尚在 v1.0 前、无外部稳定契约，直接更正以免长期维护两个名字。

## Capabilities

### New Capabilities
- `skill-env-var`: skill_registry 通过环境变量 `FLEETENT_SKILLS_DIR` 覆盖 skills 目录路径，未设置时回落默认 `./skills`。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。仅更正环境变量名，覆盖/回落语义不变。 -->

## Impact

- **代码**：修改 `src/fleetent/skill_registry.py` 行 15：`os.environ.get("MINI_AGENT_SKILLS_DIR", "skills")` → `os.environ.get("FLEETENT_SKILLS_DIR", "skills")`。
- **依赖**：无新增依赖。
- **测试**：扩展 `tests/test_skill_registry.py`：设置 `FLEETENT_SKILLS_DIR`（`monkeypatch.setenv`）时 `scan()` 使用该路径；未设置时回落 `./skills`；旧名 `MINI_AGENT_SKILLS_DIR` 不再被读取（防回归）。环境变量与 skills 目录隔离到 `tmp_path`。
- **不影响**：frontmatter 解析、递归扫描、同名冲突处理（各自独立 change）、匹配与注入；`scan(skills_dir=...)` 显式传参路径优先级不变（参数 > 环境变量 > 默认）。
