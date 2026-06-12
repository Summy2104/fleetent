## Context

Anthropic **Agent Skills** 标准协议把 SKILL.md frontmatter 限定为 6 个顶层字段:`name` / `description` / `license` / `compatibility` / `metadata` / `allowed-tools`。其中:
- `metadata` 是 **string→string** 映射(键值都是字符串),用于承载任何实现自有的扩展;官方建议用独特前缀(避免与其他实现 key 撞名)。
- `compatibility` 声明 skill 的兼容范围。
- `allowed-tools` 是工具名列表。

fleetent 当前(`src/fleetent/skills/registry.py`)用一批**非标顶层字段**承载扩展:`tags` / `platforms` / `version` / `enabled_by_default` / `enabled` / `disable_model_invocation` / `requires_tools` / `required_env_vars`。解析逻辑在 `_scan_dir`:`_parse_frontmatter` 出 dict 后,直接 `frontmatter.get("requires_tools")` 等取顶层键,经 `_as_str_list` / `_as_opt_str` / `_as_env_var_list` 归一化填进 `SkillEntry`。`required_env_vars` 当前用**嵌套对象列表**(`[{name, optional}]`)——这恰好违反标准 `metadata` 的 string-value 约束。

下游消费者只认 `SkillEntry` 的字段,不关心来源:
- `_disabled_reason`(catalog 资格谓词)读 `audit_blocked`/`disable_model_invocation`/`enabled`/`enabled_by_default`
- `_tools_available`(render-gate)读 `requires_tools`
- `skill_readiness` 读 `required_env_vars`
- `match` / `SkillIndex.match` 读 `enabled`/`enabled_by_default`/`audit_blocked`

因此本 change 的改动面被精确收敛为:**只改 `SkillEntry` 各字段从 frontmatter 哪里取值**,字段语义、缺省值、下游消费全部不动。

## Goals / Non-Goals

**Goals**
- frontmatter 解析对齐标准协议:fleetent 扩展的**标准权威位置**是 `metadata.fleetent-*`(string 值)。
- 识别并承载标准 `compatibility` 字段(不报"未知字段")。
- 标准 skill 导入 fleetent 能跑:未知 `metadata` 键 / 未识别 `fleetent-*` 键被忽略、不报错(优雅降级)。
- 不破坏任何现有 SKILL.md:旧顶层字段保留兼容读取;两处都在时标准位置优先。
- 内置 skill 迁移到标准 `metadata.fleetent-*` 形态,作为示范且验证等价。

**Non-Goals**
- 不实现 `requires-bins` 沙箱探测门控(耦合执行世界,归后续 change)。
- 不改 catalog 资格谓词 / render-gate / `skill_readiness` 的**语义**。
- 不动 `_inject_skill_provenance`(它注入 `source`/`proposal_id`/`applied_at`,是 reflection provenance、非 Agent-Skills 协议字段,正交)。
- 不删除旧顶层字段支持(兼容 shim 长期保留,本 change 不设退役时间表)。
- 不引入 `metadata` 内嵌套对象/数组(违反 string-value 约束)。

## Decisions

### D1: 扩展字段权威来源 = `metadata.fleetent-*`,旧顶层为回落
解析顺序对每个字段固定为:**`metadata.fleetent-<key>`(标准,优先) → 旧顶层 `<key>`(兼容回落) → 缺省**。

- 备选 A(只读 metadata,弃旧顶层):破坏所有现有 SKILL.md,违反"不破坏现有文件"硬约束。否决。
- 备选 B(只读旧顶层,metadata 仅作别名):无法让标准 skill 在 fleetent 跑(标准 skill 不写旧顶层)。否决。
- 备选 C(旧顶层优先、metadata 回落):与"对齐标准"目标相悖——标准位置应是权威。否决。
- **采纳:标准位置优先 + 旧顶层回落**——既对齐标准(新写法权威),又兼容存量(旧写法仍生效)。

### D2: `metadata` 值的 string 编码约定
`metadata` 严格 string→string,故 fleetent 扩展按以下编码:
- bool → `"true"` / `"false"`(大小写不敏感解析,非这两值时回落缺省并按未识别处理)。
- list[str] → 空格分隔字符串(`"run_code search_docs"`);空串 → 空列表。
- `required_env_vars` 的 `{name, optional}` → 空格分隔的变量名,**optional 用 `name?` 后缀**(`"API_KEY OPT?"` → `API_KEY` 必需、`OPT` optional)。

