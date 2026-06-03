## Context

> 按波次2 skill 轨重规划(2026-05-31)改写:地基为 `skill-read-on-demand`(已归档),不再有 SK1 的 L1/L2/match。

read-on-demand 下 Skill 内容经两个面到达模型:`available_skills_prompt` 拼入的 **name+description**(清单面),`read_skill(name)` 返回的**正文**(全文面)。注入审计需在扫描入索引时检测,拒绝 severe Skill 经这两个面到达模型。

约束(CLAUDE.md):禁止 AI 框架;不调用 LLM(纯静态);禁止全局可变状态(规则表不可变模块常量);新模块结构;mypy strict;行长 100;TDD;测试隔离。

## Goals / Non-Goals

**Goals:**
- 扫描时静态审计 SKILL.md 正文 + description,带严重度规则表。
- severe → `audit_blocked`:从 `available_skills_prompt` 清单排除 + `read_skill` 拒绝;`load()` 仍返回原文。
- suspicious → 仍可用,记审计日志 + 启动告警。
- 纯静态、不调 LLM、数据不出内网。

**Non-Goals:**
- 不调 LLM 做语义审计(确定性静态规则)。
- 不删 `_index` 条目(用标志位,`load()` 仍可取供排查)。
- 不实现禁用来源 trace(SK6 负责,`audit_blocked` 作为其来源之一)。

## Decisions

### D1:审计层独立模块 + 不可变规则表
`skill_audit.py`:`_RULES`(模块级不可变:正则/关键短语 + 严重度 + 规则标识),`audit(content, description) -> list[Hit]`。规则覆盖 docs 列举类(忽略指令/伪装 system/shell 注入等)。
**为何**:静态可单测、与 registry 解耦;不可变规则表符合「禁止全局可变状态」。

### D2:两个执行点 = 清单排除 + read_skill 拒绝
`SkillEntry` 加 `audit_blocked: bool`。`scan()` 入索引前对每个 Skill `audit(body, description)`,有 severe 命中则置 `audit_blocked=True`。
- `available_skills_prompt`:跳过 `audit_blocked`(同跳过 disabled)。
- `read_skill`:对 `audit_blocked` 返回拒绝文本(在 `load()` 之前检查)。
- `load()`:不检查 `audit_blocked`,仍返回原文。
**为何**:这两个面是 read-on-demand 下 Skill 到达模型的全部途径;`load()` 作排查出口与 SK6/已批准的「load 不受禁用约束」口径一致。

### D3:severity 处置
severe → audit_blocked(双面拒绝)+ 审计日志;suspicious(无 severe)→ 仍可用 + 审计日志 + 启动控制台告警。审计命中均写结构化日志(路径/规则/严重度/处置)。

## Risks / Trade-offs

- [静态规则有限,绕过可能] → 覆盖已知高危类即显著降风险;可观察审计轨迹便于补规则;非声称完备。
- [read_skill 检查 audit_blocked 增一次索引查询] → 廉价(已有 `_index` 查询);拒绝在 load 前短路。
- [description 也需审计(清单面)] → audit 入参含 description,清单排除覆盖。

## Open Questions

- 规则表初始覆盖范围 / 严重度划分细节,实现时按 docs 列举类落地,可后续扩。
- 审计日志是否进 eval_logger trace 还是独立审计日志:与 SK6 的禁用来源 trace 协同时统一(`audit_blocked` 作 SK6 的一个来源)。
