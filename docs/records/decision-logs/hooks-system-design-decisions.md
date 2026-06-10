# Hooks 扩展体系 — 设计与决策

> 设计批次（2026-06-07）。为 fleetent 引入"运维可配的扩展点（hooks）"：在 agent loop 的关键 juncture 上以**进程内 Python** 回调拦截/改写/变换/注入/观测，**不 fork 内核**即可定制（合规拦截、脱敏、审计、注入企业上下文）。
> 对照 hermes/claude-code/openclaw/opencode 的 hook 体系，结合 fleetent 的 on-prem 数据主权 + lean + OpenAI-compatible + agent⊥platform 解耦约束裁剪而成。
> 与 `docs/agent-loop-enhancements-decisions.md` 同范式。全部 9 个钩子点分 4 批交付。

---

## 1. 目标 / 非目标

**目标**：企业在不改内核的前提下，于 agent loop 的明确 juncture 注入受治理的自定义逻辑——工具调用决策/改参、工具结果与最终输出的变换/脱敏、上下文注入、生命周期审计。

**非目标（永久）**：
- **绝不**支持 shell/外部进程 hook（数据主权：可信边界内不引入任意脚本执行/外泄面）。仅进程内 Python。
- 不做声明式无代码 hook 规则（hookify 式）——lean，先给程序化接口。
- 不引入 AI 框架、不依赖 platform、不引入新外部依赖。

---

## 2. 架构 A：三部件，各归其位

把 hook 拆成"怎么跑 / 从哪来 / 在哪触发并影响流程"三件本质不同的事：

| 部件 | 职责 | 落点 | 依赖 |
|---|---|---|---|
| **① 引擎** | hook 怎么跑：注册、按序、错误隔离、超时、结果合并 | 新建 `runtime/hooks.py` | 无（纯机制） |
| **② 加载** | hook 从哪来：发现 + import 运维 agent-local Python | 复用 `tools/plugin_loader` | FS / agent.yaml |
| **③ 集成** | hook 在哪触发、结果怎么影响 run | `loop.py` / `context.py` / `normalizer.py` 既有 juncture | 调①、与 governance 组合 |

**为什么这么拆**：三者变化原因不同（加载约定随插件系统、运行机制随并发/隔离、触发点随 loop 演进）→ 各自独立改/测。引擎不 import loop/governance/tools → 可像 `runtime/steering.py` 一样喂 ctx 断言 result 地单测。

**为什么复用②③而非全独立（方案 B）**：fleetent 已有"加载运维代码"（plugin_loader）与"工具准入决策"（agent_policy + permission_gate）两处**单一权威点**；再造平行机制 = 两套加载器 + 两处准入决策（顺序/冲突歧义）。A 只复用这两处、引擎仍独立。

**pre_tool_use 控制流（在既有准入点组合，不另起 gate）**：
```
模型要调 write_file(args)
  → ① allowed_tools 白名单？(schema 级, check_tool_access)  否→模型看不到
  → ② hooks.dispatch("pre_tool_use", ctx{tool_name,args})    ← 新增可编程层
        deny → 跳过分发, reason 反馈模型(现有 placeholder)
        ask  → 强制走 permission_gate(即使 low risk)
        modified_args → 用改写后的 args
        proceed → 继续
  → ③ risk∈{medium,high} 或 ②要求 ask ? → permission_gate 审批(现状)
  → 分发执行
```

---

## 3. 接口契约（一次定死，9 点共用）

```python
# 注册（用法同 @tool；import 副作用注册进引擎 registry）
@hook("pre_tool_use")
def my_policy(ctx: HookContext) -> HookResult | None: ...   # 可 sync 可 async

# 输入：只读运行上下文 + 事件专属载荷
@dataclass(frozen=True)
class HookContext:
    event: str
    session_id: str | None
    agent_name: str | None
    user_id: str
    payload: dict          # 事件专属只读快照（见 §5）

# 返回：None = 放行/不改；否则按该钩子点"允许能力"取用对应字段
@dataclass
class HookResult:
    decision: Literal["proceed", "deny", "ask"] | None = None  # 仅决策点
    reason: str | None = None                # deny/ask 时回灌模型/用户
    modified_args: dict | None = None        # 仅 pre_tool_use：改写入参
    modified_content: str | None = None      # 变换点：替换结果/输出/文本
    inject_context: str | None = None        # 注入点：追加上下文
    # 纯副作用（审计/通知）→ 直接做，返回 None
```

