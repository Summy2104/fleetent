## Why

技能（skill）目前对每个 agent 全量可见：`available_skills_prompt()` 把所有「已启用」（未被四来源禁用）的 skill 都渲染进 `<available_skills>` 清单，无论该 agent 是否需要。on-premises 多团队场景下，一个 agent 往往只该接触自己职责范围内的少数 skill；把全部已启用 skill 塞进每个 agent 的清单既污染上下文、又让模型可能去 `read_skill` 不相关的指令。需要一个 per-agent 的「清单可见性收窄」机制，让每个 agent 只看见被授权的 skill 子集。

注意：这是**清单可见性收窄，不是授权边界**。遵守项目既定原则「skill 不是授权边界，tool 才是」——模型即便读了某 SKILL.md，仍越不过 `allowed_tools` 白名单与风险审批门。`allowed_skills` 只决定哪些 skill 进 `<available_skills>` 清单 / 可被默认发现，不构成能力授权。

## What Changes

- `agent_store.Agent` 新增 `allowed_skills: list[str]` 字段（默认空列表），`agents` 表加 `allowed_skills TEXT NOT NULL DEFAULT '[]'` 列（`_init_db` 的 `CREATE TABLE` 内联 + alembic 004 迁移 `op.add_column`，参照 003 plugins，**非运行时裸 ALTER**）；`create_agent` / `_SELECT_COLS` / `_row_to_agent` 读写该字段（JSON 序列化，照 `plugins` 同款）。
- **空 = 不限制（向后兼容）**：`allowed_skills` 为空 / None 时不收窄——全部已启用 skill 仍可见（等于现状）；非空时清单只保留「名字在 `allowed_skills` 且未被禁用」的 skill。这与 `plugins`（空 = 无）相反，因为 skill 现状默认全可见，改成「空 = 无」会破坏既有 agent，故此处取「空 = 不限制」。
- `skill_registry.available_skills_prompt()` 新增 `allowed_skills: list[str] | None = None` 参数；非空时在既有 `_disabled_reason` 谓词处**叠加**收窄（命中 `allowed_skills` 且未被禁用才进清单）。
- `agent_loop.run()` / `run_stream()` 新增 `allowed_skills: list[str] | None = None` 入参并透传给 catalog 构建处；调用方（server.py / im_gateway normalizer）从 agent 定义取 `agent.allowed_skills` 传入（无 agent 绑定 → None → 不收窄），参照 `agent_features` / `sandbox_mode` 的透传方式。
- **不动授权**：不改 tool 访问控制、不改 `read_skill` 的显式 `load`（按名 load 仍可，与既有「load 不受禁用约束」口径一致）；收窄只作用于**清单可见性**。

## Capabilities

### New Capabilities
- `agent-skill-scoping`: per-agent 的 `allowed_skills` 清单可见性收窄——字段持久化（默认空）、空 = 不限制（向后兼容现状全可见）、非空收窄到所列 skill、与既有 skill 禁用谓词叠加、明确为「仅可见性、非授权边界」（不改 tool 访问控制与按名 `read_skill` 的 load）。

### Modified Capabilities
- `agent-definition`: `Agent` 数据类与 `agents` 表新增 `allowed_skills: list[str]` 字段（修改既有「Agent definition storage」与「Schema」需求），照 `plugins` 同款持久化为 JSON array text、默认 `[]`、旧行向后兼容。这是对既有 agent 定义存储的需求级扩展，见 `specs/agent-definition/spec.md`。

## Impact

- **代码**：
  - `src/fleetent/agent_store.py`：`Agent` 加 `allowed_skills: list[str]`；`agents` 表 `CREATE TABLE` 内联加 `allowed_skills TEXT NOT NULL DEFAULT '[]'`；`create_agent` / `_SELECT_COLS` / `_row_to_agent` 读写（JSON 序列化，`or "[]"` 兜底旧行）。
  - 新增 `migrations/versions/004_add_agent_allowed_skills.py`：`op.add_column` 加 `allowed_skills`（参照 003，down_revision="003"）。
  - `src/fleetent/skill_registry.py`：`available_skills_prompt` 加 `allowed_skills` 参数，在 `_disabled_reason` 过滤处叠加收窄。
  - `src/fleetent/agent_loop.py`：`run()` / `run_stream()` 加 `allowed_skills` 入参，透传给 catalog 构建（run_stream 内 `available_skills_prompt` 调用；run() 经其入口透传，CLI 路径 None）。
  - `src/fleetent/server.py`：从 `agent.allowed_skills` 取出并经 kwargs 传入 `run_stream`。
  - `src/fleetent/im_gateway/normalizer.py`：构建 catalog 时把 `agent.allowed_skills` 传给 `available_skills_prompt`。
- **测试**：
  - `tests/test_skill_registry.py`：`available_skills_prompt(allowed_skills=...)` 的空 = 全可见、非空收窄、与禁用叠加。
  - `tests/test_agent_store.py`：`allowed_skills` 字段读写、默认空、旧行向后兼容。
  - `tests/test_migrations.py`：004 后 `agents` 含 `allowed_skills` 列。
  - `agent_loop` / server / normalizer 透传断言。全部 `tmp_path + monkeypatch` 隔离，skill 目录隔离，LLM mock。
- **不影响**：tool 访问控制（`allowed_tools` / `check_tool_access`）、`read_skill` 按名 load、plugins、permission_gate、context 压缩、终止与错误分类、MCP。
- **依赖**：无新增依赖（标准库 `json` + 既有 alembic）。
