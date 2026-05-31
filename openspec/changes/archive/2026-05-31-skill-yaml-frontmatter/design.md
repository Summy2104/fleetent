## Context

`skill_registry._parse_frontmatter(content)` 当前实现（行 52-64）：检查 `content` 是否以 `---` 开头，用 `content.split("---", 2)` 切出中段，逐行 `partition(":")` 取键值，全部当字符串塞进 dict。它无法表达 YAML 列表/布尔/数字，且任何「不符合预期」的情况都返回 dict（空或部分），`scan()` 据此建索引，从不报错。

`scan()`（行 12-24）调用 `_parse_frontmatter` 后取 `name`（缺失回落目录名）与 `description`（缺失空串），写入 `_index[name] = (description, str(skill_md))`。索引类型是 `dict[str, tuple[str, str]]`。

`pyyaml` 已在 `pyproject.toml`（行 19 `pyyaml>=6.0.3`、行 42 `types-pyyaml`）声明，可直接 `import yaml`，无新依赖。项目日志统一用 structlog（见 config.py），warning 走结构化日志。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态（`scan` 已支持 `skills_dir` 参数与 env 注入，路径可 monkeypatch）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 skills 目录隔离到 tmp_path。

## Goals / Non-Goals

**Goals:**
- 用标准 YAML 解析器完整解析 frontmatter，正确处理标量/列表/布尔/数字/嵌套。
- 识别并承载扩展字段 `tags` / `platforms` / `version` / `enabled_by_default`。
- 解析失败明确报警（结构化 warning，含路径与原因）并跳过该 Skill，不静默纳入。
- 保持 `match` / `load` / `list_skills` 既有对外行为兼容。

**Non-Goals:**
- 不实现递归/深层嵌套扫描（skill-nested-scan change）。
- 不处理同名冲突告警（skill-name-conflict change）。
- 不修复环境变量名（skill-env-var change）。
- 不实现渐进式加载（L1/L2/L3）、热加载、安全审计、禁用机制（各自后续）。
- `enabled_by_default=false` 的字段本次仅解析并存储，不接线到匹配过滤逻辑（禁用机制是独立后续 change）。

## Decisions

### D1：用 `yaml.safe_load` 替换按行扫描
`_parse_frontmatter` 改为：定位首尾 `---` 边界，取中段交给 `yaml.safe_load`。用 `safe_load`（而非 `load`）避免任意对象构造的安全风险（Skill 内容可能来自不完全可信来源）。
**为何**：标准解析器正确支持 YAML 全部语法；`safe_load` 与「数据不出内网 + 内容可能含注入」的安全取向一致。
**Alternatives**：①继续手写扩展解析器以支持列表——被否，重复造轮子且边界 case 永远补不全，pyyaml 已是依赖；②`yaml.full_load`/`yaml.load`——被否，可构造任意 Python 对象，安全面更大。

### D2：解析失败 = 返回 None，由 scan 跳过 + 报警
`_parse_frontmatter` 在以下情况视为失败并返回 `None`：内容不以 `---` 开头 / 找不到闭合 `---` / `yaml.safe_load` 抛 `yaml.YAMLError` / 解析结果顶层不是映射（dict）。`scan()` 收到 `None` 时记一条结构化 warning（字段含 SKILL.md 路径与失败摘要）并 `continue` 跳过该 Skill，不写入索引。
**为何**：纠正「静默吞掉」缺陷——写坏的 Skill 不该悄悄不生效；返回 None 是显式失败信号，与「成功返回 dict」清晰二分，便于单测。
**Alternatives**：①失败抛异常中断整次 scan——被否，一个坏 Skill 不应拖垮全部扫描（scan 在服务启动 lifespan 跑，应尽量健壮）；②失败返回空 dict 但记日志——被否，空 dict 与「合法但无字段」无法区分，仍可能误纳入。

### D3：索引承载结构化元数据
将 `_index` 值从 `tuple[str, str]`（description, path）扩展为包含 `description` / `path` / `tags` / `platforms` / `version` / `enabled_by_default` 的结构（dataclass 或 dict）。`match` 仍只读 `description`，`load` 仍只读 `path`，`list_skills` 输出保持 `{"name", "description"}` 不变（可后续按需扩展，但本次不改其契约以免牵连调用方）。缺省值：`tags=[]`、`platforms=[]`、`version=None`、`enabled_by_default=True`。
**为何**：扩展字段要有存放处，但对外可观察行为（match/load/list_skills）保持兼容，降低 blast radius。
**Alternatives**：保持 tuple 仅追加元素——被否，位置元组扩展易错且可读性差，结构化承载更清晰且符合「新模块结构含数据类」。

### D4：扩展字段的类型归一
`tags` / `platforms` 解析后若为单个标量则归一为单元素列表，若缺失则空列表；`enabled_by_default` 解析为布尔（缺失默认 `True`）；`version` 归一为字符串（数字也转字符串）。归一在 `scan`/构建索引处完成，避免下游每次判型。
**为何**：YAML 允许 `tags: crm`（标量）或 `tags: [crm, sales]`（列表），下游应拿到一致类型；缺省值让未声明扩展字段的旧 Skill 无缝兼容。

## Risks / Trade-offs

- [改用 yaml 解析后，原本「能被宽松行扫描勉强解析」的非法 frontmatter 现在会报失败跳过] → 这是期望行为（暴露坏 Skill）；为兼容，合法的简单 `key: value` frontmatter 行为与现状一致，用例覆盖现有 SKILL.md 形态。
- [`safe_load` 对纯文本（无 `---`）会把整个 body 当 YAML] → 通过先校验首尾 `---` 边界、只把中段喂给解析器规避；无边界直接判失败。
- [索引结构变更可能波及读取 `_index` 的其它模块] → 经核查 `_index` 仅 `skill_registry` 内部使用，`match`/`load`/`list_skills` 为唯一对外读取面，三者契约保持不变。
- [扩展字段暂未接线（如 enabled_by_default 不过滤）被误认为已生效] → spec 与 Non-Goals 明确本次仅解析存储，过滤是禁用机制后续 change。
