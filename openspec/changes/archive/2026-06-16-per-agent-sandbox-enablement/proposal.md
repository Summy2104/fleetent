## Why

沙箱启用由两层决定：全局三态 `sandbox.mode`（`off`/`selective`/`all`，从机器共享 `platform.yaml` 读）+ per-agent `features.code_execution`。这让 standalone agent（无 platform 服务）仍要为"能否跑 run_code"隐式读 `platform.yaml` 取 `mode`，与 agent⊥platform 解耦目标冲突。`mode` 的全局三态本质是"一份配置管多 agent"的机群策略，在 per-agent / standalone 形态下，每个 agent 的 `features.code_execution` 已足以表达其启用意图，三态属冗余的共享层。叠加 `per-agent-sandbox-resources`（Change 1）移除 resources/lifecycle 读取后，`mode` 是 `integrations/sandbox` 对 `platform.yaml` 的**最后一个读取点**。

## What Changes

- **移除全局三态 `sandbox.mode` 的 `platform.yaml` 读取**：删除 `load_sandbox_mode`/`_read_raw_mode`；`integrations/sandbox/enablement.py` 不再 `paths.platform_yaml_path()`。
- **`Mode` 塌缩为 {OFF, ON}**：`get_effective_mode(backend)` 仅依后端 `available()` 探测——可用→`ON`、不可用→`OFF`（保留"无 Docker 自动降级"）。`Mode`/`get_effective_mode`/`is_code_execution_enabled` 的**类型与签名保留**，多处调用方（server/file_tools/im_gateway/loop）几乎不变。
- **`features.code_execution`（per-agent）成为唯一启用策略**：`is_code_execution_enabled(mode, code_execution)` = `OFF→False`；`ON→ code_execution is not False`（**未声明=开**，保留今日 `all` 语义）。丢弃 `selective`/`all` 三态与机群"默认拒"策略。
- 从仓库 shipped `platform.yaml` 删除 `sandbox.mode`；迁移文档说明 `mode:off` → 各 agent `features.code_execution:false`、`mode:selective` → 仅给需要的 agent 设 `code_execution:true`。**不保留弃用告警**。
- **收口护栏**：叠加 Change 1 后，`integrations/sandbox` 任何模块都不再读取 `platform.yaml`——加 guardrail 测试锁定"沙箱零读 platform.yaml"。
- **BREAKING**：原先用 `mode:off` 全机禁用 / `mode:selective` 默认拒的部署，须改用 per-agent `features.code_execution` 表达。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `sandbox-enablement-control`: ① 移除全局三态 `mode`（off/selective/all）与其 `platform.yaml` 来源，`Mode` 收敛为"运行时是否具备沙箱能力"的 ON/OFF（仅由后端可用性决定）；② `features.code_execution` 成为唯一启用策略（未声明=开、显式 false=关），不再与全局 mode 联合判定；③ 重写"部署 mode 推荐选型指引"——去掉 off/selective/all 选型，改为按 per-agent `code_execution` + 运行时 Docker 可用性表述，保留"medium 免审批仅在运行时封闭（`sandbox_capable`）成立时生效、否则 fail-closed 升审批"不变式；④ "后端不可用降级 off" 语义保留。

## Impact

- 代码：`src/fleetent/integrations/sandbox/enablement.py`（删 `load_sandbox_mode`/`_read_raw_mode`/`SETTINGS_PATH`；`get_effective_mode` 只探测后端；`is_code_execution_enabled` 改 OFF/ON 判定）；`Mode` 枚举去 `SELECTIVE`/`ALL`、保留 `OFF` 并以 `ON` 取代 `ALL` 语义（保兼容的别名/最小改动由 design 定）；调用方 server.py/file_tools.py/im_gateway/normalizer.py/runtime/loop.py 适配收敛后的 `Mode`。
- public API surface：`Mode` 取值集合（OFF/ON）；`get_effective_mode`/`is_code_execution_enabled` 语义。
- owned tables：无（`features` 列已在 agent 存储，本 change 不改）。
- config namespace：移除 platform.yaml `sandbox.mode`；per-agent `features.code_execution` 不变。
- cross-module dependencies：移除 `integrations/sandbox` 对 `platform.yaml` 的最后读取（`mode`）；与 approval-minimization 的耦合改以运行时 `sandbox_capable` 表述（不改 approval 代码语义）。
- migration / shim：shipped platform.yaml 删 `sandbox.mode` + 迁移文档；无 re-export、无弃用告警。
- 依赖：建立在 `per-agent-sandbox-resources`（Change 1）之上——本 change 收口"沙箱零读 platform.yaml"护栏。
- 测试：Docker 在+code_execution 未声明/true→开、显式 false→关；无 Docker→恒关；无 platform.yaml→正常；`integrations/sandbox` 零读 platform.yaml 护栏；调用方对 ON/OFF 适配回归。
