## Why

`e2e-reflection-lifecycle` 落地后实跑暴露一个真覆盖缺口：reflection 的 **memory 提案"approve→apply"** e2e 被 **skip**——`_reflection_helpers` 用 `_new_agent_gateway_port()` 去**扫描端口猜** node 拉起的 agent gateway，猜不到就 `pytest.skip("managed agent /im/route gateway is not externally discoverable")`。结果"reflection-lifecycle"只验到"提案生成"，没验到"审批+apply 执行"——名不副实的那一半。

而 Wave B（`e2e-im-inbound-approval`）已用稳健方案解决了同一个 `/im/route` 可达性问题：`_im_helpers.managed_agent_route_server` **另起一个 `fleetent agent run --no-im --port <已知端口>` 进程**指向同一 agent home，B 的 4 个 `/im/route` 测试全靠它跑通。D5 只是没复用它。这是可修的 harness 缺口（非不可行）。

## What Changes

- `_reflection_helpers.approve_reflection_proposal_via_im` 改为经 **spawned managed agent route server**（复用 B 的 `managed_agent_route_server` 方案，已知 reserved 端口）驱动 `approve <proposal_id>`，**取代** `_new_agent_gateway_port()` 的端口扫描猜测。
- 移除"gateway 不可发现就 skip"的降级；memory 提案 approve→apply 这条 e2e **真正执行**（不再 skip）。
- 同样适用于 skill 提案 approve 路径（若该 scenario 已落地经 /im/route 审批）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `e2e-reflection-lifecycle`: "memory-maintenance 提案经真实审批后 apply" 与 "skill 提案经审批后写盘" 两条要求收紧——审批 MUST 经 spawned managed agent route server（已知端口）驱动，不得靠 best-effort 端口发现、不得在 gateway 不可自动发现时 skip 核心 approve→apply 路径。

## Impact

纯测试侧改动，零 src 产品代码改动。

- **owning package**：`tests/e2e`（改 `_reflection_helpers.py`；复用 `_im_helpers.managed_agent_route_server`）
- **public API surface**：无
- **owned tables**：无
- **config namespace**：无
- **cross-module dependencies**：`tests/e2e/_reflection_helpers` 复用 `tests/e2e/_im_helpers.managed_agent_route_server`（两者皆 e2e 测试 helper，允许跨 helper 复用）；不引入 src 依赖
- **migration / shim**：无
- **受影响代码**：`tests/e2e/_reflection_helpers.py`（改审批驱动方式）、`tests/e2e/test_reflection_lifecycle.py`（被 skip 的断言转为真跑）；**不改** `tests/e2e/conftest.py::managed_stack` 核心、**不改** src
- **CI**：仍进 `make test-e2e` slow lane，不进 per-merge `make test-pr`
