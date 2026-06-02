# Design — Model Provider Management (Admin)

## 范围与边界

本 change **只设计 Admin 管理面**：provider 配置入口、task_type 路由编排、单价维护、连通性测试，以及健康 / 观测的可观察呈现。运行语义不在本面：

- **task_type → provider 映射、AsyncOpenAI client 实例化、fallback 链遍历与切换** → `model-router` 域（[model-router.md](../../../docs/capabilities/model-router.md)、[model-fallback spec](../../specs/model-fallback/spec.md)）。
- **成本追踪 / token 用量 / 错误率 / 时延采集** → `observability` 域。

本面只调上述域的**只读查询接口**与**触发动作接口**，不复制其状态机、不重定义 fallback 遍历或健康探针的判定逻辑。管理面对 model-router 的关系：UI 让 provider / 路由 / 单价成为后台可配置、可测连通、可设 fallback 顺序、可维护单价的一等公民，让 admin 无需手改 `config/settings.yaml`。

## 自托管口径

provider 的 `base_url` 可指向任意 **OpenAI-compatible 端点**（Anthropic / OpenRouter / 本地 Ollama / vLLM 等），符合「基础设施可自托管、数据不出内网」的部署原则。本面对自托管 / 自定义模型同样适用：这类模型常无公开单价，未配单价时成本显示「未配置」而非 0（见下）。

## 配置写入边界（保存即生效，不重启）

- 管理面**不直接重写** `config/settings.yaml`，也不绕过 model-router 的配置解释。provider 配置、task_type 路由顺序、单价的落库语义经 **fleetent 配置写入边界**完成（具体载体见 0.x 决策：新配置表经 Alembic，或经 model-router 配置写入边界写回）。
- **保存即生效**：写配置后运行时下一次 `get_async_client_and_config(task_type)` 即反映新 provider / 顺序 / 参数，**无需重启服务**（生效语义由 model-router 配置读取保证，本面只触发写入）。
- **与现有 `config/settings.yaml` 的关系与迁移**：当前 provider 定义与单价均在 `config/settings.yaml`。本面引入的存储载体须与 model-router 配置**单一来源**对齐——要么 model-router 改为从该载体读、`settings.yaml` 作为初始 seed 迁移导入；要么本面写回 `settings.yaml` 等价的配置写入边界。两者择一由 0.x 决策，**不得出现 settings.yaml 与新表双写不一致**。单价字段为 model-router 配置 schema 的**向后兼容追加**（缺省即「未配置」）。

## provider 配置面（provider-admin-api）

### provider 列表

- 列出所有已配置 provider，每个展示：名称、`base_url`、`model`、所属 task_type、在各 task_type fallback 链中的优先级（顺序位次）、最近连通状态（来自连通性测试 / 健康探针缓存）。
- api_key **脱敏展示**（保留前缀 + `***` 或整体 `***`），列表 / 详情 / 任何视图均不回明文。

### 新增 / 编辑 / 删除 provider

- admin 填：`base_url`、`model`、`api_key`、`max_tokens`、`temperature`、`extra_params`（provider 特有参数透传，原样保存、运行时由 model-router 透传给底层 client）。
- **api_key 脱敏存储与展示**：写入经配置写入边界，序列化层统一脱敏；编辑时不要求重填已存 key（留空 = 不变），新填的明文只用于落库不回显。
- 保存即生效（见配置写入边界）；删除 provider 从配置与**所有 task_type 路由**中移除，写审计。

### 按 provider·model 观测（消费 observability）

- 展示各 provider / 模型的调用次数、token 用量、成本（**单价已配时**）、错误率、平均时延、被哪些 task_type / Agent 使用。
- 数据源为 observability，本面只做按 provider·model 的聚合视图，不重复定义采集语义；成本聚合复用单价表（见下）。

## task_type 路由编排（task-type-routing-console）

- 可视化每个 task_type 的 provider 列表，**列表顺序即 fallback 优先级**（对齐 model-fallback：`[primary, ...fallbacks]`）。admin 拖拽调序、增删某 task_type 下的 provider；保存经配置写入边界，调整生产 task_type 路由写审计。
- **未知 task_type 回落明示**：UI 对未为某 task_type 配置任何 provider 的情况明示——运行时回落到 `default`（语义以 model-router 场景 4 为准），不报错。本面只呈现该回落规则，不在 UI 重算路由。
- **fallback 链预演**：选定一个 task_type 展示其完整 fallback 顺序，并可模拟「首选不可用」逐级回退的链路（对齐 model-router fallback 遍历语义 / model-fallback spec）。预演为只读演示，不发真实模型调用、不触发真实 fallback。
- **健康探针状态可见**：消费 model-router 健康探针缓存（规划项），展示某 provider 连续失败被标记暂时不可用、fallback 时被跳过的状态与恢复时间，帮助定位「为什么请求总走备选模型」。状态判定委托 model-router，本面只渲染。

