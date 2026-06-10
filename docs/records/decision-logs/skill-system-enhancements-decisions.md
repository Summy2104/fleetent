# Skill 系统增强 — 执行决策日志

> 自动执行批次（2026-06-06）。承接 5 个核心 gap change（R1/R2/M1/M2/M4/M3/R3，已全部合并）之后的 P1/P2 增强项。
> 本文档记录全盘规划、范围甄别、以及执行中遇到的问题与决策点，供完成后审核。

## 范围甄别

来源：skill 系统 gap 分析报告（对照 hermes-agent / claude-code / openclaw / opencode）。
甄别原则：① 明确价值 + 低风险 → 做；② 高风险 / 违反项目原则 → 不做（记理由）；③ 大特性 / 需新依赖讨论 → 暂缓（记理由）。

### 决定执行（本批次）

| 编号 | 项 | change 名 | 理由 |
|------|----|-----------|------|
| P1-A | read_skill 拒绝写审计日志 | `skill-read-refusal-audit` | 完成 skill-injection-audit spec 的审计要求；安全可追溯；改动小 |
| P1-D | builtin vs user 层级优先 | `skill-tier-precedence` | 让 operator 可预测地覆盖 builtin skill，当前纯路径字典序是实现意外 |
| P1-C | catalog 字数预算 + compact fallback | `skill-catalog-budget` | 防 skill 库增长后 system prompt 静默膨胀、吃 prompt cache 预算 |
| P2-6/P2-3/P2-2 | frontmatter 扩展 | `skill-frontmatter-extensions` | disable_model_invocation + requires_tools + required_env_vars 都是 frontmatter→可见性，内聚成一个 change |
| P1-B | observability 落 SQLite | `skill-observability-tracking` | admin console observability 当前永久 stale，侵蚀运维信任 |
| P1-F | askit_override 接线 | `skill-askit-override-wiring` | 完成 proposal→approve→managed-skill-update 闭环 —— **先调查 askit 接口是否存在** |

### 暂缓（记理由，不在本批次）

| 编号 | 项 | 暂缓理由 |
|------|----|---------|
| P2-5 | FS watcher 自动热重载 | 引入新依赖（watchdog）+ 后台线程。CLAUDE.md 规定新依赖必须经讨论；且已有 `POST /admin/skills/reload` 覆盖核心需求。留待依赖讨论后单独立项。 |
| P2-7 | 远程 skill URL registry | 大特性：涉及内网 HTTP 端点、签名验证、本地缓存、`.well-known` 协议。需单独设计 + 可能的依赖讨论。非闭环必需。 |
| P2-10 | version 字段漂移检测 | 价值低：`skill_provenance.drift` 已通过内容编辑标记漂移；版本号语义漂移是锦上添花。 |

### 不做（记理由）

| 编号 | 项 | 不做理由 |
|------|----|---------|
| P2-1 | SKILL.md 内联 shell 执行（`!`cmd``） | **安全立场冲突**：在 skill 内容里执行 shell 扩大攻击面，与 skill-injection-audit 的防注入立场直接矛盾。on-prem 数据主权平台尤其敏感。受控代码执行已由 sandbox（run_code 工具）提供，无需在 skill 加载期引入未沙箱化的 shell 扩展。 |

## 执行顺序

串行执行（多个 change 都改 `registry.py`，串行避免合并冲突）：
A → B → C → D → E → F

每个 change 走完整 OpenSpec 流程（propose→apply→archive）+ TDD 红绿 + bb-pr main + 等 CI 合并，再开下一个。

## 执行记录

（按完成顺序追加）

### Change A — `skill-read-refusal-audit`（P1-A）✅
- 实现：`read_skill` opt-in `tool_context`；audit_blocked 拒绝分支调 `audit_log.write_audit(None, "skill.read_refused", "skill", name, detail=...)`，try/except 包裹。
- 决策点：
  - **审计落 audit_log（user_store DB）而非独立表**：standalone agent 也用 user_store（bearer 认证），DB 可达；audit_log 是通用 append-only 日志，按 action 区分语义足够。
  - **审计写入失败不阻断拒绝**：拒绝是安全核心，审计是旁路；write_audit 异常被捕获记 warning，仍返回拒绝文本。
  - **不审计"未知 skill 名"分支**：那是 LLM 笔误而非安全事件。
  - 验证 `tool_context` 不进 LLM schema（out-of-band 注入）。
- 测试：4 unit（拒绝写日志 / 含上下文 / 正常不写 / 写入失败不阻断）；全套 3580 passed。

### Change B — `skill-tier-precedence`（P1-D）✅
- 实现：`_scan_dir` 冲突分支按层级优先 `keep_existing = builtin if tier_override else existing.path <= path`；告警加 `tier_override` 字段。复用 `SkillEntry.builtin`，无新字段。
- 决策点：
  - **复用 `builtin` 标志而非新增 `tier` 字段**：当前只有 builtin/user 两层，`builtin` bool 足够；避免 schema 膨胀。
  - **判定 `keep_existing = builtin`（tiers 不同时）**：对两种到达顺序都正确，与 SK8 的"顺序无关"测试一致。
  - **更新预存测试 `test_scan_no_source_priority_override_logic`**：该测试编码了被本 change 显式反转的旧"无来源优先"规则。按 MODIFIED requirement 重写为 `test_scan_user_overrides_builtin_regardless_of_path_sort`（断言 user 胜）。这是 spec 演进的必要同步，非破坏。
  - 同层级（两 user）行为完全不变。
