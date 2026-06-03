## Context

张洋的能力域多为平铺单文件;其它 owner 的域已 package 化。现有 package 惯例(本蓝图沿用):
- **package = 目录 + `__init__.py`**,`__init__.py` re-export 该域**公共 API**(参照 `integrations/mcp/__init__.py`)。
- **域大** → 拆按职责切的内部模块(参照 `intelligence/memory/` 的 `store.py`/`operations.py`/`search.py`);**域小** → 包内少量模块。
- **去冗余前缀**:`mcp_client.py` → `mcp/client.py`。
- **跨包只 import 包公共 API**,不碰另一包内部模块。

## Goals / Non-Goals

**Goals**
- 张洋 7 个能力域各自成 package,边界清晰、跨包只用公共 API。
- 对齐现有 package 惯例与命名。
- 蓝图可被后续逐包迁移 change 直接引用;迁移全程行为不变、可回退。

**Non-Goals**
- 本 change **不搬源码**(只立蓝图 + 更新架构文档)。
- 不改运行时行为 / 公共契约 / 数据库 schema。
- 不重写模块内部逻辑;不调整既有依赖方向(如 runtime↔sub_agent 的 lazy import 边界)。
- 不动其它 owner 的域。

## Decisions

### D1 — 扩成 7 个能力包,不折叠
架构文档的 8 个粗包是草图;张洋有 7 个 capability 文档边界,故 `model/`、`tools/`、`skills/`、`session/` 各自独立成包,不折叠进 `runtime/`。`runtime/` 只装 agent 执行核心 + 运行治理。

### D2 — sandbox → `integrations/sandbox/`
`sandbox_client` 是 Docker daemon 的 CLI 适配器,与 `mcp`(MCP server 适配)、`connectors`(OAuth 适配)同属「工具依赖的、可插拔的外部执行后端」。放 `integrations/` 边界最清晰,且对齐架构文档与现有 `integrations/mcp/`。它不进 `runtime/`(runtime 是编排,sandbox 是 `run_code` 工具背后的执行后端)。

### D3 — 去冗余前缀重命名
对齐 `mcp/client.py`:`sandbox_client.py`→`sandbox/client.py`、`tool_registry.py`→`tools/registry.py`、`session_mgr.py`→`session/manager.py` 等。用 `git mv` 保留 blame。

### D4 — 公共 API 收口 + 跨包只用公共 API
每包 `__init__.py` 只导出外部真正用到的符号;跨包 import 一律走包公共 API,不 import 另一包内部模块。

### D5 — 迁移期留 re-export shim,统一删除
迁移某包时,旧扁平路径(如 `src/fleetent/sandbox_client.py`)保留一行 `from fleetent.integrations.sandbox.client import *`(+ 显式 re-export 名)的 shim,**不承载逻辑**,让外部调用方与测试不立刻断。待**所有**包迁完且调用方改到新路径后,用一个收尾 change 统一删除所有 shim。

## 目标结构(张洋负责的部分)

```
src/fleetent/
  runtime/      loop.py(←agent_loop) context.py(←context_mgr) sub_agent.py
                sub_agent_lifecycle.py snapshot.py(←agent_runtime) termination.py
                loop_detector.py budget.py layered_budget.py cancellation.py
                message_hygiene.py error_classifier.py tool_guardrails.py
  model/        router.py(←model_router) provider_health.py
                vision_client.py image_gen_client.py multimodal.py
  tools/        registry.py(←tool_registry) builtins.py(←tools)
                result_truncation.py plugin_loader.py
  skills/       registry.py(←skill_registry) audit.py(←skill_audit)
  session/      manager.py(←session_mgr) index.py(←session_index)
  integrations/
    mcp/        (已成型,不动)
    sandbox/    client.py config.py manager.py enablement.py cleanup.py
                secrets.py output_truncation.py   # 去 sandbox_ 前缀
```

## 迁移机制(后续每个逐包 change 统一套路)

1. `git mv` 移文件到目标包,按目标命名去前缀。
2. 建 `__init__.py` re-export 公共 API(只导外部用到的)。
3. 改包内 import。
4. 旧扁平路径留 re-export shim(不承载逻辑)。
5. 改最直接的内部调用方到新公共 API(外部大面积调用留 shim 兜底)。
6. 全量门禁绿:`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` + `ruff` + `mypy`(本包不新增错误);关键符号 import 自检。
7. 走 bb-pr 合 main(注意 main 高速 trunk + CI + ≤3-behind)。

## 迁移顺序(blast radius 由小到大)

`integrations/sandbox`(自包含,调用方少,立范式)→ `session` → `skills` → `model` → `tools`(import 副作用注册需谨慎)→ `runtime`(agent_loop 1706 行、被全库引用,殿后)。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| `tools.py` 靠 import 副作用注册内置工具 | 迁到 `tools/builtins.py` 后确保仍被顶层 import,否则 `get_schemas()` 为空(CLAUDE.md gotcha) |
| 循环 import(runtime↔sub_agent 既有 lazy import) | 迁移保留既有 lazy import 边界,不在本系列重构依赖方向 |
| import 大面积改动易漏 | shim 兜底 + 每步全量 pytest/mypy + 关键符号自检 |
| main 高速 trunk,大 PR 难合 | 每包小 PR、由小到大、趁 CI 窗口快合 |
| 蓝图与逐包 change 脱节 | 各逐包 change proposal 显式引用本蓝图 change |

## Open Questions

- `vision_client` / `image_gen_client` / `multimodal` 归 `model/`(模型客户端,本蓝图选此)还是 `tools/`(它们服务于 analyze_image/image_gen 工具)?**默认 `model/`**,逐包迁移 model 时如有异议再调。
- `connectors.py` 是否一并进 `integrations/connectors/`?属张亮 channels/connectors 邻域,**本系列不含**,留张亮决定。