**执行语义（统一）**：
- **错误隔离**：单 hook 抛异常 → warn 日志 + 跳过，**绝不破坏 run**。
- **超时**：每 hook 带 deadline（`asyncio.wait_for`/`CancelToken`），不挂起 loop。
- **顺序**：同事件多 hook 按注册序；**决策点 first-deny-wins（短路）**；**变换点链式**（后者见前者输出）。
- **失败策略（仅决策点）**：默认 **fail-open + 审计**（hook 崩不挡工具但记审计）；agent.yaml 可开 **strict = fail-closed**（hook 崩即 deny）。
- 纯进程内 Python、async-friendly、agent-local。

---

## 4. 能力类型矩阵

| 能力 | 含义 | 返回字段 |
|---|---|---|
| 决策 veto/ask | 拦截/放行/转审批一次工具调用 | `decision` + `reason` |
| 改写输入 | 改写将执行的工具入参 | `modified_args` |
| 变换输出 | 改写工具结果 / 最终回复（脱敏、重写） | `modified_content` |
| 注入上下文 | 往 prompt/摘要追加"必保留/企业上下文" | `inject_context` |
| 观测/副作用 | 审计、外部通知、计数（不改流程） | 返回 None |

能力由钩子点声明，避免越权（如 output 钩子不得 veto 工具）。

---

## 5. 钩子点目录（9 点，落 fleetent 真实 juncture）

| 钩子点 | 触发落点 | payload | 允许能力 | 批 |
|---|---|---|---|:--:|
| **pre_tool_use** | `loop._plan_run_slots`(~675, 分发前) + run_stream plan | tool_name, tool_args | 决策 + 改写输入 | P1 |
| **post_tool_use** | `loop._backfill_slots` + run_stream backfill(工具返回后) | tool_name, args, result, failed | 变换输出 + 观测 | P2 |
| **output_transform** | `run` 返回前(~reply) + `run_stream` done 前 | text | 变换输出 + 观测 | P2 |
| **on_user_input** | `normalizer.route` / `run` 入口 | user_text | 变换输入 + 决策(拒绝) + 注入 | P3 |
| **pre_llm_call** | loop 顶 compress/sanitize/drain 后、调 LLM 前 | messages 快照 | 注入 + 观测 | P3 |
| **on_assistant_reply** | LLM 响应后(assistant 消息) | assistant_content | 变换 + 观测 | P3 |
| **pre_compact** | `context.maybe_compress`/`_compress` 前 | messages | 注入(必保留) + 观测 | P4 |
| **post_compact** | 压缩产出摘要后 | summary, stats | 观测 | P4 |
| **on_run_complete** | run 结束(reply 定稿, near log_run) | reply, stop_reason, usage | 观测/副作用 | P4 |
| **session_start / session_end** | 会话生命周期(normalizer/agent_app) | session 元数据 | 注入 + 副作用 | P4 |

---

## 6. agent.yaml 配置

```yaml
hooks:
  enabled: true                 # 总开关（默认 false：零配置零行为变化）
  decision_failure: open        # open(默认, fail-open+审计) | strict(fail-closed)
  timeout_seconds: 5            # 每个 hook 的超时
  # hook 代码经 plugins 机制从 agent-local 目录加载（复用 FLEETENT_PLUGINS_DIR）
```
经 `AgentFile` + `GovernanceConfig` + `_governance_from_file` 解析（与现有 governance 字段同模式）；不进 platform settings。

---

