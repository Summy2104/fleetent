## Why

平台已具备 [model-router](../../../docs/capabilities/model-router.md) 运行能力（task_type → provider 映射、OpenAI-compatible client 实例化、fallback 链遍历与切换），但**缺一个统一的 Admin 管理面**让 admin 一屏完成「新增一个 OpenAI-compatible 端点、测连通、挂到路由、设 fallback 顺序、维护单价」，对照 `platform.md` 的 model_provider 管理设计：

1. **provider 纯靠改文件**：新增 / 编辑 / 删除一个 provider（base_url / model / api_key / max_tokens / temperature / extra_params）目前要手改 `config/settings.yaml`，admin 没有后台入口；也看不到 provider 列表、所属 task_type、在各 task_type fallback 链中的优先级、最近连通状态。
2. **路由编排不可视**：每个 task_type 的 provider 列表（顺序即 fallback 优先级）无法在后台拖拽编排、增删；未定义的 task_type 运行时回落 `default` 这一语义对 admin 不透明。
3. **连通性无从验证**：配完一个新端点无法「先测通再挂路由」——缺一个不计对外用量的轻量探测。
4. **单价表无入口**：成本聚合（统计面板 `token × 单价`）需要的模型单价表（「待决问题」已定放 model_router 配置）没有维护界面；未配单价的自托管 / 自定义模型在成本视图应显示「未配置」而非 0，目前无处配置。
5. **健康探针不可见**：model-router 规划中的健康探针状态（某 provider 连续失败被标记暂时不可用、fallback 时被跳过）对 admin 不可见，定位「为什么请求总走备选模型」困难。

本 change **只叠加 Admin 管理面（provider 配置入口 + 路由编排 + 单价维护 + 连通性测试 + 健康/观测呈现）**，不重定义运行语义：task_type → provider 映射、AsyncOpenAI client 实例化、fallback 链遍历与切换归 model-router 域，成本追踪归 observability 域，本面只交叉引用并消费其只读接口与触发动作。

## What Changes

**ADDED**
- `provider-admin-api`：provider 列表（名称 / base_url / model / 所属 task_type / 在各 task_type fallback 链中的优先级 / 最近连通状态），admin 可新增 / 编辑 / 删除 provider——填 base_url、model、api_key（**脱敏存储与展示**）、max_tokens、temperature、extra_params（provider 特有参数透传）；保存即生效、无需重启，落库经 fleetent 配置写入边界；按 provider·model 观测视图（调用次数 / token / 成本[单价已配时] / 错误率 / 平均时延 / 被哪些 task_type·Agent 使用，数据源 observability）；权限与审计（增删改写审计，viewer 只读看脱敏配置 + 观测）。
- `task-type-routing-console`：可视化管理每个 task_type（`default` / `cheap` / `code` 等）的 provider 列表，**列表顺序即 fallback 优先级**，admin 拖拽调序、增删某 task_type 下的 provider；未定义的 task_type 运行时回落 `default`（语义以 model-router 为准），UI 对此明示；fallback 链预演（选定 task_type 展示完整 fallback 顺序并模拟逐级回退）；健康探针状态可见（消费 model-router 健康探针缓存：被标记暂时不可用 / fallback 时被跳过 / 恢复时间）。
- `model-pricing-table`：每个模型可维护 input / output 每 1k token 单价（对齐「待决问题」已定的「单价表放 model_router 配置」）；单价供统计面板成本聚合按 `token × 单价` 计算；**未配置单价的模型在成本视图显示「未配置」而非 0**，管理页对未配置项高亮提醒。
- `provider-connectivity-test`：对单个 provider 一键发起轻量探测，展示是否可达、握手延迟、返回的模型标识，用于「配完一个新端点先测通再挂路由」；**测试不计入对外用量**（不写 observability 成本/用量）。

**MODIFIED**
- 无核心运行模块语义变更。运行语义复用 model-router / observability，本 change 不修改其状态机。仅新增管理面读写与配置载体，并向 model-router 配置 schema **追加单价字段**（见 Impact 跨域 follow-up，由 model-router 域实现 schema 变更，本面只消费 / 维护）。

## Capabilities

### New Capabilities

- `provider-admin-api`
- `task-type-routing-console`
- `model-pricing-table`
- `provider-connectivity-test`

### Modified Capabilities

- 无（运行语义复用 `model-router` / `model-fallback` / `observability`，本 change 不修改其 spec；model-router 配置 schema 增单价字段 / 暴露健康探针状态读取 / 连通性测试入口列为跨域 follow-up）

## Impact

- **代码**：
  - 新增：`provider_admin_api.py`（`/admin/providers/*` 路由，仿 `user_admin_api.py`，复用 `auth.require_role` / `auth.has_role` + `audit_log.write_audit`，不 import `agent_loop` 以便 TestClient 隔离测试）。
  - 新增 / 复用（按 0.x 决策）：provider 配置与单价的存储载体。provider 配置与单价表当前来自 model-router 的 `config/settings.yaml`；本面是落库为新配置表（经 Alembic）还是经 model-router 配置写入边界写回，须与 model-router 配置一致，由 0.x 决策。
  - 修改：`server.py`（mount `provider_admin_api.router`）。
- **跨域 follow-up（运行语义在各域，本面只消费其只读接口 + 触发动作）**：
  - **model-router 域**需：(1) 配置 schema **增加单价字段**（每 provider·model 记 input / output 每 1k token 单价，与 provider / model 声明同处，对齐「待决问题」已定结论）；(2) **暴露健康探针状态读取**（某 provider 连续失败被标记暂时不可用 / fallback 时被跳过 / 恢复时间，对应 model-router「健康探针缓存」规划项）；(3) 提供 / 暴露**连通性测试入口**（轻量探测某 provider 是否可达、握手延迟、返回模型标识，不计对外用量）；(4) 暴露**保存即生效**的配置写入边界（管理面写配置后运行时按 task_type 路由立即反映，无需重启）。
  - **observability 域**用单价做**成本聚合**（`token × 单价`）；未配置单价显示「未配置」而非 0；本面按 provider·model 聚合其观测数据（调用次数 / token / 错误率 / 时延），不重复采集。
- **数据**：按 0.x 决策——若新建配置表则走 Alembic（不在 store `_init_db()` 建表），named params（`:x`），路径可 monkeypatch；若复用 model-router 配置文件 / 写入边界则不新建表，须说明与 `config/settings.yaml` 的关系与迁移。所有写审计落既有 `audit_log` 表。
- **安全 / 破坏性**：任何视图、响应体、审计 `detail` 与日志均**不明文回显 api_key**（脱敏在序列化层统一处理）。无破坏性变更；纯增量管理面（单价字段为 model-router 配置 schema 的向后兼容追加，未配置时成本显示「未配置」）。

## Commit 切分建议

每个 commit 自包含、内部 TDD（测试先红 → 实现 → 绿）：

1. `feat(provider_config_store): provider config + pricing storage + masked serialization`（按 0.x 决策，1.x）
2. `feat(provider_admin_api): /admin/providers list + CRUD (api_key masked)`（2.x）
3. `feat(provider_admin_api): connectivity test (no outbound usage)`（3.x）
4. `feat(provider_admin_api): task_type routing console + fallback preview + health probe view`（4.x）
5. `feat(provider_admin_api): model pricing table (unconfigured shows "not configured")`（5.x）
6. `feat(provider_admin_api): per-provider/model observability view`（6.x）
7. `feat(server): mount provider_admin_api router`（7.x）
