# unified-file-exchange

## Why

agent 当前存在两个互不可见的文件世界：agent workspace（`/workspace`，file 工具与沙箱的唯一根，带越界围栏）和各 MCP server 的私有文件目录（fleetent 对其位置与内容零感知）。MCP 工具产出的文件（下载、导出）落在后者，导致 `send_file` 够不着、`read_file`/`run_code` 无法消费——2026-06-12 实测事故中 google-drive 导出的 xlsx 无法投递给用户，模型被迫谎报完成；模型甚至主动传过 `/workspace/...` 路径试图统一两个世界（被 server 拒绝），证明缺的是系统层的统一文件平面，而非模型能力。

## What Changes

- **新增统一文件交换区（file exchange）**：路径命名空间扩为双根——`/workspace/...`（session 私有，现状不动）+ `/exchange/<server_id>/...`（MCP 产物区）。模型全程只用路径，不引入任何新引用语义（无 artifact id 暴露）。
- **MCP 启动约定注入**：stdio server 子进程默认注入 `cwd` + `XDG_DATA_HOME/XDG_CONFIG_HOME/XDG_CACHE_HOME` 指向 `<agent_home>/exchange/<server_id>/` 分区树（data=产物区、config/cache 不进命名空间）。优先级 `安全白名单 < 约定注入 < agent.yaml 显式 env`——显式配置的存量部署（如 google-workspace 的 xdg 树）被原地收编为有效文件根，**零迁移**。逃生门：`file_isolation: off`、`file_root: <path>`。
- **咽喉层路径规范化与登记**：MCP 调用结果中位于有效文件根内的 host 绝对路径被确定性改写为 `/exchange/...` 规范路径并同步登记；调用窗口 diff（per-server 锁）兜底登记结果中未提及的新文件。
- **artifacts 台账**（agent_state.db 新表，嵌入式迁移）：记录工件的来源 server、相对路径、归属 session_id 等治理元数据；台账是访问控制与审计的依据，**不是模型接口**。
- **归属即访问控制**：fence 解析 `/exchange` 路径时统一校验归属——本 session 产物放行，跨 session 拒绝（host 侧所有 file 工具一致生效）。
- **沙箱归属视图**：per-session 硬链接视图目录以只读挂载为容器 `/exchange`，容器内外路径一字不差且跨 session 物理不可见；不支持多挂载的后端经 `BackendCapabilities` 能力位降级为 exec 前 staging 复制。
- **send_file 风险参数化**：保留工具（无收件人参数、免审批快速通道），免审批四条件（回当前会话 / DM / 文件全为本会话归属 / 交互上下文）全满足→直发；任一不满足→**自动升级 medium 审批**（替代现行"直接拒绝"）。支持 `/exchange` 路径。
- **send_im_message 增加 `files` 参数**：跨会话工件、指定目标的文件投递走它，恒为 medium 审批（审计不变量保持）。两工具共享同一执行内核。
- **权限门扩展**：`@tool(risk_level=...)` 支持 callable（按参数与上下文动态判风险），通用机制，本期仅 send_file 使用。

明确不做（future）：MCP resources 协议腿、MCP server 容器化、存量树物理搬家、workspace 产物与入站附件纳入台账、exchange 配额/TTL 清扫（仅留钩子）。

## Capabilities

### New Capabilities

- `file-exchange`: 统一文件交换区核心——`/exchange/<server_id>` 逻辑命名空间与有效文件根映射、artifacts 台账（归属/审计元数据）、归属访问控制、per-session 硬链接归属视图的构建与维护。

### Modified Capabilities

- `mcp-stdio-isolation`: 子进程环境构造新增"约定注入"层（cwd + XDG 三件套指向 exchange 分区树），优先级 白名单 < 约定 < 显式 env；新增 `file_isolation: off` 逃生门。
- `mcp-result-handling`: 工具结果新增确定性路径规范化（有效根内 host 绝对路径 → `/exchange` 规范路径）与登记；调用窗口 diff 兜底登记（per-server 锁）。
- `file-tools-sandbox-execution`: 路径围栏从单根（workspace）扩为双根（workspace + exchange），`/exchange` 解析附带归属校验；其余越界拒绝语义不变。
- `sandbox-workspace-mount`: 容器挂载新增第二卷——session 归属视图只读挂载为 `/exchange`；挂载后新增硬链接实时可见。
- `sandbox-backend-abstraction`: `BackendCapabilities` 新增 `exchange_mount` 能力位；无该能力的后端降级为 exec 前 staging 复制（行为可见，不静默）。
- `sandbox-file-send`: send_file 免审批条件参数化（四条件白名单），不满足时升级 medium 审批而非拒绝；path 支持 `/exchange` 命名空间。
- `builtin-outbound-tool`: send_im_message 新增可选 `files` 参数（附件投递），恒 medium 审批；与 send_file 共享执行内核。
- `permission-gate`: 工具注册的 `risk_level` 支持 callable（`(args, tool_context) -> "low"|"medium"|"high"`），调用期动态求值。

## Impact

- **代码**：新平铺模块 `src/fleetent/artifact_exchange.py`（台账 store + 命名空间解析 + 归属校验 + 视图管理，仿 `schedule_store.py` 注入模式）；`integrations/mcp/client.py`（注入/改写/登记）；`tools/file_sandbox_io.py`（fence 双根）；`tools/builtin_tools.py`（send_file/send_im_message）；`tools/registry.py` + `governance/permission_gate.py`（callable risk）；`integrations/sandbox/`（视图挂载 + 能力位）。
- **owned tables**：`artifacts`（agent_state.db，嵌入式迁移下一版本号）。
- **config namespace**：`mcp_servers[].file_root` / `mcp_servers[].file_isolation`（均可选）。
- **依赖方向**：`integrations/mcp`、`tools`、`integrations/sandbox` → `artifact_exchange`；全部 agent 侧，零 `fleetent.platform.*` import（解耦契约不变）。
- **兼容性**：存量 agent.yaml 零改动（显式 env 优先并被收编）；send_file 行为变化为"拒绝→升级审批"（模型可见、对用户更顺）；容器新增只读挂载为增量变更，旧容器自然轮换。
- **关联但不在本 change**：审批挂起-恢复的会话地址统一（conversation-address）、投递回执与完成后置校验——另行提案。
