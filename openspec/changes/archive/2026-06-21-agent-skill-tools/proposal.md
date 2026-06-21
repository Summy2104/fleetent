## Why

fleetent agent 运行时目前只有 `read_skill(name)` 一个模型可调用的 skill 工具：它只能返回 SKILL.md 正文，无法读取 skill 目录下的 `references/`、`examples/` 等支撑文件；catalog 被 cap/截断后模型无法按需查询被裁掉的 skill；且模型无法在用户显式要求时创建/修订 skill（现有 `write_skill` 仅供 reflection 离线调用）。对标 claude-code / opencode / hermes-agent / openclaw 后，补齐这批 agent 侧 skill 操作工具，让 read-on-demand 更完整、并提供受控的用户显式驱动的 skill 自创能力。

## What Changes

- **增强 `read_skill`**：增加可选 `file_path` 参数，按相对路径读取 skill 目录下的支撑文件（`references/`、`examples/` 等），带路径遍历防护；`file_path` 省略时行为完全不变。
- **新增 `list_skills(keyword=None, category=None)` 工具**：返回 name + description 的轻量索引，按关键词/类别过滤。作为常驻 catalog 被 cap/截断或模型想按主题过滤时的按需查询逃生口；**不改动**现有 catalog 注入逻辑。
- **新增 `skill_manage(action, name, ...)` 写工具**：action ∈ `create / patch / edit / delete / write_file / remove_file`，供用户显式驱动的 skill 自创/修订。
  - 每次写操作 **强制走 governance approval gate**（标强制审批风险级），用户确认后才生效。
  - 只写 **per-agent skills 目录**；builtin/bundled 按目录来源判定为只读，不能改/删。
  - 写入时 **拒绝命中 severe 注入审计** 的内容持久化；create 时写一行 provenance（来源标记 + 时间戳）。
  - 纯 agent 侧，**绝不写 platform 表**；usage 复用既有 `skill_hit` trace，不引入 curator。
- **新增配置开关 `skill_authoring_enabled`（per-agent，默认 `false`）**：仅当显式开启时 `skill_manage` 工具才进入该 agent 的 schema（schema-build 时门控）。
- **不做**：跨 agent / 跨部署 skill 分发，不接任何公网 Hub（违反数据主权）。

## Capabilities

### New Capabilities
- `agent-skill-authoring`: agent 侧模型可调用的 skill 自创/修订工具 `skill_manage`——CRUD 动作、强制审批门、per-agent-only 写入、builtin 只读、写入期注入审计、provenance、默认关闭的配置门、agent/platform 隔离。

### Modified Capabilities
- `skill-read-on-demand`: 在既有 read-on-demand 发现面上新增两条要求——(1) `read_skill` 支持可选 `file_path` 读取 skill 目录下支撑文件（遍历防护）；(2) 新增 `list_skills` 按需查询工具（关键词/类别过滤），作为 catalog 被 cap/截断时的查询逃生口。

## Impact

- **owning package**：`tools/`（`builtin_tools.py` 新增/增强工具）+ `skills/`（`registry.py` 新增读取支撑文件、过滤查询、删除/写文件、provenance、写入审计的 public 函数）。两者均为 **agent 运行时模块**，零 `fleetent.platform.*` import，满足「无 platform 也能 `fleetent agent run`」基线。
- **public API surface**：新增工具 `list_skills`、`skill_manage`；增强 `read_skill`。`skills/registry` 新增/扩展：读取支撑文件、`list_skills` 过滤、`delete_skill`/`write_skill_file`/`remove_skill_file`、单文件写入期审计 helper（复用 `audit.py`）。
- **owned tables**：无（skill 全为文件，provenance 落 SKILL.md frontmatter）。
- **config namespace**：`AgentFile.skill_authoring_enabled: bool = False`（agent.yaml）。
- **cross-module dependencies**：`tools → skills` public API；`skill_manage` 经现有 `@tool(risk_level=...)` + `governance.approval_policy` 审批机制（既有 tools→governance 边）。
- **migration / shim plan**：无模块迁移；无新增持久化表；不触碰 platform 管理表。
- **观测**：`read_skill` file_path 读取与 `skill_manage` 写操作复用 agent 侧 observability trace（`skill_hit` 及同类），不写 platform store。
