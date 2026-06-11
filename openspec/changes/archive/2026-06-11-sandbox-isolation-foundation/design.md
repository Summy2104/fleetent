## Context

本 change 是"沙箱优先执行"序列的前置地基,只做三件让"沙箱隔离 → 免审批"安全前提成立的事,**不**启用任何免审批(见 proposal)。三处现状(均已核实):

- `integrations/sandbox/manager.py:58-60` 的 `_sanitise(raw)` = `_SAFE_NAME.sub("-", raw)[:48]`,被 `_container_name`(:63)与 `workspace_host_path`(:221)共用。
- `runtime/loop.py:748` `sandbox_capable=is_sandbox_backed(name)` 为静态工具名查表;同文件 `:2087` 已有 `sandbox_enablement.get_effective_mode()` 但未喂进 gate。
- 既有 `action-gate`(已归档合并)的 `resolve_action_mode` 已有"mode=SANDBOX 但 sandbox_capable=False → 升 APPROVAL"的 fail-closed——本 change 复用它,只改喂进去的 `sandbox_capable` 真值,**不改 gate 契约**。
- workspace 根 `paths.workspaces_dir() = data_dir()/workspaces`,`data_dir()` 在 standalone 已重定向到 agent home(`agent-data-isolation` 既有契约),故 workspace 已落 `agents/<id>/data/workspaces/`——本 change 不动 rooting。

## Goals / Non-Goals

**Goals:**
- 容器名与 workspace 宿主目录的 key 派生对超截断边界的同前缀 key 无碰撞,结构性满足 `sandbox-lifecycle` / `sandbox-workspace-mount` 既有隔离要求与 `agent-data-isolation`。
- 喂给 action gate 的 `sandbox_capable` 反映运行时封闭性;无 docker / 无容器封闭时 fail-closed 升审批("无 docker = 不免审批")。
- workspace 宿主目录按 scope 回收:session 随会话过期整目录回收、agent 按 mtime 目录内清理。

**Non-Goals:**
- 不翻任何工具默认免审批、不改 registry risk 常量、不加 agent.yaml 配置字段(归后续"放松管制"PR)。
- 不拆 scope(workspace_scope 与镜像持久化解耦是后续独立高风险重构)。
- 不动 workspace rooting / 不做 uploads·generated 迁入 / 不加 sandbox_exec(归"执行世界"PR)。
- 不修 `_HostBackend` 围栏的 symlink/TOCTOU 缝本身(本 change 只确保降级态不免审批,不重写围栏)。

## Decisions

### D1:无碰撞 key 派生 —— 可读前缀 + 完整 key 哈希后缀
新增单一 key 派生函数(替换/收口 `_sanitise` 的用途),形如 `<sanitised 可读前缀(截断)>-<sha256(完整未截断 key)[:N]>`,总长压在 docker 容器名 63 字符上限与文件系统目录名上限之内。`_container_name` 与 `workspace_host_path` **共用同一函数**,一处修复同覆盖两者。
- 备选:仅放大截断上限 → 否决,只把碰撞边界外推、不根除。
- 备选:用完整 key 不哈希 → 否决,超 docker/文件系统长度限制。
- 参照:openclaw 用 slug32+hash8 截 63,同构。

### D2:运行时封闭性派生 `sandbox_capable`
在 gate 调用点(`_plan_run_slots`)把 `sandbox_capable` 从 `is_sandbox_backed(name)` 改为运行时派生:`is_sandbox_backed(name) AND effective_mode != OFF AND 该工具本次确在容器内执行(后端提供容器执行 / workspace_mount)`。`effective_mode` 经既有 `get_effective_mode()` 每 run 取一次并缓存传入,避免热路径重复 await。
- file tools 的"本次是否容器内执行"取自与 `_select_backend` 同源的判定(container vs `_HostBackend`),保证 `write_file`/`edit_file` 在降级态 `sandbox_capable=False`。
- 备选:改 `resolve_action_mode` 签名 → 否决,gate 契约本就正确(fail-closed 已在),错的是输入真值。
- 收口为一个 helper(如 `runtime_sandbox_capable(tool_name, effective_mode, backend_caps)`),供 loop 调用,便于 unit 测试。

### D3:workspace GC 按 scope 分策略,经 sandbox public API 触发
- session scope:在既有会话 TTL 过期点(`session-ttl-cleanup`)调用 sandbox 暴露的 workspace-GC 入口,先经既有释放路径销毁活跃容器、再整目录 `rmtree` 该会话子目录。
- agent scope:在既有 idle sweep 内按 mtime 目录内清理超保留期内容,不整删。
- 删除前 `is_blocked_mount` 同源校验 + realpath 落在 `workspaces` 根内双重护栏。
- 备选:绑 `release_session`(会话释放即删)→ 否决,会话可能 resume,释放只销容器非终结;TTL 过期才是真正生命终点。
- 模块边界:GC 逻辑落 `integrations/sandbox`(maintenance 路径),会话过期点经 **sandbox public API** 调用,`session/` 不 import sandbox internal;两者均 agent 运行时,无 platform 依赖。

## Risks / Trade-offs

- **key 派生变更使存量容器名/ workspace 目录成孤儿** → 旧容器由既有 `sandbox-orphan-cleanup` 回收;旧 workspace 目录为临时数据、低危,由新 GC 或一次性运维清理兜底;变更前后无需数据迁移。
- **`effective_mode` 引入热路径 await** → 每 run 取一次并缓存,不在每次 gate 解析重复获取。
- **session 整目录 rmtree 与 resume 竞态** → 仅在 TTL 过期(会话已终结)触发,先销容器再删,叠加 `is_blocked_mount` + realpath 双护栏。
- **agent scope mtime 清理误删在用依赖** → 保留期取保守默认(不短于 idle TTL);该粒度数据隔离问题由后续拆 scope change 根除,本 change 仅做有界回收止血。
- **per-tool 容器内执行判定不彻底**(只看 mode、漏 `workspace_mount=False` 的后端)→ 判定 MUST 取自后端能力而非仅 mode,unit 覆盖 microsandbox/无 mount 分支。

## Migration Plan

- 无 DB 迁移(workspace 为文件系统)。
- 部署后:存量旧名容器/目录孤儿化,无需手动迁移;可选一次性清理旧 `workspaces` 子目录。
- Rollback:回滚代码即可,新派生产生的目录孤儿化、低危无害;gate 行为回退到改前(降级态仍按旧静态判定——故回滚须连带回退依赖本 change 的后续免审批配置,避免裸露降级态免审批)。

## Open Questions

- 哈希后缀长度 N 与可读前缀预算的具体取值(docker 63 vs 文件系统 255 下的分配)——实现期定,以 unit 锁定无碰撞。
- agent scope workspace 保留期默认值——倾向对齐或长于 idle TTL,实现期定。
- 后端在工具调用点暴露"本次是否容器内执行 / workspace_mount"能力的接口形态——确认现有 backend capabilities 是否已足够,不足则补最小只读查询。