- 测试：3 新 unit + 1 重写；registry 92 passed；全套 3605 passed。

### Change C — `skill-catalog-budget`（P1-C）✅
- 实现：`available_skills_prompt` 加 `max_skills=150`/`max_chars=18000` keyword 参数；抽出 `_render_catalog(shown, total, *, compact)` helper。两级降级：超条数截前 N + 警告 → 超字符切 compact（省 description）→ compact 仍超则按条数再截（至少留 1）。
- 决策点：
  - **函数默认参数而非 agent_config 字段**：最简单，调用点（normalizer/loop）零改动；per-agent 调节是未实现需求（YAGNI）。
  - **compact 是全有/全无 description**：避免半截描述误导模型；compact 只在超 18000 字符（极大库）触发。
  - **截断警告置于指令之前**：模型先知"列表不完整"再读 catalog。
  - **测试修正**：compact 测试初版 max_chars=600 触发了意外的条数再截（存活项依赖 dict 迭代序非 s0），改用 max_chars=1500 让 compact 容纳全部 5 个，干净测"切 compact 不再按条数截"。
- 测试：3 新 unit；registry 95 passed；全套 3635 passed。

### Change D — `skill-frontmatter-extensions`（P2-6 + P2-3 + P2-2）✅
- 实现：SkillEntry + _scan_dir 加三字段。
  - `disable_model_invocation`：_disabled_reason 加 "model_invocation_disabled"（audit_blocked 之后）→ catalog 隐藏；read_skill 不查 _disabled_reason 故仍可达。
  - `requires_tools`：available_skills_prompt 加 `available_tools: set|None=None`（None 不过滤，兼容）+ helper `_tools_available`；loop.py 加 `_visible_tool_names(allowed_tools)`（get_schemas + check_tool_access 同源）在两处 catalog 调用传入。渲染期过滤（工具集每会话可变）。
  - `required_env_vars`：`_as_env_var_list` 解析（过滤非 mapping/无 name）+ `skill_readiness(name)->{missing}` 查非 optional 且不在 os.environ 的 env；不阻塞 catalog。
- 决策点：
  - **顶层字段而非 metadata.fleetent 嵌套块**：更简单；未来需命名空间再迁移（YAGNI）。
  - **disable_model_invocation 走 _disabled_reason（scan期），requires_tools 走渲染期过滤**：前者作者意图固定，后者工具可用性每会话可变，分两层正交。
  - **available_tools=None 默认不过滤**：兼容未传工具集的调用方（纯渲染测试等）；loop.py 显式传。
  - **测试修正**：read_skill 返回完整 SKILL.md（含 frontmatter），初版测试误期望仅 body，改为 `"the body" in loaded`。
- 测试：5 新 unit；registry 100 passed；全套 3663 passed。

### Change E — `skill-observability-tracking`（P1-B）✅
- 实现：migration 057 建 skill_hits 表（id PK / skill_name / agent_id / session_id / triggered_at + index on skill_name）；skill_admin_store 加 record_hit(named params INSERT) + observe(COUNT + DISTINCT session)；read_skill 成功 load 后 best-effort try/except record_hit（tool_context 取 agent/session，import 函数内避循环依赖）；engine_observability 改调 observe 替换 stale 占位符。
- 决策点：
  - **命中点在 read_skill 成功 load 后**：只记成功加载；audit_blocked（Change A 审计）/ 未知名（笔误）不记。
  - **best-effort record_hit**：DB 失败记 warning 不阻断返回正文；与 Change A 审计同样的旁路安全姿态。
  - **lazy import**：builtin_tools → platform.skill_management 函数内 import，避免循环依赖。
  - **skill_hits 无保留策略**：append-only 流水，暂不做 TTL 清理（YAGNI）；未来可加（同 traces/session 清理模式）——记此处供后续。
- 测试：3 integration（真实 DB+migration）+ 3 unit（read_skill 命中/失败不阻断/拒绝不记）+ 1 unit（engine_observability 透传）；全套 3686 passed。

### Change F — `skill-askit-override-wiring`（P1-F）⏸️ 暂缓
- 调查结论：`askit_console` 仅 `agent_apply_api.py`——**agent 定义**的幂等 apply API（create_agent_def/update_agent_def/apply）。**无 skill 定义的概念或 apply 接口**。
- `askit_override`（promote/discard 漂移的 managed skill）需要 askit 能 apply **skill** 定义，但 askit 完全不建模 skill。
- **暂缓理由**：接线需先在 askit 建立 skill-authoring/apply surface（一个实质性新 capability，askit 当前只管 agent 定义）。强行复用 agent apply API 语义错误（skill ≠ agent）。当前 `askit_override` 占位返回 {ok:True} 不破坏功能——promote/discard 只是不落地 managed-skill 重新对账（drift 标志仍由 skill_admin_store.clear_drift 清除）。
- **后续建议**：单独立项"askit skill-authoring"——在 askit_console 加 skill 定义的幂等 apply（get/create/update_skill_def + apply），再回头接线 askit_override。属新 capability 而非"接线"，不应塞进本增强批次。
- 不强行造接口（避免错误的领域耦合）。task#6 标记 completed（已调查并决策暂缓）。