## 模型单价表（model-pricing-table）

- 每个模型可维护 **input / output 每 1k token 单价**。单价表归 **model_router 配置**（与 provider / model 声明同处，operator 维护，对齐「待决问题」已定结论）；本面是其维护界面。
- 单价供统计面板 / observability 成本聚合按 `token × 单价` 计算。
- **未配置单价显示「未配置」而非 0**：自托管 / 自定义模型常无公开价，成本视图对未配置模型显示「未配置」字样，管理页对该模型单价项**高亮提醒**。区分「单价为 0」（显式配 0）与「未配置」（缺省），不得把缺省当 0 聚合出 $0 成本。
- 改单价写审计。

## 连通性测试（provider-connectivity-test）

- 对单个 provider 一键轻量探测：展示**是否可达、握手延迟、返回的模型标识**，用于「配完一个新端点先测通再挂路由」。
- **不计对外用量**：探测调用不写 observability 的成本 / token 用量（语义委托 model-router / 探测实现，本面只触发 + 呈现结果）。探测入口由 model-router 域暴露（跨域 follow-up），本面消费其返回。
- 探测可在「未挂路由」前进行；可达后 admin 方将其挂到某 task_type 路由。

## 敏感值脱敏（贯穿所有视图）

- **绝不明文回显 api_key**（provider 配置、列表、详情、连通性测试回显、观测视图）。
- **脱敏在序列化层统一处理**：所有 `/admin/providers/*` 响应经同一脱敏序列化器（如 `_mask(value)` → 保留前缀 + `***` 或整体 `***`），避免每端点各自处理而漏脱敏；审计 `detail` JSON 同样脱敏后再落库。
- 本面 API 接收明文 api_key 仅用于落库（经配置写入边界），落库后读取只输出脱敏占位；编辑留空表示不变更。

## 权限与审计

- 路由 `/admin/providers/*`，仿 `user_admin_api.py`：登录会话解析 → `auth.has_role` / `auth.require_role` 守卫。
  - **viewer**：只读——浏览 provider 配置（密钥脱敏）、task_type 路由顺序、fallback 预演结果、健康探针状态、按 provider·model 观测。
  - **admin / built_in_admin**：写——新增 / 编辑 / 删除 provider、编排 task_type 路由顺序、维护单价表、发起连通性测试。
- 写操作一律 `audit_log.write_audit(actor, action, target_type, target_id, detail)`：provider 增删改、改 task_type 路由顺序、改单价。
- 删除 provider / 调整生产 task_type 路由 / 改单价为重点审计动作；二次确认复用 platform.md 高危确认语义。

## 测试隔离（遵循 CLAUDE.md）

- `provider_admin_api.py` 不 import `agent_loop`，用 FastAPI **TestClient** 单测路由（与 `user_admin_api.py` 同款，规避 PEP 695 的 3.12 依赖）。
- **mock model-router / observability 接口**：本面只消费跨域只读接口（健康探针状态、连通性测试、按 provider·model 观测）与触发动作（连通性探测）；测试 patch 这些接口返回构造的状态 / 探测结果 / 观测聚合，断言列表渲染、路由顺序、回落明示、单价「未配置」呈现、脱敏；**不发真实模型调用、不发真实探测请求**（用 `respx` 或 `unittest.mock` mock client / 探测）。
- **脱敏断言**：构造含 api_key 的输入，断言任何响应体与审计 `detail` 均不含明文 key。
- **连通性测试不计用量断言**：mock 探测，断言探测不写 observability 成本 / 用量。
- **单价语义断言**：未配单价模型成本聚合返回「未配置」而非 0；显式 0 与缺省可区分。
- 数据库 / 路径隔离：若新建配置表，复用统一 DB fixture 或 `monkeypatch` `DB_PATH` 到 `tmp_path`；named params（`:x`），不新增 `?` 占位符；schema 走 Alembic，不在 store 里 `_init_db()` 建表。若复用 model-router 配置文件，则 monkeypatch 配置路径 / 写入边界到 `tmp_path`。
- 权限守卫：构造 viewer / admin / 无 session 会话，断言读放行、写 403（含场景 120 viewer 不可改）、无 session 401。
