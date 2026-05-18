# Skill System Design

## 什么是 Skill

Skill 是遵循 [Agent Skills](https://agentskills.io) 开放标准的知识/指令包。不是可调用的函数（tool），而是注入进 LLM context 的操作指令和领域知识。

```
my-skill/
├── SKILL.md     # 必须：frontmatter metadata + 操作指令
├── scripts/     # 可选：可执行脚本
├── references/  # 可选：参考文档
└── assets/      # 可选：模板资源
```

SKILL.md 最小结构：

```yaml
---
name: my-skill
description: 什么场景下用这个 skill（Claude 用这段决定何时激活）
---

## 指令内容

具体的操作步骤、规范、知识...
```

## 和 Tool 的区别

| | Tool | Skill |
|--|------|-------|
| 调用方式 | LLM 通过 function call 调用 | 内容注入进 messages |
| 执行结果 | 返回数据给 LLM | LLM 按指令执行 |
| 典型用途 | 查时间、读文件、调 API | 代码审查流程、部署规范、业务操作指引 |

## Progressive Disclosure（渐进加载）

```
启动时：只加载 name + description（context 占用极小）
匹配时：任务和某 skill 相关 → 加载完整 SKILL.md 注入 context
执行时：LLM 按 SKILL.md 指令操作，必要时执行脚本
```

## Harness 层实现（不是独立模块）

Skill 加载不需要新模块，在 agent_loop.py 的 while 循环开头加一步：

```python
# agent_loop.run() 里，LLM 调用前
matched_skill = skill_registry.match(user_input)
if matched_skill and not already_loaded(matched_skill, messages):
    skill_content = skill_registry.load(matched_skill)
    messages.append({"role": "system", "content": skill_content})
```

已加载的 skill 内容在会话内持久保留，不重复注入。

## skill_registry.py 的职责

1. **启动时扫描** `skills/` 目录，建立 `{name: (description, path)}` 索引
2. **match(user_input)**：把用户输入和各 skill 的 description 做相关性判断（简单版：关键词匹配；进阶版：embedding 相似度）
3. **load(name)**：读取完整 SKILL.md，返回字符串
4. **list()**：返回所有 skill 的 name + description，注入 system prompt 让 LLM 知道有哪些 skill 可用

## Skills 目录结构

```
skills/
  summarize-doc/
    SKILL.md
  code-review/
    SKILL.md
    references/checklist.md
  deploy/
    SKILL.md
    scripts/run.sh
```

优先级（多级同名时）：project > personal > enterprise，和 Claude Code 标准一致。

## Frontmatter 支持的字段（最小集）

| 字段 | 说明 |
|------|------|
| `name` | skill 名称，默认用目录名 |
| `description` | LLM 用这段判断何时激活，必填 |
| `disable-model-invocation` | `true` 表示只能用户手动调用（`/skill-name`） |
| `user-invocable` | `false` 表示只有 LLM 自动激活，不出现在菜单 |

## 和 Claude Code 实现的差异

Claude Code 在 harness 层通过文件监控透明加载 skill，LLM 感知不到加载过程。

mini-agent 在 agent_loop 里显式 match + inject，效果等价，实现更简单。
