## Why

通过 `POST /admin/skills`（带 `content`）创建的 skill，其内容**从不落盘**。`create_skill` → `_publish` 只写 DB 状态（`skill_admin_store.set_audit_result` / `set_status`）并触发 `engine_reload()`，`body.content` 在审计后被直接丢弃，从未写成 `<skills_dir>/<name>/SKILL.md`。

由此产生一连串失效：

- `GET /admin/skills/{name}/content` 返回 404 `skill content not found`（`engine_skill_content` → `registry.load` 在索引里找不到该 skill）。
- `engine_reload()` rescan skills pool 时拿不到任何文件，新建 skill **永远不会进入 registry 索引**，对任何 agent 不可匹配/不可注入。
- node 的 per-agent skill 文件同步（`materialize.skill_bundles_for_agent`）从 pool 目录读取 `SKILL.md`，文件不存在 → 绑定该 skill 的 agent 同步不到 skill 文件。

对比同文件的 `_import_skill_dir`（目录导入路径）：它 `shutil.copytree` 把整个 skill 目录写入 `engine_skills_dir()` 后才 `_publish`，因此导入可用、而 inline 创建不可用。这是 inline 创建路径独有的落盘缺口。

## What Changes

- `create_skill` 在审计**通过**（verdict 非 `rejected`）后，SHALL 把 `content` 落盘为 `<engine_skills_dir()>/<name>/SKILL.md`，随后由既有 `engine_reload()` rescan 进入索引。
- 落盘前 SHALL 用 `_safe_skill_name` 校验 skill 名（防路径穿越），不安全名返回 422、不落盘。
- verdict 为 `rejected`（quarantine）时 MUST NOT 落盘，与现有 quarantine 语义一致。
- 行为对齐 `_import_skill_dir`：两条创建路径（inline 创建 / 目录导入）此后都把文件落到同一 skills pool。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `skill-admin-api`: 「Upload or create with frontmatter validation and audit gating」requirement 补一条——inline 创建（`POST /admin/skills` 带 `content`）在审计通过后 SHALL 把内容落盘为 `<skills_dir>/<name>/SKILL.md`，使内容可读回、可被 registry rescan、可被 node 同步给 agent。

## Impact

- **owning package**: `platform/`（`platform/skill_management/skill_admin_api.py` 的 `create_skill` 落盘逻辑）
- **public API surface**: 无新增对外 API；`POST /admin/skills` 的契约语义被修正（创建即落盘），HTTP 形态不变。
- **owned tables**: 无（仅写文件系统 skills pool，不触碰持久化表）
- **config namespace**: 无
- **cross-module dependencies**: 经既有可注入 seam `engine_skills_dir()` / `engine_reload()`（默认委托 `skills.registry`）落盘与 rescan；不新增跨包依赖，不 import platform 以外的运行时内部实现。`materialize.skill_bundles_for_agent`（node desired-state 投递）为下游消费者，文件落盘后自然取到。
- **migration / shim plan**: 无 schema/迁移。纯行为修正（补齐落盘）；既有 quarantine（rejected 不落盘）/ 导入路径行为不变。
- 受影响代码：`src/fleetent/platform/skill_management/skill_admin_api.py`
- **范围外**：`PUT /admin/skills/{name}`（edit）同样未把编辑内容落盘，属同类缺口，但本 change 仅修复创建路径（bug 复现与诉求所在）；如需一并修复另开。
