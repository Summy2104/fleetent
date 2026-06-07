## Why

参考项目（claude-code / openclaw / opencode / hermes）的 skill frontmatter 比 fleetent 丰富：可声明"不直接暴露给模型的内部 skill"、"依赖某工具才有意义的 skill"、"运行前需要哪些 env"。fleetent 当前只有 `name/description/tags/platforms/version/enabled/enabled_by_default`，缺这三类常用能力，导致：内部组合 skill 无法隐藏、sandbox 不可用时相关 skill 仍出现在 catalog 误导模型、缺配置的 skill 直到运行才暴露。

## What Changes

- `disable_model_invocation`（bool，默认 false）：true 时 skill 从 `<available_skills>` catalog 隐藏，但 `read_skill(name)` 仍可按名加载（供其他 skill 或 hook 组合调用）
- `requires_tools`（list[str]，默认 []）：声明该 skill 依赖的工具名；catalog **渲染期**检查——任一所需工具不在当前会话可用工具集时，该 skill 从 catalog 隐藏（工具集每会话可变，故渲染期而非 scan 期判定）
- `required_env_vars`（list，默认 []，每项 `name` + 可选 `optional`）：声明运行前需要的 env；不阻塞 catalog，新增 `skill_readiness(name)` helper 报告缺失的非 optional env（供 admin console readiness 显示）

## Capabilities

### New Capabilities

无新 capability。

### Modified Capabilities

- `skill-yaml-frontmatter`：新增三个可选 frontmatter 字段的解析（向后兼容默认值）
- `skill-read-on-demand`：`disable_model_invocation` 与 `requires_tools` 影响 catalog 可见性（read_skill 不受 disable_model_invocation 影响）

## Impact

- **修改文件**：`src/fleetent/skills/registry.py`（SkillEntry / _scan_dir / _disabled_reason / available_skills_prompt / 新 skill_readiness）、`src/fleetent/runtime/loop.py`（两处 catalog 调用传 available_tools）
- **测试**：`tests/unit/test_skill_registry.py`
- **无破坏性变更**：三字段全默认值；`available_tools=None` 时不过滤（兼容）；现有 SKILL.md 解析与渲染不变
