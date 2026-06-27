# fleetent-apply-api

## REMOVED Requirements

### Requirement: Idempotent agents apply API
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;已核实 `POST /admin/agents/apply` 零调用方。本次确立 `agents` 表为 agent 配置单一当前态真相源,apply 入口整体退役。
**Migration**: agent 创建/更新改由控制台直接写 `agents` 表当前态(见新 capability `agent-config-single-source`);`POST /admin/agents/apply` 与 `POST /admin/agents/apply:batch` 端点整体退役,无替代端点。

### Requirement: Apply owns the agent definition only, never bindings
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;apply 入口零调用方。本次确立 `agents` 表为 agent 配置单一当前态真相源,apply 入口整体退役,其"只写定义不碰 bindings"的边界约束随之消失。
**Migration**: agent 定义字段经控制台原地更新(见 `agent-config-single-source`);bindings(`user_agents`/默认绑定)仍是独立运行态,由各自路径管理,不再受 apply 边界约束;apply 端点无替代。

### Requirement: Apply upsert resolution and adopt
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;apply 入口零调用方。本次确立 `agents` 表为 agent 配置单一当前态真相源,apply 的 `agent_id`→`name` upsert 与 adopt 语义整体退役。
**Migration**: 无 apply 入口即无 upsert/adopt;agent 由控制台按 `agent_id` 直接定位与编辑(见 `agent-config-single-source`),provenance flip/adopt 概念一并退役,无替代端点。

### Requirement: 无服务端 askit 任务队列,部署唯一经 apply API
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;apply 入口零调用方。本次确立 `agents` 表为 agent 配置单一当前态真相源,"部署唯一经 apply API"前提消失。
**Migration**: askit 任务队列表(`askit_tasks`/`askit_task_logs`/`askit_workspaces`)仍保持不存在;"部署唯一经 apply API"约束随 apply 端点一并退役,agent 经控制台直写 `agents` 表(见 `agent-config-single-source`)。

### Requirement: Apply is authenticated and audited
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;apply 入口零调用方。本次确立 `agents` 表为 agent 配置单一当前态真相源,apply 端点整体退役,其专属鉴权/审计约束随之消失。
**Migration**: 控制台写 agent 配置走既有 admin 鉴权与审计路径(见 `agent-config-single-source`);apply 端点专属的鉴权与审计要求随端点退役,无替代端点。

### Requirement: Skills delivery triggers hot reload
**Reason**: 该条记述的 skill 投递→热重载行为原文即声明"不经 apply API",独立于 apply;apply 入口退役不影响该行为,它被冗余归档在 apply-api capability 下。
**Migration**: skill 投递与热重载行为由独立 capability `skill-hot-reload`(及 `skill-bundle-distribution`)继续承载(代码侧 `skills/registry.py` 的 `skill-external-hot-reload` 钩子),行为不变;仅从 apply-api capability 移除此冗余记述。

### Requirement: Managed agent model config carries provider env names, never secrets
**Reason**: 该条编码的是一条**活的安全保证**(agent 模型配置只引用 `api_key_env`、明文 secret 永不入 agent 定义/物化产物),与 askit/版本无关,本 change 之后依然成立,不应随 apply 退役而丢失。
**Migration**: 该安全保证迁移到 `agent-config-single-source` 新增的"模型凭证只引用 env 变量名"requirement 继续约束,并由既有 `platform-agent-lifecycle` 的 `.env` 物化要求共同保障;仅从 apply-api capability 移除其载体。