- 备选(JSON-in-string,如 `fleetent-required-env: '[{"name":"X"}]'`):值仍是 string 合法,但可读性差、与"用空格分隔列表"的协议惯例相悖,且把嵌套结构藏进字符串等于变相违反 string-value 精神。否决。
- 备选(metadata 内嵌套对象):直接违反 string-value 约束,且正是 openclaw 的反面教材。否决。
- **采纳:空格分隔 + `name?` 后缀**——纯 string、可读、无嵌套。

### D3: `compatibility` 只识别承载、不接运行时语义
`compatibility` 是标准字段,本 change 解析它、存进 `SkillEntry`(可选只读字段),使其成为"已知字段"而非被无视。**如何用它过滤/匹配不在本 change 范围**——避免本 change 越界改 catalog 语义。

- 备选(本 change 就实现 compatibility 过滤):扩大 blast radius、改 catalog 语义,违反 Non-Goals。否决。
- **采纳:识别 + 承载,运行时语义留给后续**。

### D4: 未知键优雅降级
解析时:`metadata` 中非 `fleetent-` 前缀键一律不读;`fleetent-` 前缀但不在已识别集合内的键一律不读。两者都**不报 parse 失败**(沿用 `_parse_frontmatter` 只在缺边界/YAML 错误/非映射时返回 None 的既有契约)。这样 fleetent 拿到别的实现的标准 skill(含它自己的 `metadata.*`)不炸。

### D5: 归一化 helper 复用 + 微扩展
`_as_str_list`(已有,处理 list/scalar)对**空格分隔 string** 需扩展:当值是带空格的单字符串时拆分。新增小 helper:
- `_as_bool_meta(str) -> bool | None`:`"true"`/`"false"` → bool,其余 → None(回落)。
- `_split_ws(str) -> list[str]`:空格分隔。
- env-var 归一化:从空格分隔 string 解析 `name` / `name?`(后缀 `?` = optional),产出与现有 `_as_env_var_list` 同形的 `[{name, optional}]`(下游 `skill_readiness` 零改动)。

## Risks / Trade-offs

- **双来源歧义**:同一字段标准位置与旧顶层都写且值不同 → 由 D1 明确"标准优先"消歧,并有专门 scenario 锁定。
- **string 编码误用**:作者把 `fleetent-enabled: "yes"` 写错 → 按 D2 回落缺省(视为未识别),不静默反转语义;`enabled` 缺省真 = 仍可见,安全侧。
- **`name?` 与合法变量名冲突**:env 变量名不含 `?`(POSIX 环境变量名仅 `[A-Za-z_][A-Za-z0-9_]*`),`?` 作 optional 标记无歧义。
- **内置 skill 迁移引入差异**:迁移即重写内置 SKILL.md frontmatter,用"迁移前后解析结果等价"测试兜底。
- **兼容 shim 长存**:旧顶层读取路径长期保留 = 解析逻辑略复杂,但这是"不破坏存量"的必要代价;后续可在独立 change 评估退役。

## Migration

- **现有用户 SKILL.md**:零改动。旧顶层字段继续被读取,行为不变。鼓励(非强制)迁移到 `metadata.fleetent-*`。
- **内置 skill**:本 change 将仓库内置 skill 的非标顶层字段迁移为 `metadata.fleetent-*` 标准形态;`required_env_vars` 的嵌套对象形态改为 `fleetent-required-env` 空格分隔 + `name?`。
- **无 DB / 无 schema 迁移**:frontmatter 是文件系统 SKILL.md,纯解析层改动。
- **无 re-export shim**:无模块迁移,`SkillEntry` 与 public 函数签名/行为不变(仅可能新增可选 `compatibility` 只读字段,带缺省,不破坏现有构造点)。

## Open Questions

- `fleetent-required-env` 是否需要支持除 optional 外的更多属性(如默认值)?当前只迁移 `optional`(现有唯一支持的属性);更多属性等真实需求出现再扩,避免过早把编码搞复杂。
- 旧顶层字段的退役时间表?本 change 不定,留作后续独立评估(避免与"对齐标准"耦合)。
