# Tasks: structured-logging-infrastructure

## 1. 物理迁移 + 兼容 shim

- [x] 1.1 写失败测试：断言 `from fleetent.structured_logging import get_logger`（新顶层路径）可用 —— 先红（模块尚不存在）
- [x] 1.2 移动 `src/fleetent/observability/structured_logging.py` → `src/fleetent/structured_logging.py`；在旧路径放 re-export shim（`from fleetent.structured_logging import *` + 显式 re-export 公共名）—— 1.1 转绿
- [x] 1.3 写失败测试：断言旧路径 `from fleetent.observability.structured_logging import get_logger` 经 shim 仍可用 —— 应已绿（验证 shim 正确）；若红则修 shim
- [x] 1.4 跑 import smoke（server 启动链 + `runtime/loop` 触发链）确认无 circular import；受影响层 `uv run pytest tests/unit -q` 无新增失败

## 2. 依赖护栏（先红后绿）

- [x] 2.1 在 `tests/unit/test_module_dependency_guardrails.py` 加失败断言：`structured_logging` MUST NOT import 业务能力模块（runtime/memory/kb/reflection/long_term_ctx/session/tools）与 `fleetent.platform.*`，且可经顶层路径导入 —— 跑该测试见红（断言尚未覆盖新模块即视为未就位）
- [x] 2.2 确认/实现护栏逻辑使 2.1 转绿（structured_logging 本就不该 import 业务/平台；若实测有违规 import 则清理）
- [x] 2.3 `uv run pytest tests/unit/test_module_dependency_guardrails.py -q` 全绿

## 3. 调用方分批迁移（每批跑受影响层）

- [ ] 3.1 迁移 `runtime`（13 处）import 到 `fleetent.structured_logging`；跑 `tests/unit` 相关 + `tests/integration` 受影响
- [ ] 3.2 迁移 `integrations`(6) + `im_gateway`(2) import；跑受影响层
- [ ] 3.3 迁移 `knowledge_base`(4) + `session`(1) import；跑受影响层
- [ ] 3.4 迁移 `tui`(4) import；跑受影响层
- [ ] 3.5 迁移 `platform`(4) + `config.py` import；跑受影响层
- [ ] 3.6 迁移 `observability` 内部（`__init__` / `traces` / `diagnostics`，3 处）import 到新路径
- [ ] 3.7 修正测试中对 `observability.structured_logging` 的 monkeypatch/patch 目标，改打到 `fleetent.structured_logging` 真实模块

## 4. 删 shim + 契约收口

- [ ] 4.1 `grep -rn "observability.structured_logging" src tests`（排除 shim 自身与 binary）确认零旧路径残留
- [ ] 4.2 删除 `observability/structured_logging.py` shim；新增「收口后无残留旧路径」测试转绿（§spec structured-logging 第三 Requirement 末 scenario）
- [ ] 4.3 更新 CLAUDE.md：把 `structured_logging` 从「agent 运行时模块」列表移出，标为基础设施底座（理由：跨域日志底座，被 agent 与 platform 共同消费）；同步「现存待审计 agent→platform 依赖」相关措辞如涉及
- [ ] 4.4 更新 `openspec/specs/observability/spec.md` Purpose 注记：structured logger 的模块归属移交 `structured-logging` spec（仅 Purpose 文字，非 Requirement 改动）

## 5. 收尾验收

- [ ] 5.1 `uv run python scripts/check_test_layers.py` 通过
- [ ] 5.2 `make test-pr` 全绿
- [ ] 5.3 `uv run pytest tests/integration -q` 对照 main 基线，确认无新增失败
- [ ] 5.4 解耦基线复核：`fleetent agent run` 在无 platform 环境下日志正常（structured_logging 作为底座不引入 platform 依赖）
