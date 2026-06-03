## Why

蓝图迁移序列**收官包**（sandbox✅ → session → skills → model → tools → **runtime**）：把 agent 执行核心 + 运行治理共 13 个平铺模块收进 `runtime/` 能力包。agent_loop（1706 行）被全库引用、被 18 个测试文件 39 处 patch——blast radius 最大，因此殿后，并在前五包的范式与教训（monkeypatch 随迁、lazy import、可变全局）全部验证后执行。

## What Changes

- **迁移 13 文件**到 `src/fleetent/runtime/`（`git mv` 保留 blame；蓝图已决：包内平铺，不预拆子包）：
  `agent_loop.py`→`loop.py`、`context_mgr.py`→`context.py`、`agent_runtime.py`→`snapshot.py`、`sub_agent.py`、`sub_agent_lifecycle.py`、`termination.py`、`loop_detector.py`、`budget.py`、`layered_budget.py`、`cancellation.py`、`message_hygiene.py`、`error_classifier.py`、`tool_guardrails.py`（后 10 个仅移动，名字不变）。
- **建 `runtime/__init__.py`** re-export 公共 API（`run`、`run_stream`、`CancelToken` 等）。
- **旧扁平路径留 13 个 re-export shim**（不承载逻辑；含 `agent_loop.py`——注意三处重命名 `loop.py`/`context.py`/`snapshot.py` 的 shim 源路径）。
- **改 src 直接调用方**：`cron_scheduler.py`、`__main__.py`、`server.py`、`tui/dispatch.py`、`im_gateway/normalizer.py`、`tools/builtin_tools.py`（tools 迁移后路径）；`sub_agent`↔`loop` 的 lazy import 边界**包内化但保持 lazy**（蓝图 Non-Goal：不改依赖方向）。
- **测试 patch 目标全量随迁**：39 处 patch `fleetent.agent_loop.*` 改为 `fleetent.runtime.loop.*`（shim 上 patch 不生效）——这是本包最大的机械改动面。
- 行为不变、无 schema 变更。

## Capabilities

### Modified Capabilities
- `package-architecture`: 记录 runtime 域**已完成包化**——`runtime/` 成包、公共 API 收口、旧路径仅 shim、契约/行为不变。至此蓝图 7 包全部落地，后续可启动「统一删 shim」收尾 change。

## Impact

- **代码**：新增 `src/fleetent/runtime/`（13 模块 + `__init__.py`）；13 个旧路径变 shim；6 处 src 调用方改 import。
- **测试**：18 个文件、39 处 agent_loop patch 随迁——必须逐处核对（patch 在 loop 命名空间内引用的符号名不变，仅模块前缀变）；纯 import 测试靠 shim 渐进。
- **关键回归点**：`import fleetent.runtime.loop` 仍触发 `import fleetent.tools` 注册副作用；run/run_stream 流式契约、压缩 identity check（`m is tail[0]`）、CancelToken 传播、sub_agent 深度限制全部不变。
- **依赖**：**硬依赖 tools 已迁**（loop 顶部副作用 import 与 registry 引用），软依赖 session/skills/model 已迁（loop 的 import 行在前序 change 已指向新包）。
- **后续**：全部 7 包就位后，单独提「删除所有 shim + 全库 import 切新路径」收尾 change。
- **分支**：基于并 PR 合回 `main`。
