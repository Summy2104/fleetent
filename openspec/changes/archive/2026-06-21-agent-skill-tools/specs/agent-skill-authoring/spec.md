## ADDED Requirements

### Requirement: skill_manage 工具提供用户显式驱动的 skill 自创/修订

系统 MUST 提供 agent 侧模型可调用工具 `skill_manage(action, name, ...)`，action MUST 覆盖 `create`、`patch`、`edit`、`delete`、`write_file`、`remove_file` 六种。`create` MUST 用给定 content 新建一个 skill（SKILL.md）；`edit` MUST 整体重写已存在 skill 的 SKILL.md；`patch` MUST 对已存在 skill 的 SKILL.md（或指定文件）做 old_string→new_string 的定向替换；`delete` MUST 删除一个已存在 skill；`write_file` MUST 在 skill 目录下新增/覆盖一个支撑文件；`remove_file` MUST 删除一个支撑文件。任一 action 操作不存在的 skill（除 create）或 create 一个已存在的 skill 时 MUST 返回明确错误文本而非抛出。写成功后 MUST 触发 registry 热重载，使新内容立即对索引可见。

#### Scenario: create 新建 skill
- **WHEN** 经审批后调用 `skill_manage(action="create", name="my-skill", content="<合法 SKILL.md>")`
- **THEN** 在 per-agent skills 目录下创建 `my-skill/SKILL.md`，并热重载使其进入索引

#### Scenario: patch 定向替换
- **WHEN** 经审批后对已存在 skill 调用 `skill_manage(action="patch", name="my-skill", old_string="A", new_string="B")`
- **THEN** 该 skill 的 SKILL.md 中 "A" 被替换为 "B" 并热重载

#### Scenario: delete 删除 skill
- **WHEN** 经审批后调用 `skill_manage(action="delete", name="my-skill")`
- **THEN** 该 skill 目录被移除并热重载，使其从索引消失

#### Scenario: 对不存在的 skill 操作返回错误
- **WHEN** 调用 `skill_manage(action="edit", name="no-such-skill", content=...)`
- **THEN** 返回说明该 skill 不存在的错误文本，不中断 agent 循环

#### Scenario: create 已存在的 skill 返回错误
- **WHEN** 对一个已存在的 skill 调用 `skill_manage(action="create", ...)`
- **THEN** 返回说明该 skill 已存在的错误文本，不覆盖原内容

### Requirement: skill_manage 的每次写操作强制走审批门

`skill_manage` 的所有写 action MUST 经 governance approval gate，由审批确定性保证「用户显式」——即使模型未经用户要求自行调用，写操作 MUST 在用户批准前不生效。其风险定级 MUST 不低于强制审批档（medium 即触发审批），并经中心 `approval_policy` 裁定。审批被拒绝或未批准时 MUST NOT 改动任何 skill 文件。

#### Scenario: 写操作需审批
- **WHEN** 模型调用 `skill_manage(action="create", ...)`
- **THEN** 该调用被定级为需审批，进入审批流程，未批准前不写入任何文件

#### Scenario: 审批拒绝不改动文件
- **WHEN** 一次 `skill_manage` 写操作被用户拒绝
- **THEN** 目标 skill 文件保持原状，无任何创建/修改/删除

### Requirement: skill_manage 仅写 per-agent 目录且 builtin 只读

`skill_manage` 的写/改/删 MUST 仅作用于当前 agent 的有效用户 skills 目录；对来源为 builtin/bundled 的 skill（索引项 `builtin` 为真）的 edit/patch/delete/write_file/remove_file MUST 被拒绝并返回明确错误文本。该工具 MUST 纯 agent 侧操作文件，MUST NOT 写入任何 platform 管理表、MUST NOT `import fleetent.platform.*`，以保证「无 platform、platform 表不存在」环境下仍可运行。

#### Scenario: 拒绝改动 builtin skill
- **WHEN** 对一个索引来源为 builtin 的 skill 调用 `skill_manage(action="edit", ...)`
- **THEN** 返回说明 builtin skill 只读的错误文本，不修改其内容

#### Scenario: 写入落在 per-agent 目录
- **WHEN** 经审批 create 一个新 skill
- **THEN** 新 skill 写入该 agent 的用户 skills 根目录下，而非包内 builtin 目录

#### Scenario: 不触碰 platform 表
- **WHEN** 在 platform 管理表不存在的环境下执行任一 `skill_manage` 写操作
- **THEN** 操作仅读写 skill 文件并成功/失败于文件层，不因缺少 platform 表而报错

### Requirement: skill_manage 写入时执行静态注入审计与路径防护

写入 SKILL.md 内容的 action（create/edit，以及改到 SKILL.md 的 patch）MUST 在持久化前对**最终 SKILL.md 全文**运行与 scan 路径一致的静态注入审计；命中任一 `severe` 模式时 MUST 拒绝持久化并返回明确错误文本（已有内容保持原状）。所有以相对路径定位文件的 action（write_file/remove_file/patch 的文件参数）MUST 将路径解析限定在该 skill 目录之内，解析后越界的路径 MUST 被拒绝。

#### Scenario: severe 注入内容拒绝写入
- **WHEN** create/edit 的 content 命中一条 `severe` 注入模式
- **THEN** 返回因安全审计被拒的错误文本，不持久化该内容

#### Scenario: patch 后全文重审计
- **WHEN** 一次 patch 使 SKILL.md 最终全文命中 `severe` 模式
- **THEN** 该 patch 不被持久化，skill 保持 patch 前状态

#### Scenario: write_file 路径遍历被拒绝
- **WHEN** `skill_manage(action="write_file", file_path="../../evil", ...)`
- **THEN** 返回路径越界错误，不在 skill 目录之外写入任何文件

### Requirement: skill_manage 默认关闭，仅显式开启的 agent 可见

`skill_manage` 工具 MUST 受 per-agent 配置 `skill_authoring_enabled` 门控，默认 `false`。当某 agent 未开启时，`skill_manage` 的工具 schema MUST NOT 进入该 agent 暴露给模型的工具集（模型看不到该工具）。仅当 agent 显式设 `skill_authoring_enabled: true` 时，该工具 schema 才对其可见。

#### Scenario: 默认关闭时工具不可见
- **WHEN** 一个未设置 `skill_authoring_enabled`（默认 false）的 agent 组装工具 schema
- **THEN** `skill_manage` 不出现在该 agent 的工具 schema 列表中

#### Scenario: 显式开启后工具可见
- **WHEN** 一个设置了 `skill_authoring_enabled: true` 的 agent 组装工具 schema
- **THEN** `skill_manage` 出现在该 agent 的工具 schema 列表中

### Requirement: create 写入 provenance 来源标记

`skill_manage` 的 create action MUST 在新建 skill 的 SKILL.md frontmatter 写入一行来源标记（标明该 skill 由 agent 工具创建）与创建时间戳。时间戳 MUST 由工具层注入（registry 不读系统时钟以保持可测）。成功的写操作 MUST 记录一条 agent 侧 observability trace（与既有 `skill_hit` 同侧），MUST NOT 写 platform store；本变更 MUST NOT 引入 usage 计数 sidecar 或自动 curator。

#### Scenario: create 注入来源标记
- **WHEN** 经审批 create 一个新 skill
- **THEN** 该 skill 的 SKILL.md frontmatter 含来源标记（agent 工具创建）与时间戳

#### Scenario: 写操作记录 agent 侧 trace
- **WHEN** 一次 `skill_manage` 写操作成功
- **THEN** 记录一条 agent 侧 observability trace，不写任何 platform 表
