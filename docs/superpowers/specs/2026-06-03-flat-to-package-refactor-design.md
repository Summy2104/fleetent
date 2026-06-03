# 平铺源码 → package 结构改造（张洋负责模块）

**日期**: 2026-06-03 · **负责人**: 张洋 · **状态**: 设计已批准,待 writing-plans

## 背景 / 问题

张洋负责的能力域(agent-runtime / model-router / tools / mcp / sandbox / skill / session)在 `src/fleetent/` 下大多是**平铺单文件**(`agent_loop.py`、`tool_registry.py`、`sandbox_*.py`、`session_mgr.py` 等 30+ 个),而其它 owner 的域已成 package(`intelligence/`、`integrations/mcp/`、`governance/`、`platform/`、`im_gateway/`、`observability/`)。`docs/architecture.md` 的「目标 package map」要求**代码按能力边界组织**,且「当前模块地图」已把 `integrations/sandbox/` 标为目标位置(代码尚未到位 → 文档/代码不一致)。

本改造把张洋的平铺模块**渐进迁移**到 package 结构,对齐架构文档与现有 package 惯例。

## 目标 / 非目标

**目标**
- 张洋的能力域各自成 package,边界清晰、跨包只用公共 API。
- 对齐现有 package 惯例(`__init__.py` 收口公共 API;去冗余前缀;域大拆内部模块)。
- 全程**行为不变**(纯结构搬迁 + import 调整),每步全量测试绿、可回退。

**非目标**
- 不改任何运行时行为 / 公共契约 / 数据库 schema。
- 不重写模块内部逻辑(只移动 + 改 import + 必要的去前缀重命名)。
- 不动其它 owner 的域(intelligence / platform control plane / channels 等)。
- 不一次性大爆改(见「推进方式」:渐进、逐包一个 PR)。

## 现有 package 惯例(本设计沿用)

- **package = 目录 + `__init__.py`**;`__init__.py` re-export 该域的**公共 API**(参照 `integrations/mcp/__init__.py`)。
- **域大** → 拆成按职责切的内部模块(参照 `intelligence/memory/` 的 `store.py`/`operations.py`/`search.py`…)。**域小** → 包内少量模块。
- **去冗余前缀**:`mcp_client.py` → `mcp/client.py`;据此 `tool_registry.py` → `tools/registry.py`、`sandbox_client.py` → `sandbox/client.py`、`session_mgr.py` → `session/manager.py`。
- **跨包只 import 包公共 API**,不碰另一个包的内部模块。

## 目标结构(张洋负责的部分)

```
src/fleetent/
  runtime/          # agent 执行核心(agent-runtime 域)
    __init__.py     # 公共 API: run, run_stream（+ 必要的运行治理类型）
    loop.py         # ← agent_loop.py
    context.py      # ← context_mgr.py
    sub_agent.py        sub_agent_lifecycle.py
    snapshot.py     # ← agent_runtime.py
    termination.py  loop_detector.py  budget.py  layered_budget.py
    cancellation.py message_hygiene.py error_classifier.py tool_guardrails.py
  model/            # LLM 路由(model-router 域)
    __init__.py     # 公共: get_async_client_and_config, ROUTES, RouteConfig/RouteOverride
    router.py       # ← model_router.py
    provider_health.py
    vision_client.py  image_gen_client.py  multimodal.py
  tools/            # 工具系统(tools 域)
    __init__.py     # 公共: tool, get_schemas, dispatch, set_schema_visibility_filter
    registry.py     # ← tool_registry.py
    builtins.py     # ← tools.py（import 副作用注册保持不变）
    result_truncation.py  plugin_loader.py
  skills/           # skill 域
    __init__.py     # 公共: scan, available_skills_prompt, match, load, ...
    registry.py     # ← skill_registry.py
    audit.py        # ← skill_audit.py
  session/          # session 域
    __init__.py     # 公共: session_lock, load, save, load_meta, list_session_ids, ...
    manager.py      # ← session_mgr.py
    index.py        # ← session_index.py
  integrations/
    mcp/            # 已成型(不动)
    sandbox/        # ← sandbox_*.py
      __init__.py   # 公共: SandboxClient, 资源/启用/清理 API
      client.py     # ← sandbox_client.py
      config.py     # ← sandbox_config.py
      manager.py    # ← sandbox_manager.py
      enablement.py # ← sandbox_enablement.py
      cleanup.py    # ← sandbox_cleanup.py
      secrets.py    # ← sandbox_secrets.py
      output_truncation.py  # ← sandbox_output_truncation.py
```

