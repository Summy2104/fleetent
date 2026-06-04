## Why

蓝图 `runtime-package-blueprint`（已归档）既定的迁移序列已全部落地：sandbox→`integrations/sandbox/`、session→`session/`、skills→`skills/`、model→`model/`、tools→`tools/`、runtime→`runtime/`（PR #4-#8 + sandbox PR #98）。蓝图明确规定：全部迁完后用**一个收尾 change 统一删除所有 re-export shim**——本 change 即执行这一收官步。

当前 `src/fleetent/` 下仍残留 32 个旧扁平路径文件，全是纯 re-export shim（8-16 行、零 def/class）。src 与 tests 对这些旧路径的引用已清零（`from fleetent.<旧模块> import` 与字符串 patch 目标均为 0），shim 已无任何消费方，继续保留只会让 `package-architecture` 与 `module-boundaries` 两份 spec 处于「迁移期过渡态」与「legacy 已移除」的自相矛盾状态。删除它们即消解矛盾、收口公共 API 边界。

main 已有同类先例可照抄：`mcp_client.py` / `memory_layer.py` 早已删除并有 `tests/unit/test_memory_legacy_import_cleanup.py` 断言旧路径导入失败；`openspec/specs/module-boundaries/spec.md` 已为 admin/governance/integrations/memory 域确立「Legacy 导入已移除」需求范式。

## What Changes

- **删除 32 个 re-export shim 文件**（`git rm`，纯壳无逻辑）：
  - sandbox(7)：`sandbox_client/sandbox_config/sandbox_manager/sandbox_enablement/sandbox_cleanup/sandbox_secrets/sandbox_output_truncation.py`
  - session(2)：`session_mgr/session_index.py`
  - skills(2)：`skill_registry/skill_audit.py`
  - model(2)：`model_router/provider_health.py`
  - tools(6)：`tool_registry/tool_result_truncation/plugin_loader/vision_client/image_gen_client/multimodal.py`
  - runtime(13)：`agent_loop/context_mgr/agent_runtime/sub_agent/sub_agent_lifecycle/termination/loop_detector/budget/layered_budget/cancellation/message_hygiene/error_classifier/tool_guardrails.py`
- **新增回归测试** `tests/unit/test_legacy_flatpath_import_cleanup.py`：parametrize 遍历 32 个旧模块路径断言 `ModuleNotFoundError`；正向用例抽查 6 个新包路径 import 成功且公共符号可达。
- **改文档**：README.md「Adding Tools」示例的注释与 import 从旧扁平路径改为新包路径。
- **改 spec**（本 change 的 spec delta）：
  - `package-architecture`：6 个能力域 Requirement 里「旧扁平路径 SHALL 仅保留为 shim」措辞改为「旧扁平路径 SHALL 已移除、不再可导入」，对应 Scenario 改为「旧扁平路径已移除」（WHEN 导入旧路径 THEN ModuleNotFoundError），其它 Scenario 不变。
  - `module-boundaries`：为 runtime/model/tools/skills/session 域补齐「legacy 导入已移除」表述，对齐已有 admin/governance/integrations/memory 范式。

不改任何 src 运行时逻辑——只删 shim + 加测试 + 同步文档/spec。

## Capabilities

### Modified Capabilities
- `package-architecture`: 6 个能力域（sandbox/session/skills/model/tools/runtime）由「旧路径仅为 shim」推进到「旧路径已移除、不可导入」，消解过渡态。
- `module-boundaries`: 为 runtime/model/tools/skills/session 域补齐「legacy 导入已移除」需求，与 admin/governance/integrations/memory 范式一致。

## Impact

- **代码**：删除 `src/fleetent/` 下 32 个 shim 文件；零运行时逻辑改动。
- **测试**：新增 `tests/unit/test_legacy_flatpath_import_cleanup.py`（33 个 parametrize 旧路径用例 + 6 个新路径正向断言）；全量套件作回归网。
- **关键回归点**：`import fleetent.tools` 触发的内置工具注册副作用不变（`get_schemas()` 仍为 12）；新包公共 API 全部可达。
- **依赖**：无新依赖。
- **蓝图**：引用 `runtime-package-blueprint`——本 change 是其规定的收尾步。
- **分支**：基于并 PR 合回 `main`。
