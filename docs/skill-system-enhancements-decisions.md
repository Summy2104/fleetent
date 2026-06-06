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
