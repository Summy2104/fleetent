## Context

`scan()`（skill_registry.py 行 38）：解析 `skills_dir`（默认环境变量 `FLEETENT_SKILLS_DIR`，见 skill_registry.py:48，或 `skills`）→ `_index.clear()`（行 49，**就地清空**）→ 对 **builtin（`BUILTIN_SKILLS_DIR`）+ 用户 `skills/` 两个源** 各 `rglob("SKILL.md")` 逐个解析填充模块级 `_index`。它在 FastAPI lifespan 启动时跑一次（`server.py` 行 68），CLI 路径 `run_sync()` 每次跑（`agent_loop.py` 行 408 的 `scan_skills()`；`run()` 行 234 不扫描、不注入 Skill）。HTTP 服务进程长驻，启动后 `_index` 不再更新——除非重启。

**统一 apply / 归档序**（Track G 全局决策）：本轨顺序 SK4（本 change）→ SK5 → SK1 → SK3 → SK6，SK4 最先实施。本 change 抽出的统一构建逻辑 `_build_index` 是后续 SK5（审计闸门接在构建逻辑内）的承载点；本 capability 为纯 ADDED。

CLAUDE.md gotcha 明确：`skill_registry.scan()` 在服务启动时运行（FastAPI lifespan），不是每次请求；CLI `run()` 每次调用。本 change 是「在运行期增加重扫能力」，不是改启动时机。

`scan()` 当前的 `_index.clear()` 是**就地清空**：clear 与重新填充之间存在「索引半空」窗口，且若填充中途抛错则旧数据已丢。这正是运行期重扫不能直接复用 `scan()` 的原因。

session_mgr 的原子写（`.json.tmp → rename`）确立了项目「构建完成再整体替换」的原子切换范式，本 change 在索引维度复用同一思路。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态（索引路径/目录可注入，模块级 `_index` 引用可被原子替换）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 skills 目录隔离 tmp_path，外部 HTTP/认证 mock。

## Goals / Non-Goals

**Goals:**
- 运行期可经 admin CLI / 管理 API 触发重扫，无需重启服务。
- 重扫先构建到新索引对象、全部成功后原子整体替换模块级索引引用，杜绝半空窗口。
- 重扫失败保留旧索引不变并记录结构化 warning，服务不降级。
- in-flight 任务继续使用其取用时的 Skill 内容，不被重扫中途篡改。

**Non-Goals:**
- 不改 `scan()` 在启动 / CLI 的触发时机。
- 不实现文件系统监听（inotify/watchdog）自动触发——只做显式触发（CLI/API）。
- 不做增量 diff 重扫（只做全量重扫后整体替换）。
- 不保证「正在 load() 读盘的某 SKILL.md 被删」的文件级原子性（见 Risks）。
- 不实现安全审计、禁用过滤、渐进式加载、多 Skill 共存（各自 change）。

## Decisions

### D1：抽出纯构建逻辑 `_build_index(skills_dir) -> dict[str, SkillEntry]`
把 `scan()` 中「遍历目录 + 解析 frontmatter + 组装 `SkillEntry`」的逻辑抽成一个**不触碰全局 `_index`** 的纯构建函数，返回一个全新的 `dict[str, SkillEntry]`。`scan()`（启动/CLI）与 `reload()`（运行期）都调用它，区别仅在如何把结果落到全局索引。
**须覆盖两个源**：`scan()` 现扫 **builtin（`BUILTIN_SKILLS_DIR`）+ 用户 `skills/` 两个源**（行 50-51 各调一次 `_scan_dir`），`_build_index(skills_dir)` 必须保持同一覆盖面——内部对 builtin 与用户目录各扫一遍、合并进同一个新 dict（同名冲突沿用现有 SK8 path-sort 策略），不能只认 `skills_dir` 一个源。语义：`_build_index(d)` 返回的 dict 等价于「`scan(d)` 后的 `_index` 内容」，只是落在新 dict 而非全局。
**为何**：构建与「发布到全局」解耦后，重扫可以先安全地构建好新索引，再决定是否替换；消除 `clear()+填充` 的就地耦合，是原子切换与失败保留的前提。
**Alternatives**：直接在 `scan()` 里加 `reload` 标志走不同分支——被否，就地 `clear()` 仍在路径上、难以同时满足「无半空窗口」「失败保留旧索引」。