## 7. 安全立场与约束（on-prem 数据主权）

- **仅进程内 Python，永不 shell**：不在可信边界内引入任意脚本执行/外泄面。
- **agent-local + 零 platform**：hook 代码、配置全在 agent 侧；引擎不 import platform。
- **错误隔离 + 超时**：buggy/挂起的 hook 不破坏 run；决策点失败有 open/strict 双档。
- **默认关闭**：`hooks.enabled=false` 时零注册、零派发、零行为变化（字节级）。
- **可注入可 reset**：引擎 registry 是 module-level 可 monkeypatch + `reset()`（守"全局可变状态须可注入"红线）。

---

## 8. 与现有机制集成（不重复造）

- **pre_tool_use 决策** 与 `agent_policy.check_tool_access`(白名单) + `permission_gate`(审批) 组合于 `_plan_run_slots` 同一准入点（§2 控制流）。
- **加载** 复用 `tools/plugin_loader`（agent-local Python 发现/import + 解耦约定）。
- **脱敏** post_tool_use/output_transform 可复用 `tool-arg-secret-redaction`/`sandbox-output-redaction` 的脱敏函数。
- **审计** on_run_complete/post_tool_use 可写 observability trace / `platform-audit-log`（注：审计写入若涉 platform 表须经既有 agent 侧边界，hook 本身不直连 platform）。

---

## 9. 四批交付计划（每批 = 一个 OpenSpec change + PR，串行）

| 批 | change | 内容 | 钩子点 |
|:--:|---|---|---|
| **P1** | `agent-hook-engine` | 引擎 `runtime/hooks.py`(registry/HookContext/HookResult/dispatch/隔离/超时/reset) + plugin_loader 式加载 + agent.yaml 配置 + **pre_tool_use**(决策+改参，接 permission_gate 准入) | pre_tool_use |
| **P2** | `agent-hook-tool-output` | 工具结果/最终输出变换与观测(复用脱敏) | post_tool_use, output_transform |
| **P3** | `agent-hook-message-flow` | 消息流：入站变换/拒绝/注入、发送前注入、回复后变换 | on_user_input, pre_llm_call, on_assistant_reply |
| **P4** | `agent-hook-lifecycle` | 压缩与生命周期 | pre_compact, post_compact, on_run_complete, session_start, session_end |

P1 = 引擎 + 最难（governance 集成）的 pre_tool_use，一次把契约/隔离/超时验透；P2–P4 = "同契约 + 新 juncture + 测试"的廉价增量。串行避免 `loop.py` 合并冲突。

---

## 10. 测试策略

- **引擎单测**（`tests/unit`，纯机制）：注册/按序/first-deny-wins/变换链/异常隔离/超时/reset；喂 HookContext 断言 HookResult，零外部依赖（仿 `test_steering.py`）。
- **集成点单测**：每个钩子点在其 loop juncture 触发、payload 正确、效果生效（deny 跳过分发 / modified_args 生效 / modified_content 替换 / inject 进 prompt）；`hooks.enabled=false` 时零行为变化（回归保护）。
- **加载**：agent-local 模块 `@hook` import 后注册到 registry。
- 每批 TDD 红绿 + ruff/mypy/全量 pytest + `openspec validate --strict` + check_test_layers。

---

## 11. 关键决策记录

- **架构 A**（独立引擎 + 复用 plugin_loader 加载 + pre-tool 决策接 permission_gate 准入）——避免重复造"加载运维代码"与"工具准入决策"两处单一权威点；引擎独立保职责清晰。否决方案 B（全独立 → 两套加载器 + 两处准入）。
- **仅 Python、永不 shell**——数据主权硬约束。
- **决策点默认 fail-open + 审计**，strict 可选——可用性优先、合规可加严。
- **默认 `hooks.enabled=false`**——零惊吓，未启用字节级不变。
- **9 点全做、分 4 批**——契约 P1 定死，后续增量。

---

## 12. 执行记录（实施期追加）

```
(待实施)
```