### 决策记录
- **扩成 7 个能力包**(model/tools/skills/session 各独立),不折叠进 runtime —— 对齐 7 个 capability 文档的边界(架构文档那 8 个粗包是草图,本设计据能力边界细化)。
- **sandbox → `integrations/sandbox/`** —— sandbox 是「工具依赖的外部执行后端」(Docker daemon 适配器),与 `mcp/`、`connectors` 同类;放一起边界最清晰,且对齐架构文档与现有 `integrations/mcp/`。
- **去冗余前缀重命名** —— 对齐 `mcp/client.py` 惯例。
- **infrastructure / channels 暂不在本改造范围**(config/db 是横切基础,connectors/cron/webhook 属张亮 channels 域)。

## 迁移机制(每个包统一套路)

每个包一个独立 PR,步骤:
1. **建包目录 + 移文件**(`git mv` 保留历史),按目标命名去前缀。
2. **建 `__init__.py`** re-export 该包公共 API(只导出外部真正用到的符号)。
3. **改包内 import**(模块间相对/绝对引用更新)。
4. **旧扁平路径留 re-export shim** —— 例如 `src/fleetent/sandbox_client.py` 仅一行 `from fleetent.integrations.sandbox.client import *`(+ 显式 re-export 名),**不承载逻辑**;让外部调用方与测试不立刻断。
5. **改最直接的内部调用方**到新公共 API(可选,降低 shim 依赖);外部大面积调用方留给后续清理。
6. **全量门禁绿**:`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` + `ruff` + `mypy`(本包不新增错误);关键符号 import 自检。
7. **合 main**(走 bb-pr;注意 main 高速 trunk + CI 门禁 + ≤3-behind)。

**shim 生命周期**:迁移期保留;待**所有**包迁完 + 调用方全部改到新路径后,用一个收尾 PR 统一删除所有 shim。

## 推进顺序(blast radius 由小到大)

1. **`integrations/sandbox/`** —— 自包含,调用方少(agent_loop/tools/server),立起迁移范式。
2. **`session/`** —— 调用方中等(agent_loop、normalizer、cron)。
3. **`skills/`** —— skill_registry/audit。
4. **`model/`** —— router + provider_health + 模型客户端。
5. **`tools/`** —— registry + builtins(import 副作用注册需谨慎保持)。
6. **`runtime/`** —— agent_loop 1706 行、被全库引用,blast radius 最大,殿后。

每个包是独立 spec→plan→实现→PR;本设计是共享的「目标与机制」,各包 PR 引用之。

## 风险 / 权衡

| 风险 | 缓解 |
|------|------|
| import 大面积改动易漏 | shim 兜底 + 全量 pytest/mypy 每步把关;关键符号 import 自检 |
| `tools.py` 靠 import 副作用注册内置工具 | 迁到 `tools/builtins.py` 后,确保 `runtime` 顶层仍 import 它(否则 `get_schemas()` 为空,见 CLAUDE.md gotcha) |
| 循环 import(runtime↔sub_agent 等既有 lazy-import) | 迁移时保留既有 lazy import 边界,不在本改造重构依赖方向 |
| main 高速 trunk,大 PR 难合 | 每包小 PR、趁 CI 窗口快合;顺序由小到大 |
| 测试里硬编码旧 import 路径 | shim 让多数测试不动;逐步把测试 import 改到新路径 |
| 重命名 vs 历史可追溯 | 用 `git mv` 保留 blame |

## 测试

- 每包迁移**不新增/不改测试语义**;只在测试 import 旧路径失败时改 import(优先靠 shim 避免)。
- 每步收尾:全量 `pytest -q`(带 `ANTHROPIC_API_KEY=sk-test-dummy`)+ `ruff check src tests` + `mypy src`(本包不新增错误模式)。
- 关键公共符号 import 自检(如 `from fleetent.integrations.sandbox import SandboxClient`)。

## 验收(整体)

- 张洋的 7 个能力域各自成 package,`__init__.py` 收口公共 API。
- 所有跨包调用走公共 API;无对其它包内部模块的直接 import。
- 全程行为不变,全量门禁持续绿。
- 收尾删除所有 re-export shim 后仍全绿。
- `docs/architecture.md` 模块地图与实际代码一致。
