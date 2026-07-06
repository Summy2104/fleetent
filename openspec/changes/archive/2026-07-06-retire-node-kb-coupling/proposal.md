# retire-node-kb-coupling

## Why

node 与 KB 现存两处耦合都是为"agent 与 KB 同机直读"的旧形态服务的：①reconcile 在 platform 未物化 http provider 时从同机 kb-service.yaml 兜底注入；②容器后端给每个 agent 容器只读挂载租户 `kb/data/` 并在 spawn 前垫底建库。KB 中心化（kb-binding-provider-materialize 落地）后，platform 物化已是权威接线方，双轨注入重演"多套口径"的维护成本，且 fallback 有"同机掩盖异机 bug"效应（platform 忘配 kb_serve 时单机被兜底救活、上多机才炸，与 forwarder 内网 DNS 写死同型）；RO 挂载则背着 WAL 滞后快照的已知隐患。决策已定：**managed agent 的 KB 访问一律 HTTP，platform 配置 `kb_serve` 是 managed KB 的硬前提；local provider 只保留 standalone dev（`fleetent agent run` 同机）**。

## What Changes

全减法，无新增能力：

- **删 node 的 provider fallback 注入**：`node/reconcile.py` 的 `_inject_managed_knowledge_provider` / `_managed_kb_auth_ref` / `_managed_kb_url` 及 `_write_home` 调用点、`load_host_service_config` import。node 从此不读 kb-service.yaml、不产出任何 knowledge 配置——agent.yaml 的 knowledge 段以 platform 物化产物为唯一来源。
- **删容器后端的 KB 挂载与垫底**：`node/backend.py` ContainerBackend 的租户 KB 目录 RO 挂载、spawn 前 `_prepare_tenant_kb`（嵌入式迁移 + touch kb_vectors.db）及相关 import。agent 容器不再看得见任何 KB 文件——顺带结案 kb-ro-mount WAL 滞后快照隐患。
- **BREAKING（部署行为）**：platform 未配置 `kb_serve` 时，managed agent 即使有 KB 绑定也不再获得可用的检索通路（物化保持 local，容器内无文件可读）。依赖 node fallback 的存量部署升级后须在 platform.yaml 配置 `kb_serve` 段（模板已含）。
- 相关测试随删/改：注入测试改写为"node 不注入"守卫；容器挂载测试删 KB 断言。
- docs：`docs/capabilities/knowledge-base.md` 部署前提段明确"platform 物化是唯一接线方"。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-knowledge-config`：provider 部署形态默认从"managed 未声明时由 node 注入 http"改为"managed 的 http provider 由 platform 物化唯一注入；node MUST NOT 注入；platform 未配置则保持 local（仅同机 standalone dev 可用）"。
- `tenant-scoped-db-routing`：删除"容器部署下 node SHALL 把 `kb/data/` 只读挂入 agent 容器"的要求（`kb/data/` 归组与单元搬迁语义保留）；目录建立者清单中移除 node reconcile。

## Impact

- **Owning package**：`fleetent.node`（reconcile.py / backend.py），纯删除。
- **Public API surface**：无 HTTP 端点变化；agent 容器的挂载面收窄（少一个 RO mount）。
- **Owned tables / migrations / config namespace**：均无。
- **Cross-module dependencies**：node 对 `knowledge_base`（service_config、core.migrations）的 import 清零——node 与 KB 解耦完成。
- **Migration / shim plan**：无代码迁移。升级说明：managed KB 用户确认 platform.yaml `kb_serve` 段已配置（kb-binding-provider-materialize 起为权威通路）；已按 fallback 运行的环境在下一次物化/reconcile 后由 platform 通路接管。
- **切片终审**：不触碰 dockerize 线的 compose 文件与文档；与在途 change 无文件交叠。
