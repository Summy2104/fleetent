## ADDED Requirements

### Requirement: Flat-path package migration cleanup
flat→package 迁移收尾后，系统 SHALL expose runtime、model、tools、skills、session 五个能力域的实现 through 各自 canonical package paths only；这些域对应的 legacy 顶层平铺 shim 模块 SHALL NOT remain importable。

#### Scenario: Runtime canonical package exists
- **WHEN** 调用方导入 `fleetent.runtime` 或 `fleetent.runtime.loop`
- **THEN** 导入成功

#### Scenario: Model canonical package exists
- **WHEN** 调用方导入 `fleetent.model` 或 `fleetent.model.router`
- **THEN** 导入成功

#### Scenario: Tools canonical package exists
- **WHEN** 调用方导入 `fleetent.tools` 或 `fleetent.tools.registry`
- **THEN** 导入成功

#### Scenario: Skills canonical package exists
- **WHEN** 调用方导入 `fleetent.skills` 或 `fleetent.skills.registry`
- **THEN** 导入成功

#### Scenario: Session canonical package exists
- **WHEN** 调用方导入 `fleetent.session` 或 `fleetent.session.manager`
- **THEN** 导入成功

#### Scenario: Legacy runtime imports are removed
- **WHEN** 调用方导入 `fleetent.agent_loop`、`fleetent.context_mgr`、`fleetent.agent_runtime`、`fleetent.sub_agent`、`fleetent.sub_agent_lifecycle`、`fleetent.termination`、`fleetent.loop_detector`、`fleetent.budget`、`fleetent.layered_budget`、`fleetent.cancellation`、`fleetent.message_hygiene`、`fleetent.error_classifier` 或 `fleetent.tool_guardrails`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy model imports are removed
- **WHEN** 调用方导入 `fleetent.model_router` 或 `fleetent.provider_health`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy tools imports are removed
- **WHEN** 调用方导入 `fleetent.tool_registry`、`fleetent.tool_result_truncation`、`fleetent.plugin_loader`、`fleetent.vision_client`、`fleetent.image_gen_client` 或 `fleetent.multimodal`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy skills imports are removed
- **WHEN** 调用方导入 `fleetent.skill_registry` 或 `fleetent.skill_audit`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy session imports are removed
- **WHEN** 调用方导入 `fleetent.session_mgr` 或 `fleetent.session_index`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy sandbox flat-path modules are removed
- **WHEN** 调用方导入 `fleetent.sandbox_config`、`fleetent.sandbox_manager`、`fleetent.sandbox_enablement`、`fleetent.sandbox_cleanup`、`fleetent.sandbox_secrets` 或 `fleetent.sandbox_output_truncation`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Cleanup is behavior-preserving
- **WHEN** flat-path cleanup change 完成
- **THEN** 全量测试（`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`）通过，且仓库不包含运行时代码或数据库 schema 变更
