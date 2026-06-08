# Design: structured-logging-infrastructure

## Context

`structured_logging` 现居 `observability/`（CLAUDE.md「agent 运行时模块」之一）。实测它被 37 文件跨 9 区域消费，其中 **platform 4 处**——一个真正的 agent-runtime 模块不会被 platform 反向依赖，这反证它是跨域底座。intelligence-layering 重构已确立同类处理范式（`vector_store`：无业务态、KB+memory 共消费 → 提为顶层基础设施 + shim + 依赖护栏）。本 change 把同一范式套到 structured_logging，范围独立。

## Goals / Non-Goals

**Goals**
- 把 structured_logging 物理提为顶层基础设施模块，定位正确（跨域底座，非 agent runtime）。
- 固化依赖契约：被任意层（含 platform）消费，自身不 import 业务/平台。
- 行为/公共 API 零变更，旧 import 路径经 shim 持续可用。

**Non-Goals**
- 不改 logger 行为、level 语义、脱敏基线、通道隔离逻辑。
- 不动 observability 的其余成员（traces / usage / diagnostics / performance / pilot_verification）。
- 不碰 `platform/maintenance` 写 trace 的边界问题（属 governance 线，另议）。

## Decisions

### D1: 顶层单文件模块 `fleetent.structured_logging`，不建 package
- **选择**：`observability/structured_logging.py` → `src/fleetent/structured_logging.py`。
- **理由**：它是单个 ~7KB 文件；codebase 已有 `config.py` / `db.py` / `paths.py` / `auth.py` 等顶层单文件模块惯例，符合「顶层平铺」哲学。
- **Alternative（弃）**：建 `structured_logging/` package——单文件无需 package，徒增空 `__init__`。
- **Alternative（弃）**：纯契约 relabel、不动代码——无法表达「不在 observability 下」的物理事实，import 路径仍误导。

### D2: target 名 = `structured_logging`，禁用 `logging`
- `logging` 会 shadow stdlib `logging`，本模块内部及全仓大量 `import logging` 将被劫持。沿用现名零风险。

### D3: shim 在 `observability/structured_logging.py` re-export，本 change 内迁完即删
- 旧路径保留 `from fleetent.structured_logging import *` + 显式 re-export，37 调用方在本 change 内分批改到新路径；改完删 shim（vector-store 同款做法）。
- **理由**：本 change 体量可控（纯路径替换），一次做透比留长期 shim 干净。`observability/__init__` 若曾 re-export logger，同步指向新路径。

### D4: 依赖护栏随本 change 上
- 在 `module-dependency-guardrails` 加断言：`structured_logging` 可经顶层路径导入；MUST NOT import 业务能力模块（runtime/memory/kb/...）与 `platform`。与 vector_store 的护栏并列。

### D5: CLAUDE.md 本 change 内同步改
- 与 intelligence 多阶段「契约统一收口」不同，这是独立单 change，无中间态反复，故契约文字随代码一起改：把 structured_logging 从「agent 运行时模块」列表移出，标为基础设施底座。

## Risks / Trade-offs

- **[circular import 风险]** structured_logging 被 config.py 消费，而它自身可能读配置 → Mitigation：迁移后跑全量 import smoke（`runtime/loop` 触发链 + server 启动），确认无环；保持它不 import 业务模块即天然无环。
- **[遗漏调用方致运行期 ImportError]** → Mitigation：shim 在位时旧路径仍可用，红绿循环 + `make test-pr` + integration 基线对照兜底；删 shim 前 grep 确认零旧路径残留。
- **[mypy/ruff 路径敏感断言]** 测试里 monkeypatch `observability.structured_logging.X` 的 → Mitigation：patch 目标改打到 `fleetent.structured_logging` 真实模块（同 runtime shim 教训）。

## Migration Plan

1. 移动文件到顶层，旧路径留 re-export shim（绿）。
2. 加依赖护栏断言（红→绿）。
3. 分批把 37 调用方 import 改到 `fleetent.structured_logging`（每批跑受影响层）。
4. 全部迁完 → 删 shim → grep 确认零残留 → CLAUDE.md 改契约。
5. 收尾 `make test-pr` + integration 基线对照。

**Rollback**：保留 shim 即可随时回退（旧路径始终可用）；删 shim 前的任一步都可单独 revert。

## Open Questions

- 无强阻塞项。唯一可议：observability spec 的 structured-logging **行为** requirements 是否一并迁到新 `structured-logging` spec？本 change 取保守——行为 spec 留 observability，新 spec 只管放置/边界契约，避免一次动太多 spec。可在 review 时确认。
