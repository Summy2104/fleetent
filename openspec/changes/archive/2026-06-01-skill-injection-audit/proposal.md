## Why

> 注:本 change 原设计建立在 SK1 的「L1 清单 + L2 关键词命中注入」地基上。波次2 skill 轨重规划(2026-05-31)后,skill 注入地基已是 `skill-read-on-demand`(已归档):框架注入 `<available_skills>` 清单(`available_skills_prompt`,含 name/description/location),模型按需调 `read_skill` 工具读全文,无关键词匹配。本文件已**按 read-on-demand 重写**。

SKILL.md 是会进入 system prompt 的内容,且 skills 目录可能纳入用户/第三方贡献的 Skill。恶意或被污染的 SKILL.md 可藏 prompt 注入串(「忽略之前的指令」「伪装 system 指令」「shell 注入命令」等)。在 read-on-demand 模型下,Skill 内容经两个面到达模型:

- **清单面**:`available_skills_prompt` 把每个已启用 Skill 的 **name + description** 拼进 system prompt 稳定前缀。
- **全文面**:模型调 `read_skill(name)` 取回**完整 SKILL.md 正文**。

注入串可能藏在 description(清单面)或正文(全文面)。需要一道**静态安全审计闸门**在扫描入索引时检测,拒绝严重注入的 Skill 经这两个面到达模型。

## What Changes

- 新增**注入审计层**(`src/fleetent/skill_audit.py`):对 SKILL.md **正文 + description 字段**运行一组**已知注入模式检测规则**,每条带**严重度**(`suspicious` / `severe`)。
- 规则集覆盖 docs 列举的若干类,实现为模块级**不可变规则表**(正则/关键短语 + 严重度 + 规则标识),可被测试只读引用。
- 审计接入 `scan()` 索引流程:每个 Skill 在纳入前先审计。
  - **命中 severe**:打 `audit_blocked` 标志(留在 `_index`、不删),`available_skills_prompt`(清单)MUST 跳过被标记项、`read_skill` MUST 拒绝返回被标记项的全文——**name/description(清单面)与正文(全文面)均永不到达模型**;记审计日志。`load()` 忽略该标志、仍按名返回原文供人工排查。
  - **命中 suspicious**(无 severe):仍纳入清单、`read_skill` 仍可读,但**记审计日志** + 启动控制台告警。
- 纯静态规则匹配,**不调用 LLM**(确定性、可单测、数据不出内网、无外部依赖)。

## Capabilities

### New Capabilities
- `skill-injection-audit`: Skill 内容的静态注入审计——扫描时对 SKILL.md 正文 + description 运行已知注入模式规则(带严重度);命中 severe 打 `audit_blocked`(从 `available_skills_prompt` 清单排除、`read_skill` 拒绝返回,`load()` 仍可取原文)、命中 suspicious 记审计日志 + 启动告警;纯静态规则、不调用 LLM。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。SK2 frontmatter 解析、read-on-demand 的清单/read_skill 机制不变;本次在「纳入清单/可被 read_skill」前新增审计闸门。 -->

## Impact

- **代码**:新增 `src/fleetent/skill_audit.py`(规则表 + `audit(content, description) -> list[hit]`);`skill_registry`:`SkillEntry` 加 `audit_blocked: bool=False`,`scan()` 入索引前审计并标注,`available_skills_prompt` 跳过 `audit_blocked`,`read_skill` 对 `audit_blocked` 返回明确拒绝文本;审计命中写结构化日志,启动时 suspicious 控制台告警。
- **测试**:规则表命中(severe/suspicious、正文 + description)、severe→不入清单 + read_skill 拒绝 + load 仍可取、suspicious→入清单但记日志/告警、干净 Skill 无告警。
- **不影响**:`load()` 按名取原文契约(审计只约束清单/read_skill 自动到达模型的面);`match()`/`list_skills()`;不引入新依赖、不调 LLM。
- **依赖**:`skill-read-on-demand`(已归档)——审计的两个执行点是其 `available_skills_prompt` 与 `read_skill`。与 `skill-disable-mechanism`(SK6,改写中)的禁用来源 trace 协同:`audit_blocked` 作为禁用来源之一被 SK6 记录。
