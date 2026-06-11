## Why

fleetent 的 SKILL.md frontmatter 自行扩展了一批顶层字段(`requires_tools` / `required_env_vars` / `enabled_by_default` / `enabled` / `disable_model_invocation` / `tags` / `platforms` / `version`),与 Anthropic **Agent Skills 标准协议**不兼容。标准协议只认 6 个顶层字段:`name` / `description` / `license` / `compatibility` / `metadata` / `allowed-tools`;一切非标扩展都必须放进 `metadata` 命名空间,且 `metadata` 是严格的 **string→string** 映射(值必须是字符串,空格分隔列表用字符串表达),并建议用独特前缀避免与其他实现的 key 撞名。

后果是双向的:
1. **拿别人的标准 skill 进 fleetent 跑不顺**——标准 skill 把扩展放在 `metadata.*`,fleetent 现在不读 `metadata`,这些信息(依赖工具、所需 env、可见性)被丢弃;`compatibility` 字段也未被识别。
2. **fleetent 的 skill 拿到别的标准实现里会触发未知顶层字段**——非标顶层字段在严格校验的实现里可能报错或被特殊对待。

本 change 让 fleetent frontmatter 解析**对齐标准协议**:扩展字段一律以 `metadata.fleetent-*`(string 值)为权威来源,识别标准 `compatibility` 字段,同时**保留旧顶层字段的兼容读取**(shim 式过渡,不破坏任何现有 SKILL.md 文件),并为内置 skill 做存量迁移。目标:标准 skill 导入 fleetent 能跑,fleetent skill 拿到别的实现不炸(未知 `metadata` 被忽略 = 优雅降级)。

本 change **独立**,与"沙箱优先执行"批次的其余 change **无耦合、无依赖**。

## What Changes

- **`metadata` 命名空间承载扩展(新权威来源)**:frontmatter 解析读取标准 `metadata` 映射;fleetent 自有扩展统一为 `metadata.fleetent-*`、值为 **string**(布尔用 `"true"`/`"false"`,列表用空格分隔字符串)。已识别键:
  - `fleetent-requires-tools`(空格分隔工具名)
  - `fleetent-required-env`(空格分隔变量名;`optional` 语义用 `name?` 后缀表达,而非嵌套对象)
  - `fleetent-enabled-by-default`(`"true"`/`"false"`)
  - `fleetent-enabled`(`"true"`/`"false"`)
  - `fleetent-disable-model-invocation`(`"true"`/`"false"`)
  - `fleetent-tags` / `fleetent-platforms`(空格分隔)/ `fleetent-version`(string)
- **标准 `compatibility` 字段识别**:解析顶层 `compatibility`(标准协议字段),作为已知字段承载(不报"未知字段"风险);具体如何影响匹配不在本 change 的运行时改动范围内,本 change 只做"识别 + 承载"。
- **旧顶层字段保留兼容读取(shim 式过渡)**:旧顶层 `requires_tools` / `required_env_vars` / `enabled_by_default` / `enabled` / `disable_model_invocation`(及 `tags`/`platforms`/`version`)仍被读取并填入 `SkillEntry`,**不破坏现有文件**。当 `metadata.fleetent-*` 与旧顶层同时存在时,以 **`metadata.fleetent-*` 为权威**(标准位置优先),旧顶层为回落。`SkillEntry` 字段语义与缺省值保持不变,下游(catalog 过滤、`skill_readiness`、`requires_tools` render-gate)零改动。
- **未知 `metadata` 优雅降级**:`metadata` 中非 `fleetent-` 前缀的键、以及未识别的 `fleetent-*` 键一律被忽略、不报错——保证 fleetent 拿到别的实现的标准 skill 不炸。
- **存量内置 skill 迁移**:把仓库内置 skill 的非标顶层字段迁移进 `metadata.fleetent-*`(标准形态),验证迁移后解析结果与迁移前一致。
- **本 change 明确不做**:不实现 `requires-bins` 沙箱探测门控(会耦合执行世界,归后续);不改 catalog 过滤 / 资格谓词 / `skill_readiness` 的语义;不动 `_inject_skill_provenance`(reflection 注入 `source`/`proposal_id`/`applied_at` 的非 frontmatter-协议字段,正交);不在 `metadata` 内嵌套对象(违反 string-value 约束,亦不学 openclaw 的嵌套对象做法)。

## Capabilities

### New Capabilities

无。本 change 只修改既有 `skill-yaml-frontmatter` 能力契约,不新增 capability。

### Modified Capabilities

- `skill-yaml-frontmatter`: frontmatter 解析对齐 Agent Skills 标准协议——扩展字段以 `metadata.fleetent-*`(string 值)为权威承载、识别标准 `compatibility`、保留旧顶层字段兼容读取(标准位置优先于旧顶层)、未知 `metadata` 优雅降级。

## Impact

- **代码**:`src/fleetent/skills/registry.py`(`_scan_dir` 的 `SkillEntry` 构造改为"`metadata.fleetent-*` 优先 → 旧顶层回落 → 缺省";新增 `metadata` 与 `compatibility` 解析 + `metadata.fleetent-*` 归一化 helper:string→bool、空格分隔 string→list、`name?` → env-var optional 语义);`SkillEntry` 可加只读字段承载 `compatibility`(可选,不破坏现有构造)。内置 skill 的 `SKILL.md` frontmatter 文本迁移到 `metadata.fleetent-*`。
- **复用而非新建**:不新增运行时机制——catalog 资格谓词(`_disabled_reason`)、render-gate(`_tools_available`)、`skill_readiness` 对 `SkillEntry` 字段的消费完全不变;本 change 只改"`SkillEntry` 这些字段从 frontmatter 哪里取值"。
- **模块边界声明**:
  - owning package:`skills`(`skills/registry.py` 的 frontmatter 解析)。
  - public API surface:`skills.registry.SkillEntry`(dataclass;字段语义与缺省不变,可新增可选 `compatibility` 只读字段)、`scan` / `reload` / `available_skills_prompt` / `skill_readiness` / `match` / `load`(签名与行为不变);`_parse_frontmatter` / `_scan_dir` / 新增归一化 helper 为 internal。
  - owned tables:无(frontmatter 为文件系统 SKILL.md,不落 DB)。
  - config namespace:无新增(skills 目录解析复用 `FLEETENT_SKILLS_DIR`,本 change 不动)。
  - cross-module dependencies:`runtime/loop.py` 经 `skills.registry` public API 消费 `requires_tools`/catalog(行为不变);`skills` MUST NOT `import fleetent.platform.*`,保持 agent/platform 单向解耦;agent 须仍能在无 platform、platform 表不存在环境下 `fleetent agent run`。
  - migration / shim plan:旧顶层字段保留为兼容回落读取(代码内 shim,不删除旧字段支持),现有 SKILL.md 文件零改动即可继续工作;内置 skill 迁移到标准 `metadata.fleetent-*` 形态做示范。无 re-export shim 需求(无模块迁移)。
- **测试**:unit(标准 `metadata.fleetent-*` 被解析进 `SkillEntry`;`metadata` 优先于旧顶层;旧顶层在无 metadata 时仍生效;未知 `metadata` 键被忽略不报错;`compatibility` 被识别承载;string→bool / 空格分隔 string→list / `name?` env optional 归一化;迁移后内置 skill 解析结果等价)。本 change 无需 integration(纯 frontmatter 解析逻辑,不触 DB/FastAPI/store 协作)。
- **依赖**:无(独立 change)。基于当前 main 的 `skill-yaml-frontmatter` / `skill-env-var` / `skill-disable-mechanism` 既有契约。
