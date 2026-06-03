## ADDED Requirements

### Requirement: 从插件目录扫描并加载插件

平台 SHALL 提供插件加载能力，扫描一个可配置的插件目录（默认 `./plugins`，可经环境变量 `FLEETENT_PLUGINS_DIR` 覆盖），把其中每个含 `plugin.yaml` 清单文件的子目录识别为一个候选插件。当插件目录不存在时，加载 MUST NOT 抛出异常，视为没有任何插件。

#### Scenario: 识别含清单的插件目录
- **WHEN** 插件目录下存在子目录 `crm_tools/` 且包含 `plugin.yaml`
- **THEN** 该子目录被识别为名为其清单声明的候选插件

#### Scenario: 环境变量覆盖插件目录
- **WHEN** 设置了环境变量 `FLEETENT_PLUGINS_DIR` 指向某目录
- **THEN** 加载从该目录而非默认 `./plugins` 扫描

#### Scenario: 插件目录不存在
- **WHEN** 配置的插件目录不存在
- **THEN** 加载返回空结果且不抛出异常

### Requirement: 仅加载启用的插件

加载 SHALL 仅加载 `plugin.yaml` 中 `enabled` 为真的插件。`enabled` 缺省或为假的插件 MUST 被跳过，且其代码 MUST NOT 被导入。

#### Scenario: 启用的插件被加载
- **WHEN** 某插件的 `plugin.yaml` 含 `enabled: true`
- **THEN** 该插件被加载，其工具进入工具注册表

#### Scenario: 未启用的插件被跳过
- **WHEN** 某插件的 `plugin.yaml` 含 `enabled: false` 或未声明 `enabled`
- **THEN** 该插件被跳过，其代码不被导入，其工具不进入工具注册表

### Requirement: 插件工具加命名空间前缀

加载启用的插件时，平台 SHALL 复用现有 `@tool` 注册机制（导入插件包触发注册副作用），并将该插件注册的每个工具重命名为命名空间形式 `{插件名}__{工具名}`（双下划线分隔），保留其原有 schema 与 risk_level。命名空间前缀 MUST 使用双下划线，与 MCP 工具 `{server}__{tool}` 约定一致。

#### Scenario: 插件工具带命名空间前缀注册
- **WHEN** 插件 `crm_tools` 的 `__init__.py` 含一个 `@tool` 函数 `lookup`
- **THEN** 工具注册表中以 `crm_tools__lookup` 注册该工具，且不以裸名 `lookup` 单独存在

#### Scenario: 命名空间工具保留 schema 与 risk_level
- **WHEN** 插件工具声明了 `risk_level="medium"`
- **THEN** 命名空间化后的工具 `{插件名}__{工具名}` 仍报告 `risk_level="medium"`，其 schema 的工具名为命名空间名

### Requirement: 清单错误或导入失败时跳过并告警

当某插件的 `plugin.yaml` 格式错误（缺失、非法 YAML、顶层非映射、缺 `name`）或其代码导入失败时，平台 MUST 跳过该插件并记录一条 warning 日志，MUST NOT 因此中断平台启动或阻断其余插件的加载。

#### Scenario: 清单格式错误被跳过
- **WHEN** 某插件的 `plugin.yaml` 是非法 YAML 或缺少 `name`
- **THEN** 该插件被跳过并记录 warning，加载流程继续

#### Scenario: 插件代码导入失败被跳过
- **WHEN** 某启用插件的 `__init__.py` 在导入时抛出异常
- **THEN** 该插件被跳过并记录 warning，其工具不进入注册表

#### Scenario: 单个坏插件不影响其余插件
- **WHEN** 插件目录中同时存在一个清单错误的插件和一个有效插件
- **THEN** 有效插件被正常加载，其工具进入注册表

### Requirement: 平台启动时加载插件

平台 SHALL 在服务启动时（开始接受请求之前）执行一次插件加载，与技能扫描同生命周期。

#### Scenario: 启动时加载插件
- **WHEN** 平台服务启动
- **THEN** 在服务开始接受请求前执行一次插件加载

### Requirement: agent 须经 plugins 白名单授权方可见可用插件工具

agent 定义 SHALL 含一个 `plugins` 列表（默认为空，向后兼容）声明其被授权的插件。仅当某插件在该 agent 的 `plugins` 列表中时，该插件的工具才对该 agent 可见可用；未列出插件的工具 MUST NOT 出现在暴露给 LLM 的工具列表中，亦 MUST NOT 被该 agent 调用。该授权 SHALL 复用既有的工具访问控制机制：将 agent 的 `plugins` 展开为命名空间模式 `{插件名}__*` 并入该 agent 的有效 `allowed_tools`，由暴露给 LLM 前的工具 schema 过滤（既有 `check_tool_access` 判定）施加。

#### Scenario: 已授权插件的工具暴露给 LLM
- **WHEN** 某 agent 的 `plugins` 含 `crm_tools`
- **THEN** `crm_tools__lookup` 出现在暴露给该 agent 的工具 schema 列表中，可被调用

#### Scenario: 未授权插件的工具不暴露
- **WHEN** 某 agent 的 `plugins` 不含 `crm_tools`
- **THEN** `crm_tools__lookup` 不出现在暴露给该 agent 的工具 schema 列表中，不可被该 agent 调用

#### Scenario: 默认空 plugins 看不见任何插件工具
- **WHEN** 某 agent 未声明 `plugins`（默认空列表）
- **THEN** 任何 `{插件名}__{工具名}` 形式的插件工具都不出现在暴露给该 agent 的工具列表中

### Requirement: 插件名命名空间全局唯一

加载某插件前，平台 SHALL 校验其插件名在工具命名空间中全局唯一：插件名 MUST NOT 与已注册的 MCP server_id 或内置工具命名空间前缀冲突，两个插件之间的名字 MUST NOT 重复。命名冲突时，平台 MUST 跳过冲突插件并记录 warning，MUST NOT 改写或覆盖既有工具键，且 MUST NOT 中断其余插件加载。

#### Scenario: 插件名与已注册命名空间冲突被跳过
- **WHEN** 某插件名与一个已注册的 MCP server_id 相同
- **THEN** 该插件被跳过并记录 warning，既有同名命名空间的工具键不被改写

#### Scenario: 加载插件不改写既有工具键
- **WHEN** 加载一个插件（其 `__init__.py` 可能间接 import 了既有注册副作用模块）
- **THEN** 仅该插件自身的工具以 `{插件名}__{工具名}` 形式新增进注册表，既有内置/MCP 工具键不被改写或纳入命名空间化
