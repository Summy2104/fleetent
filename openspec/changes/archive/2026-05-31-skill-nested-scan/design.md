## Context

`scan(skills_dir)`（skill_registry.py 行 12-24）流程：解析目录路径 → `_index.clear()` → 若目录不存在直接返回 → `for skill_md in base.glob("*/SKILL.md")` 遍历 → 解析 frontmatter → 写入 `_index[name] = (description, str(skill_md))`。

问题集中在 glob 模式 `"*/SKILL.md"`：`*` 只匹配单层目录名，等价于「只看 `skills/<dir>/SKILL.md`」。更深的 `skills/<a>/<b>/SKILL.md` 不被匹配。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态（`scan` 已支持 `skills_dir` 参数与 env 注入，路径可 monkeypatch）；mypy strict；行长 100；TDD Hard Gate；测试 skills 目录隔离到 tmp_path。

## Goals / Non-Goals

**Goals:**
- 递归发现 `skills/` 下任意深度的 `SKILL.md` 并纳入索引。
- 保持单层 Skill 的发现/解析/匹配行为完全兼容。
- 保持目录不存在时安全返回的既有兜底。

**Non-Goals:**
- 不改 frontmatter 解析（skill-yaml-frontmatter change）。
- 不处理因递归而更易出现的同名冲突（skill-name-conflict change 负责告警与确定性选定）；本 change 仅扩大发现范围，冲突时沿用现状行为（后写覆盖），并在 Risks 标注由后续 change 收口。
- 不修复环境变量名（skill-env-var change）。
- 不限制递归深度、不做符号链接环检测（当前 skills 为本地受控目录，过度防御无必要）。

## Decisions

### D1：`glob("*/SKILL.md")` → `rglob("SKILL.md")`
用 `pathlib.Path.rglob("SKILL.md")` 递归匹配任意层级的 `SKILL.md`，替换原一层 glob。其余建索引逻辑（frontmatter 解析、name 回落、写 `_index`）保持不变。
**为何**：`rglob` 是标准库直接提供的递归 glob，改动最小、语义精确，无新依赖；与既有「逐个 SKILL.md 建索引」结构天然契合。
**Alternatives**：①`os.walk` 手写递归——被否，比 `rglob` 啰嗦且易错；②固定支持「两层」`glob("*/*/SKILL.md")`——被否，仍是硬编码深度，无法满足「任意层级」诉求。

### D2：name 回落仍取 SKILL.md 的直接父目录名
递归后 `skill_md.parent.name` 仍是该 SKILL.md 最近一层目录名（如 `skills/crm/contracts/SKILL.md` 回落为 `contracts`）。保持现状语义：name 优先取 frontmatter，缺失才回落直接父目录名。
**为何**：与现有单层行为一致，最小惊讶；frontmatter 显式 `name` 是推荐实践，回落仅兜底。
**Alternatives**：用相对 skills 根的路径拼接作为 name（如 `crm/contracts`）——被否，会改变现有 name 语义并牵连 match/load 的键，超出本 change 范围。

### D3：遍历顺序的确定性留给后续 change
`rglob` 的返回顺序在不同平台/文件系统下不保证稳定，这会让同名冲突的「谁覆盖谁」不确定。本 change 不引入排序逻辑，确定性选定与告警由 skill-name-conflict change 统一处理，避免两个并行 change 的实现交叠。
**为何**：单一职责；冲突处理是独立 capability（SK8），在那里一并定确定性规则更内聚。

## Risks / Trade-offs

- [递归扫描更易暴露同名 Skill，现状为静默覆盖且顺序不确定] → 本 change 仅扩大发现范围，冲突告警与确定性选定由 skill-name-conflict change（SK8）收口；两 change 合并后行为完整。
- [深目录下误放的 SKILL.md（如示例/模板）会被意外索引] → 属预期行为变更，由 Skill 作者负责目录卫生；后续禁用机制可显式排除，不在本 change 范围。
- [大目录递归的性能] → `scan` 在服务启动 lifespan 仅跑一次，Skill 数量级有限，递归开销可忽略。
