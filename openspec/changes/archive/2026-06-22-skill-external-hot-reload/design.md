## Context

`skills/registry.py` 已有:模块级 `_index`(name→SkillEntry)、`scan(skills_dir)`(破坏性 clear+update,boot/CLI 用)、`reload(skills_dir)`(build-then-atomic-swap,失败保留旧索引)、`_last_skills_dir`(最近一次扫描的根)。catalog 经 `available_skills_prompt()` 读 `_index` 渲染,**每条入站消息组装一次 system prompt 时注入**(IM `normalizer` / HTTP `run_stream` / CLI `run_sync`),其后该 run 的多轮 LLM 调用复用同一 prompt。

运行期 reload 的现有触发面:admin API `POST /admin/skills/reload` + admin 上传/编辑 + `skill_manage` 写。**缺口**:外部直接改 skills 文件,运行中的 agent(IM 长驻进程)不感知。

约束:agent 运行时模块 MUST NOT import platform;长生命周期异步资源须遵守 owner-task 契约(本设计**刻意不引入任何后台/长驻任务**以完全规避该雷区);TDD Hard Gate。

调研结论(4 项目):claude-code/openclaw 用 FS watcher(后台任务 + 第三方库/原生 API);hermes 用「每次构建 prompt 按 mtime+size manifest 比对,变了才重扫」(无 watcher、无后台任务、零依赖);opencode 无热加载。fleetent 的 catalog 本就每条消息注入,天然适配 hermes 式按需比对。

## Goals / Non-Goals

**Goals:**
- 外部(手改/`git pull`/内网 sync)改 skills 后,运行中的 agent **无需重启**,下一条入站消息即反映新集合(新增可匹配、删除不再匹配、编辑生效)。
- 零新依赖、零后台任务、不触碰异步生命周期契约。
- 常态开销可忽略(只 stat,不读不解析);复用既有原子 `reload()` 的所有保证。
- per-agent 配置可关。

**Non-Goals:**
- 不做文件系统 watcher / 后台轮询任务(事件驱动/idle 刷新非目标;freshness 只在服务消息时才需要)。
- 不改 CLI 一次性路径(已每次全量 scan)。
- 不改 `reload()` 的原子/失败/in-flight 语义(直接复用)。
- 不在每次 LLM 调用做(仅每条入站消息一次)。

## Decisions

### D1:按需 manifest 比对(hermes 式),挂在 catalog 注入前
新增 `registry.refresh_if_changed(skills_dir=None) -> bool`:
1. `root = skills_dir or _last_skills_dir`;None(从未 scan)→ 返回 False(无可比对基线)。
2. walk `root`,对每个 `SKILL.md` 做 `os.stat`,拼当前 manifest `{relpath: (st_mtime_ns, st_size)}`。
3. 与模块级 `_manifest` 比对(普通 dict 比较):相等 → 返回 False;不等 → 调 `reload(root)`(原子重建)、返回 True。
- **不读文件内容、不解析 YAML**——这是与 `reload`/`scan` 的关键开销差。
- 挂载点:`normalizer`(IM)与 `run_stream`(HTTP)在 `available_skills_prompt(...)` 之前调一次。`_index` 刷新后,本条消息的 catalog 与本轮 `read_skill`/`list_skills`/`skill_manage` 都看到最新集合。
- 备选:后台轮询 owner-task / FS watcher —— 否决:引入长驻任务(撞 owner-task 契约)或第三方依赖,而 idle 刷新无实际价值。

### D2:`_manifest` 由 scan/reload 维护,保持与 `_index` 同源
新增模块级 `_manifest: dict[str, tuple[int,int]]`。`scan()` 与 `reload()` 成功重建 `_index` 后,**用同一次遍历或紧接一次轻量遍历**填充 `_manifest`(覆盖 user 根下 SKILL.md)。这样 `refresh_if_changed` 的「旧基线」永远对应当前已索引状态,首条消息不会误判为变化。
- 监听范围 = **user skills 根**(运行期变化只发生在此;package `BUILTIN_SKILLS_DIR` 不在运行期变)。`reload`/`_build_index` 内部仍重扫 builtin+user 两源 —— manifest 只用于「要不要触发 reload」,不改变 reload 的扫描范围。
- 备选:manifest 覆盖 builtin+user 两源 —— 否决:builtin 是包内只读资源,运行期不变,纳入只增成本无收益。

### D3:并发用模块级小锁
多用户并发消息会并发调 `refresh_if_changed`。用一个模块级锁(如 `threading.Lock`)包住「比对+(必要时)reload+写 `_manifest`」临界区。`reload()` 本身已原子;锁只为避免重复 walk/reload 与 `_manifest` 撕裂。
- agent 运行时是 asyncio 单事件循环,`refresh_if_changed` 是同步 ~毫秒级调用,内联执行(不进线程池)——简单且开销可忽略。
- 备选:无锁、接受良性重复 reload —— 可行但 `_manifest` 读改写可能交错致重复触发;小锁更确定,成本极低。

### D4:per-agent 开关 `skill_hot_reload`,默认开
`AgentFile.skill_hot_reload: bool = True`。挂载点在调 `refresh_if_changed` 前检查该 agent 的开关;关则跳过(退回 boot 扫一次 + `skill_manage` 写时 reload)。与既有 `skill_authoring_enabled` 同风格,经各入口的 agent 配置读取。
- 默认开:这是想要的默认行为,实测开销可忽略。
- 备选:常开不可配 —— 否决:超大 skill 库/极致性能场景需要不改代码的退出口。

## Risks / Trade-offs

- **每条消息增 ~毫秒级 stat 开销**(实测 41 skill ≈ 5ms,变更态 reload ≈ 74ms 一次性) → 相对 LLM TTFT 可忽略;`skill_hot_reload=false` 可关;规模到上千再优化(缓存 walk/只 stat 已知列表)。
- **mtime+size 理论盲点**(同纳秒改且大小不变) → 可忽略(hermes 同口径);size 多一维降低碰撞。
- **同步 stat 阻塞事件循环 ~5ms** → 可接受(loop 本就有同步工作);不引线程池保持简单。
- **首条消息误判** → 由 D2(scan/reload 同步维护 `_manifest`)消除:基线即当前已索引状态。
- **并发撕裂 `_manifest`** → D3 小锁消除。
- **复用 reload 的既有保证**(原子切换/失败保留旧/in-flight 用旧版) → 不重新发明,降低风险。

## Migration Plan

- 纯增量:新函数 + 一个默认 `true` 的 agent 配置字段 + 两处调用接线。无 DB、无 platform、无迁移脚本。
- 部署后默认即生效;关掉 `skill_hot_reload` 退回旧行为。回滚 = 移除接线调用与字段。

## Open Questions

无(挂载点、manifest 结构与范围、并发处理、配置默认值均在 brainstorm 阶段敲定)。
