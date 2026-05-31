## Context

`scan(skills_dir=None)`（skill_registry.py 行 12-15）：当未显式传入 `skills_dir` 时，从环境变量 `MINI_AGENT_SKILLS_DIR` 读取，缺省回落字符串 `"skills"`。这是 mini-agent → fleetent 改名前的遗留前缀。

项目权威文档对该变量的命名：
- CLAUDE.md「环境变量」节：`FLEETENT_SKILLS_DIR`（覆盖 skills/ 目录，默认 ./skills）。
- docs/capabilities/skill.md：依赖 config 的 `FLEETENT_SKILLS_DIR`，并在 v1.0 规划列「环境变量名修复：将 MINI_AGENT_SKILLS_DIR 更正为 FLEETENT_SKILLS_DIR」。

实现与文档当前不一致：实现读旧名，文档写新名。本 change 以文档为准更正实现。

约束（CLAUDE.md）：禁止全局可变状态（路径/环境读取可经 `skills_dir` 参数与 `monkeypatch.setenv` 注入）；mypy strict；行长 100；TDD Hard Gate；测试隔离到 tmp_path。

## Goals / Non-Goals

**Goals:**
- 环境变量名更正为 `FLEETENT_SKILLS_DIR`，与权威文档对齐。
- 未设置时回落 `./skills` 行为不变；显式传参优先级不变。

**Non-Goals:**
- 不保留 `MINI_AGENT_SKILLS_DIR` 兼容别名。
- 不把 skills 目录配置迁入 `Settings`（当前是 `scan` 局部 env 读取；是否纳入 pydantic Settings 是更大的配置统一议题，超出本次最小修正范围）。
- 不改 frontmatter 解析、递归扫描、同名冲突（各自独立 change）。

## Decisions

### D1：直接更正变量名，不保留旧别名
将 `os.environ.get("MINI_AGENT_SKILLS_DIR", "skills")` 改为 `os.environ.get("FLEETENT_SKILLS_DIR", "skills")`。不做「先查新名、再回退旧名」的双读兼容。
**为何**：旧前缀是内部遗留，项目处于 v1.0 前、无对外稳定的环境变量契约；双读会让两个名字长期共存、文档与实现继续发散。一次性更正最干净，并与 CLAUDE.md 唯一事实来源一致。
**Alternatives**：①双读 + 旧名弃用告警——被否，为不存在的外部用户增加长期维护负担；②把路径搬进 `Settings`——被否，属配置统一的更大重构，本次只做最小命名修正。

### D2：保持 `scan(skills_dir=...)` 参数优先
解析优先级维持现状：**显式 `skills_dir` 参数 > `FLEETENT_SKILLS_DIR` 环境变量 > 默认 `"skills"`**。测试已大量用显式传参隔离（见现有 `tests/test_skill_registry.py`），环境变量分支用 `monkeypatch.setenv` 覆盖测试。
**为何**：保持既有调用约定不变，仅改环境变量名这一处，blast radius 最小。

## Risks / Trade-offs

- [若有部署仍按旧名 `MINI_AGENT_SKILLS_DIR` 配置，更名后该配置静默失效（回落默认）] → 经核查旧名为内部遗留、无文档背书该名；更名后与文档一致，反而消除「按文档配置不生效」的更常见陷阱。变更需在发布说明提示。
- [环境变量读取测试可能污染进程级 env] → 用 `monkeypatch.setenv` / `monkeypatch.delenv`，自动在测试后还原，符合项目隔离规范。
