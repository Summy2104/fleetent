## Context

托管链路：platform `GET /nodes/{id}/desired-state`（`node_desired_state_api.py:85`）按 placement+status 组装每 agent 的 `{agent_id, name, config, secrets}`；node `provider.py` 拉取并解析成 `DesiredState`，`reconcile.py` 调谐成本地进程：`_write_home`（写 `agent.yaml`+`.env` 到 `<home>/agents/<name>/`）→ `backend.spawn`（`fleetent agent run <name> --home <home>`）。

skill 在平台是**目录树**（`<pool>/<name>/SKILL.md` + 兄弟文件，pool 由 `skill_registry._resolve_skills_dir(None)` 解析）；元数据/绑定在管理库 `skills`（全局 `global_enabled`）与 `agent_skills`（per-agent `enabled` 矩阵 + `base_version`）。单机 `materialize._copy_skills` 把**整个 pool** 拷进 `<home>/skills`，靠运行时 `allowed_skills` 收窄可见性。

**关键事实（修正任务前提）**：agent 进程（`runtime/agent_app.py:472-478`）固定 `skills_root = home_dir/"skills"; scan_skills(skills_dir=str(skills_root))`，注释明示「self-contained: never the process CWD or `FLEETENT_SKILLS_DIR`」。sandbox（`cfg.source`，由 agent_app seed 成 home/skills）、reflection（`_last_skills_dir`=home/skills）同样不读 `FLEETENT_SKILLS_DIR`。`scan()` 始终额外从包内 `BUILTIN_SKILLS_DIR` 读 builtin。**结论**：让托管 agent 加载平台 skill 的唯一有效且不改 agent 代码的途径 = 把文件写进 `<home>/agents/<name>/skills/`；注入 `FLEETENT_SKILLS_DIR` 是 no-op。

约束：node SHALL NOT `import fleetent.platform.*`；不改 agent 运行时与 `agent_config.py`。

## Goals / Non-Goals

**Goals:**
- 托管 agent 启动即拥有其绑定/allowed skill 的文件，`read_skill` 可用，行为与单机 materialize 对齐（按绑定收窄）。
- skill 增删改触发 agent 优雅重启；移除的 skill 文件清理干净。
- 「已移除 agent」的本地 home 目录被删除、ledger 收缩；platform 不可达（cache 回落）时不误停/误删。

**Non-Goals:**
- 不改 agent 侧 skill 加载、不注入/不依赖 `FLEETENT_SKILLS_DIR`。
- 不动 builtin skill（agent 从包内 scan）、不动 skill drift/backflow。
- 不做 skill 文件的条件/增量下发（带宽优化），本 change 每轮全量传绑定 skill 文件。
- 不改 `_config_hash` 既有 config-hash 语义（skill 变更走独立 manifest 比对，避免污染既有 hash 测试）。

## Decisions

### 决策 1：平台侧新增 `materialize.skill_bundles_for_agent(agent)`，desired-state 每 agent 加 `skills` 键

在 `materialize.py`（已 import `skill_registry` 并用其内部 `_resolve_skills_dir`）新增 public 助手，复用既有收窄助手 `_allowed_skills_for` / `_global_disabled_skills` / `skill_admin_store.has_any_binding`：

- pool = `Path(skill_registry._resolve_skills_dir(None))`；不存在 → `[]`。
- 选 skill 名集合（与运行时 `allowed_skills` 语义一致）：
  - `allowed = _allowed_skills_for(agent)`；`has_binding = skill_admin_store.has_any_binding(agent.id)`（缺表降级 False）。
  - `allowed` 非空 → `names = set(allowed)`；否则若 `has_binding` → `names = set()`（显式收窄为零）；否则 → `names = {pool 下所有 skill 目录名}`（未收窄=全 pool）。
  - `names -= set(_global_disabled_skills())`。
- 对每个 `name`（排序）且 `pool/<name>/SKILL.md` 存在：files = `rglob` 全部文件（排除 `.git`），每项 `{"path": <posix 相对路径>, "content_b64": b64encode(read_bytes)}`；`version = _skill_dir_version(skill_dir)`（既有内容 hash）。
- `node_desired_state_api.get_desired_state` 每 agent 条目加 `"skills": materialize.skill_bundles_for_agent(agent)`。

**Why**：助手放 materialize 保持「读 `skills.registry` 内部」集中在既有单点（不让 API handler 直接碰 registry 内部，过 `check_module_boundaries`）；base64 二进制安全（skill 可含脚本/图片）；按绑定收窄＝数据最小化且与下发 `agent.yaml` 的 `allowed_skills` 自洽。

### 决策 2：node 把 skill 文件写进 `<home>/agents/<name>/skills/`，不注入 `FLEETENT_SKILLS_DIR`

`provider.py`：`DesiredAgent` 加 `skills: list[DesiredSkill] = field(default_factory=list)`（新增 `DesiredSkill(name, version, files)` / `DesiredSkillFile(path, content_b64)`）；`_desired_state_from_payload` 解析 `agent.get("skills", [])`；cache 写入**保留** skills（非 secret，`_strip_secrets_for_cache` 只剔 `secrets`）；`_overlay_last_live_secrets` 重建时透传 `skills`。

