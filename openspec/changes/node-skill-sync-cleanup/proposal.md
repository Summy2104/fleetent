## Why

托管部署下 node 拉起 managed agent 时，desired-state 只下发 `agent.yaml`（含 `allowed_skills` 技能**名**），但 agent 进程从 `<home>/skills/` 读 skill **文件**（`runtime/agent_app.py` 固定 `scan_skills(skills_dir=<home>/skills)`，注释明示 self-contained、**从不读 `FLEETENT_SKILLS_DIR`**）。node 从不把平台 skill 文件落到 agent 侧 → 托管 agent 启动后 catalog 里这些 skill 全缺文件，`read_skill` 失败。这是托管路径相对单机 `materialize`（`_copy_skills` 会把 pool 拷进 `<home>/skills`）的硬缺口。

同时 reconcile 的「agent 从期望态消失」分支只 `stop`、不删 `<home>/agents/<name>` 目录（orphan 目录会被 `_local_agent_names()` 永久重列、ledger 永不收缩），且 stop **未按来源门控**——platform 短暂不可达回落 cache（甚至空 cache）时仍会停掉本地在跑的 agent，违反既有 `node-supervisor` spec「缓存缺失时…不误停在跑的 agent」。

## What Changes

- **平台下发 skill 文件**：`GET /nodes/{id}/desired-state` 每个 agent 条目 SHALL 新增 `skills` 字段，附带该 agent **绑定/allowed**（经 `agent_skills` 矩阵或 authored `allowed_skills` 收窄、再扣除全局 disabled）的 skill 的文件内容（结构 `[{name, version, files:[{path, content_b64}]}]`，base64 二进制安全）；未收窄的 agent 下发整个 pool。剥密规则不变（skill 文件非 secret）。
- **node 落盘 + 加载接线**：reconcile materialize home 时 SHALL 把下发的 skill 文件写到 `<home>/agents/<name>/skills/<skill>/...`——即 agent 启动 `scan` 的目录，**无需也不注入 `FLEETENT_SKILLS_DIR`**（agent 进程固定忽略该变量，注入是无效死代码）。builtin skill 由 agent 侧从包内 `BUILTIN_SKILLS_DIR` 直接 scan，node 不触碰，二者天然共存（同名时平台 skill 在 user-tier 覆盖 builtin）。
- **skill 变更触发重启 + 清理**：node SHALL 用一份 per-agent skill manifest（`<home>/agents/<name>/.node-skills.json`，记 `{skill_name: version}`）判定 skill 增删改；变更则优雅停后重拉（agent 无热重载、boot 时读 skill）。移除的 skill SHALL 清理其目录；node **只清理自己 manifest 记录过的 skill**，绝不删 builtin / operator 自留 skill。
- **删除清理 + 缓存安全**：reconcile 对「权威 remote 期望态里已消失」的 agent，SHALL 在 stop（舱壁化、失败只记日志）后删除其 `<home>/agents/<name>` 整个目录并从 ledger 移除该条目；**cache 回落态下 MUST NOT stop 或删除**（修复既有 spec 合规缺口）。

## Capabilities

### New Capabilities
<!-- 无新增 capability；复用既有 node-supervisor / node-desired-state-api -->

### Modified Capabilities
- `node-desired-state-api`：期望态响应每 agent 条目新增一条 requirement——附带其绑定/allowed skill 的文件内容（收窄语义与 `materialize._allowed_skills_for` 一致）。
- `node-supervisor`：①新增 requirement——materialize 时同步 skill 文件到 `<home>/skills` 并在 skill 增删改时重启、清理移除的 skill；②新增 requirement——权威态删除已移除 agent 的本地 home 目录、cache 态不误停不误删；③MODIFY 既有「幂等 reconcile（期望↔实际）」：disappear 分支的 stop 受 remote 源门控并联动删除清理。

## Impact

- **owning package**：`node/`（`reconcile.py`、`provider.py`）+ `platform/`（`node_management/node_desired_state_api.py`、`agent_lifecycle/materialize.py` 新增 skill-bundle 下发助手）。
- **public API surface**：
  - `materialize.skill_bundles_for_agent(agent) -> list[dict]`（平台侧，供 desired-state 端点调用）。
  - `node.provider.DesiredAgent` 新增 `skills: list[DesiredSkill]` 字段；新增 `DesiredSkill`/`DesiredSkillFile` dataclass。
- **owned tables**：无（skill 元数据/绑定沿用既有 `skills`/`agent_skills` 管理表，本 change 只读）。
- **config namespace**：无。
- **cross-module dependencies**：node SHALL NOT import `fleetent.platform.*`（不变，node→platform 仅 HTTP）。platform 端 `node_desired_state_api` → `materialize`（既有方向）；`materialize` 复用 `skills.registry._resolve_skills_dir`（既有用法，materialize.py:620 已有）。**不改 agent 运行时与 `agent_config.py`**。
- **migration / shim plan**：无 schema/迁移。行为纯增量；旧 node（不识别 `skills` 字段）兼容（字段缺省 `[]`）；存量 managed agent 上线后下一轮 reconcile 自动补 skill 文件（一次性按需重启）。
- **范围外**：不改 agent 侧 skill 加载/`FLEETENT_SKILLS_DIR` 解析；不做 skill 内容的 If-None-Match/条件下发（每轮全量传 skill 文件的带宽优化列为后续）；不动 skill drift/backflow 链路。
