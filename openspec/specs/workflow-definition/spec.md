# workflow-definition Specification

## Purpose
workflow.yaml 声明格式与 load 期校验：步骤/依赖/字段映射语法、DAG 禁环、引用存在性、tool schema 对照校验、定义目录解析。

## Requirements

### Requirement: workflow.yaml 声明格式

系统 SHALL 支持以 YAML 文件声明 workflow：顶层字段 `name`（必填，kebab-case 唯一名）、`description`（可选）、`inputs`（可选，启动参数声明：参数名 → `{type, default?}`）、`steps`（必填，非空列表）。每个 step SHALL 含 `id`（run 内唯一）、`type`（限 `tool` / `agent` / `notify`）、可选 `depends_on`（step id 列表，纯控制依赖）、可选 `timeout_seconds`（默认 300）、可选 `retry.max_attempts`（默认 0）。按 type 的专属字段：`tool` 需 `tool`（注册工具名）与 `args`（映射表）；`agent` 需 `prompt`（模板文本），可选 `agent`（目标 agent 名，省略=宿主 agent 自身）与 `output_schema`（JSON Schema）；`notify` 需 `text`（模板文本），可选 `to`（投递目标）。未知顶层字段或未知 step 字段 SHALL 触发校验错误（fail-closed，不静默忽略）。

#### Scenario: 合法定义加载成功
- **WHEN** 加载一个含 `tool → agent → notify` 三步、依赖与映射均合法的 workflow.yaml
- **THEN** 返回结构化定义对象，含全部 step 与解析后的依赖关系

#### Scenario: 缺少 type 专属字段被拒绝
- **WHEN** 一个 `type: tool` 的 step 未提供 `tool` 字段
- **THEN** load 失败并报明确错误（指出 step id 与缺失字段），不产生可执行定义

#### Scenario: 未知字段被拒绝
- **WHEN** 定义中某 step 含拼写错误字段（如 `depend_on`）
- **THEN** load 失败并指出该未知字段，MUST NOT 静默忽略

### Requirement: 定义目录解析

workflow 定义 SHALL 从统一目录加载：env `FLEETENT_WORKFLOWS_DIR` 优先，未设置时默认 `<config_dir>/workflows`，目录解析 SHALL 经 `paths.py` 统一优先级机制（与 agents/skills 目录同模式）。目录不存在或为空 SHALL 视为"无可用 workflow"（正常状态，不报错）；按 `name` 查找定义时不存在 SHALL 返回明确的 not-found 错误。

#### Scenario: env 覆盖生效
- **WHEN** 设置 `FLEETENT_WORKFLOWS_DIR=/tmp/wf` 且其中存在 `weekly-report.yaml`
- **THEN** `load_definition("weekly-report")` 从该目录加载成功

#### Scenario: 定义不存在
- **WHEN** 请求加载不存在的 workflow 名
- **THEN** 返回明确的 not-found 错误，列出可用 workflow 名以便排查

### Requirement: DAG 校验（禁环与引用存在性）

load 期 SHALL 执行图校验：step `id` 全局唯一；`depends_on` 与 `${steps.<id>...}` 引用的 step id 必须存在；以"控制边 ∪ 数据引用隐含边"构成的有向图 MUST 无环（Kahn 拓扑排序判定）；存在环时 SHALL 报错并指出环上的 step id 集合。自引用（step 引用自身输出）SHALL 按环处理拒绝。

#### Scenario: 环被拒绝
- **WHEN** 定义中 a `depends_on: [b]` 且 b 的 `args` 引用 `${steps.a.output.text}`
- **THEN** load 失败，错误信息包含成环的 step id（a、b）

#### Scenario: 引用不存在的 step
- **WHEN** 某 step 引用 `${steps.ghost.output.x}` 而 `ghost` 未定义
- **THEN** load 失败并指出无效引用及其所在 step

### Requirement: 字段映射语法与静态值

模板占位符 SHALL 仅支持两个命名根：`${inputs.<path>}`（run 启动参数）与 `${steps.<id>.output.<path>}`（上游 step 输出）；`<path>` 为点分路径，支持 dict key 与非负整数 list index。**step 字段中的数据引用 SHALL 自动隐含对被引用 step 的控制依赖**（无需重复写 `depends_on`）。不含 `${}` 的值即字面量静态注入，原样传递。load 期 SHALL 校验占位符语法合法且命名根有效；非法语法（如 `${foo.bar}` 未知根）SHALL 报错。

#### Scenario: 数据引用隐含控制依赖
- **WHEN** step `send` 的 `text` 引用 `${steps.analyze.output.summary}` 且未声明 `depends_on`
- **THEN** 图中存在 `analyze → send` 依赖边，`send` 在 `analyze` 成功前不会就绪

#### Scenario: 未知命名根被拒绝
- **WHEN** 某字段含 `${env.HOME}`
- **THEN** load 失败并指出仅支持 `inputs` / `steps` 两个命名根

#### Scenario: 字面量原样传递
- **WHEN** tool step 的 `args.url` 为不含占位符的字符串
- **THEN** 执行时该值原样传给工具，不做任何解析

### Requirement: tool step 的 schema 对照校验

对 `type: tool` 的 step，load 期 SHALL 对照工具注册表中该工具的 JSON schema 校验：工具名必须已注册；schema 声明的必填参数必须在 `args` 中出现（字面量或映射均可）；字面量参数值的类型 SHALL 与 schema 声明类型一致，不一致即报错；映射参数（`${}`）的类型校验推迟到运行期。引用未注册工具 SHALL 报错。

#### Scenario: 缺必填参数被拒绝
- **WHEN** 工具 schema 声明 `url` 必填，而 step `args` 未提供
- **THEN** load 失败并指出缺失的必填参数名

#### Scenario: 字面量类型不符被拒绝
- **WHEN** schema 声明 `count` 为 integer，而 `args.count` 为字符串字面量 `"abc"`
- **THEN** load 失败并报类型不匹配

#### Scenario: 映射参数推迟运行期
- **WHEN** `args.text` 为 `${steps.a.output.body}`（load 期值未知）
- **THEN** load 通过，类型核对留到运行期渲染时