`reconcile.py` 新增 `_materialize_skills(agent_name, skills)`：写到 `<home>/agents/<name>/skills/`，逐 skill `rmtree`+重写（确保 skill 内删文件也生效），base64 解码 `write_bytes`；写 manifest `<home>/agents/<name>/.node-skills.json = {name: version}`。`_write_home` 改为接收 `DesiredAgent`，在 `agent.yaml`+`.env` 之后调 `_materialize_skills`。

**backend.spawn 的 env 不变**（仍只 `{**os.environ, **secrets}`）：注入 `FLEETENT_SKILLS_DIR` 对 agent 无效（见 Context），写盘到 `<home>/skills` 即生效。

### 决策 3：skill 变更经 manifest 比对触发重启；config-hash 不变

restart 判定 = `current_hash != desired_config_hash`（既有，`_config_hash` 不动）**OR** `_skills_changed(name, desired.skills)`（desired `{name:version}` ≠ 磁盘 manifest）。冷拉起路径无条件 `_write_home`（含写 skill）。

**Why not 合并进 config-hash**：既有两条 hash 测试断言 ledger 值=`sha256(config yaml)`，合并会破坏它们；独立 manifest 比对零侵入既有语义，且 manifest 同时承载「node 管了哪些 skill」供清理。存量在跑 agent 首次见到非空 skills 而 manifest 缺失 → 判为变更 → 一次性重启补齐（可接受）。

### 决策 4：清理只删 node 自管 skill；删除整 home 仅在权威态

- skill 清理：`_materialize_skills` 先读旧 manifest，`prev_names - desired_names` 的目录 `rmtree`；只动 manifest 记录过的名字 → builtin（agent 从包内 scan，且 sandbox 路径 materialize 进来的 builtin 副本不在 manifest）与 operator 自留 skill 不受影响。同名平台 skill 删除后，builtin 经包内 scan 自动回退、不丢。
- 整 home 删除（disappear 分支）：仅当 `desired_state.source == "remote"`；先 `stop`（try/except 舱壁化、失败只 `_logger.warn`、不中断 loop）再 `shutil.rmtree(<home>/agents/<name>)`，并 `hashes.pop(name)`。`source != "remote"`（cache 回落）→ 整个 disappear 分支跳过（既不 stop 也不删），修复既有 spec「缓存缺失时不误停」缺口。

## Risks / Trade-offs

- **[每轮全量下发 skill 文件]** → desired-state 响应/缓存随 skill 体量增大；本 change 接受（内网 loopback/LAN、正确性优先），node 经 manifest 版本比对只在变更时重 materialize+重启，带宽优化（条件下发）列后续。
- **[skill 文件写 cache 落盘]** → cache 持久化 skill 内容（非 secret，与既有持久化 config 一致）；体积增大可接受。
- **[node 与 agent 对 `<home>/skills` 的读写]** → node 在 `spawn` **之前**于 `_write_home` 内写 skill；agent boot 时已就位；同一 home 仅 node reconcile 串行写。agent 运行中 sandbox 可能往 home/skills materialize builtin 副本（`dest.exists()` 跳过、不 clobber node 写的同名平台 skill），node 清理只按 manifest，互不误伤。
- **[存量 agent 一次性重启]** → 上线后首轮对有绑定 skill 的在跑 agent（manifest 缺失）触发一次重启补 skill；属预期、文档化。
- **[stop 失败]** → disappear 分支 stop 舱壁化，失败记日志后仍删 home（进程已死是常态）；不影响 `_post_status` 与其它 agent。
- **[manifest 损坏]** → `.node-skills.json` 被截断/写坏（如上次写盘时进程被 kill）时，`_read_skill_manifest` 舱壁化降级为 `{}`（记日志），视作「manifest 缺失」→ 下一轮 materialize 重写补齐，绝不让单 agent 的损坏 manifest 冒泡中断整个 reconcile 循环与状态上报。
- **[skill 名/文件路径穿越]** → skill 文件从下发载荷 base64 解码后落盘，node 作为落盘执行方对路径做一次边界自检：skill 名必须是单路径分量（拒含 `/`、`\`、`.`、`..`），skill 内文件 dest 必须是 skill 目录的严格子孙；越界者跳过并记日志。change 检测与 materialize 用同一过滤（`_valid_skills`）保证收敛、不重启抖动。平台侧 `_read_skill_files` 本就只产出干净相对路径，此为纵深防御。

## Migration Plan

- 纯增量、无 schema/迁移。
- 旧 node 客户端忽略未知 `skills` 字段（向后兼容）；新 node 对旧 platform（无 `skills` 键）按缺省 `[]` 处理（向前兼容）。
- 回滚：移除 `skills` 下发与 `_materialize_skills`/删除清理调用即可；已落盘的 `<home>/skills` 与 `.node-skills.json` 残留无害（agent 仍能 scan）。

## Open Questions

- 无阻塞项。带宽优化（skill 内容按 version 条件下发，避免每轮全量传）确认为后续独立 change。