### D2：`reload()` 构建到新索引 + 原子整体替换
`reload(skills_dir=None)`：调用 `_build_index()` 得到 `new_index`；**仅当构建成功**（未抛出、目录存在）后，把模块级索引引用整体指向 `new_index`（单次赋值，原子）。读取方（`match`/`match_all`/`load`/`l1_summary`/`list_skills`）通过同一模块级引用访问。
**为何**：Python 模块级名称的整体重绑定是原子的——任一读取要么看到旧索引、要么看到新索引，绝不会看到半空中间态。这满足「重扫期间继续用旧索引、完成后原子切换」。
**Alternatives**：加锁保护 `_index` 的逐项更新——被否，引入并发复杂度且仍有半空窗口；原子整体替换更简单且天然无窗口。
**注**：读取方需通过「访问模块级当前索引引用」而非在函数定义时捕获旧引用，确保替换后读到新索引；实现首步核实各读取函数对 `_index` 的引用方式（见 Open Questions）。
**实现注记（原子替换安全性）**：已核实当前无任何模块 `from skill_registry import _index`（各调用方都 import `match`/`load`/`scan` 等函数，经函数间接访问模块级 `_index`），因此整体重绑定模块级名称对所有读取方即时可见、不存在外部持有旧引用的别名——原子整体替换安全。据此，`reload()` 的替换 MUST 用 `global _index; _index = new_index`（**重绑定模块全局名**），而非 `_index.clear()+update()` 之类的就地 mutation——后者会重新引入半空窗口、丧失失败保留旧索引的能力。

### D3：重扫失败保留旧索引 + 结构化告警
`reload()` 在 `_build_index()` 抛错或目录不可用时：**不替换**模块级索引（旧索引原样保留），记录一条结构化 warning（含 skills_dir 与失败原因），返回失败结果摘要。服务继续用旧 Skill，不降级为空。
**为何**：直接落实 skill.md「扫描失败时保留旧索引并告警，不影响服务」；与 SK2「一个坏 Skill 不应拖垮扫描」的健壮性取向一致。
**Alternatives**：失败时清空索引——被否，正是要避免的服务降级；静默失败——被否，违背可观察性。

### D4：in-flight 任务用旧版 Skill —— 依赖「请求早期一次性取用 + 原子替换」
Skill 注入发生在请求处理早期（`run_sync()` 行 408-415 的 `scan→match→load`、`run_stream()` 行 451-453 的 `match→load`，构造 messages 时一次性取用并拼入 system prompt；`run()` 不涉及），之后该请求不再回读索引。配合 D2 的原子整体替换：一个请求要么在替换前完成取用（用旧 Skill），要么在替换后取用（用新 Skill），不会取到半个。已注入的 system prompt 是该请求的私有副本，重扫不影响。
**为何**：满足 skill.md「正在执行中的任务继续使用旧版 Skill，不受影响」；无需为 in-flight 任务额外加版本快照机制——一次性取用 + 原子替换已足够。
**Alternatives**：给每个请求绑定索引版本快照——被否，过度设计，注入早期一次性取用已天然隔离。

### D5：触发通道 = admin CLI 子命令 +（可选）管理 API
新增 `reload-skills` admin 子命令（沿用 `admin.py` 的 `add_parser` 模式）触发 `reload()` 并打印结果摘要；可选在 `server.py` 加一个 Bearer 认证的管理端点触发同一 `reload()`。
**为何**：skill.md 明确「经 admin CLI 或管理 API 触发」；复用既有 CLI/认证骨架，blast radius 小。
**Open**：API 端点是否本 change 必做、还是 CLI 优先 API 后续——见 Open Questions。

## Risks / Trade-offs

- [`load()` 读盘时该 SKILL.md 被删/改] → `load()` 按 `path` 现读文件，重扫替换的是索引引用而非文件；极端竞态（in-flight 请求 load 时文件已被删）属文件级而非索引级问题，本 change 不保证文件原子性，沿用现有 `load` 行为（读失败按既有异常处理，不吞）。
- [读取函数若在定义时捕获了旧 `_index` 引用，原子替换不生效] → 实现首步核实并确保所有读取经「当前模块级索引」访问；加测试断言 `reload` 后 `match`/`list_skills` 反映新内容。已核实无任何模块 `from skill_registry import _index`（全 import `match`/`load`/`scan` 函数）→ 不存在外部持有旧索引别名，重绑定模块全局名（`global _index; _index = new`）对所有读取方即时可见，原子整体替换安全。
- [全量重扫成本] → Skill 数量小、重扫是低频管理操作，全量重扫可接受；不引入增量 diff 的复杂度。
- [并发重扫] → 两次 `reload()` 并发各自构建新索引、各自原子替换，最后赢者生效，无半空；如需串行化可后续加锁，本次接受「最后写赢」语义。

## Open Questions

- 读取函数当前对 `_index` 的引用方式（模块级名 vs 捕获）——实现首步核实，必要时统一为经 getter / 模块属性访问以保证原子替换可见。
- 管理 API 端点是否纳入本 change（还是 CLI 先行、API 作后续）——结合 server 认证与运维触发偏好在 propose review 时定。
- 并发 `reload()` 是否需串行化（加锁）——本次取「最后写赢」，若运维场景需要可后续补。
