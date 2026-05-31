## Why

`tool_registry` / `agent_policy` 早已为工具提供 per-agent 访问控制：`run()` 接收 `allowed_tools`，用 `check_tool_access` 的 fnmatch 白名单过滤暴露给当前 agent 的工具。**Skill 维度却没有任何等价控制**——`skill_registry.match()` 对全体已扫描 Skill 做全局关键词匹配，`agent_loop` 的 `match→load` 链把命中的 Skill 无差别注入 system prompt，与「当前是哪个 agent」无关。

这带来两个治理缺口：

- **无法按 agent 限定 Skill**：一个面向 HR 的 agent 与一个面向运维的 agent 共享同一 skills/ 目录时，二者会注入到对方领域的 Skill，没有边界。工具有白名单，Skill 没有——同一套访问控制语义在两个维度上不一致。
- **默认全局注入过于宽松**：任何 Skill 一旦扫描入索引，就对所有 agent 的请求参与匹配，运维侧无法声明「这个 agent 只允许这些 Skill」。

v1.0 的多 agent 治理要求 Skill 注入像工具一样受 per-agent 白名单约束。本 change 把工具早有的 `allowed_tools` 机制类比到 Skill 维度，引入 `allowed_skills`（可选 `blocked_skills`），并采用 **opt-in 显式绑定**作为默认 posture。

## What Changes

- 为 Skill 注入引入 **per-agent 访问控制**，类比工具的 `allowed_tools`：agent 定义新增 `allowed_skills`（Skill 名 / fnmatch 模式白名单），可选 `blocked_skills`（在白名单命中后再排除）。
- `agent_loop` 的 Skill 注入链（`match→load`）按当前 agent 的 `allowed_skills` / `blocked_skills` **过滤匹配到的 Skill**：仅当命中的 Skill 名匹配白名单且不被黑名单排除时才注入。
- `run()` / `run_stream()` 增加 `allowed_skills: list[str] | None`、`blocked_skills: list[str] | None` 参数透传（类比既有的 `allowed_tools`）。
- **默认 posture = opt-in 显式绑定**：当 agent **未声明** `allowed_skills`（参数为 `None`）时，**不注入任何 Skill**（最严格）。这是相对现状（全局注入）的**行为变更**，下文及 design 明确标注。
- 复用既有 fnmatch 风格（`agent_policy`）做 Skill 名匹配，与工具访问控制保持同一套语义与实现风格。
- **依赖 SK2（`skill-yaml-frontmatter`）**：本 change 排其后，依赖其提供的结构化 frontmatter 索引（Skill 名作为白名单匹配键由 frontmatter `name` 提供，索引已承载结构化元数据）。

## Capabilities

### New Capabilities
- `agent-skill-binding`: Skill 注入的 per-agent 访问控制——agent 定义声明 `allowed_skills`（fnmatch 白名单）/ 可选 `blocked_skills`，`agent_loop` 的 Skill 注入链按当前 agent 过滤命中的 Skill；默认 opt-in，未声明白名单的 agent 不注入任何 Skill。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。skill_registry 的扫描/匹配/加载算法本身不变；本次仅在注入链上新增过滤层。注：默认注入行为由「全局注入」改为「opt-in 不注入」是实现层行为变更，因 Skill 注入此前无既有 spec 承载，故收口在本新 capability 内描述。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/agent_loop.py`：`run()` / `run_stream()` / `run_sync` 的 `match→load` 注入链增加按 `allowed_skills` / `blocked_skills` 的过滤；`run()` / `run_stream()` 新增 `allowed_skills` / `blocked_skills` 参数（类比 `allowed_tools` 的透传位置）。
  - 在 `agent_policy` 复用既有 fnmatch 判定（`check_tool_access` 同款语义）实现 Skill 名白/黑名单匹配，保持单一实现风格。
- **跨域协调（governance 域 / 张亮）**：`allowed_skills` / `blocked_skills` 字段需加在 agent 定义（`agent_store` 的 `Agent` 数据类 + `agents` 表 + 读写路径），该模块属 governance 域。本 change 负责 **Skill 侧过滤逻辑**，agent 字段的落库需与张亮协同添加——见 design「跨域协调点」。
- **配置 / 默认路径**：CLI `run_sync` 无 agent 绑定，opt-in 下默认不注入 Skill；缓解方案（默认 agent 经配置声明 `allowed_skills`）列为 Open Question，本次不强行实现。
- **测试**：扩展 `tests/test_skill_registry.py`（若过滤判定下沉到 registry/policy）与 `tests/test_agent_loop.py`（注入链过滤、opt-in 默认不注入、白/黑名单组合）。LLM 调用按规范 mock，skills 目录隔离到 `tmp_path`。
- **不影响**：关键词匹配算法本身、工具的 `allowed_tools` / `check_tool_access`、Skill frontmatter 解析（SK2 负责）；不引入新依赖。
- **边界（Non-Goals）**：不做内置 Skill 类别 / 全局禁用开关（并行的 `builtin-skills` change）；不改关键词匹配算法；不引入新依赖。
