# skill-bundle-distribution Specification

## Purpose
TBD - created by archiving change tenant-first-layout. Update Purpose after archive.
## Requirements
### Requirement: Platform exposes immutable skill bundles for node deployment

系统 SHALL 允许 platform 从公共 skill 池为某个 skill 的某个版本生成 immutable bundle，并通过 node 授权 API 提供下载。bundle MUST 表示一个完整 skill 目录，包含 `SKILL.md` 与其子文件/子目录，MUST 排除 `.git` 与其它 VCS 内部目录。

#### Scenario: Node downloads a versioned skill bundle
- **WHEN** node 按 desired-state 中的 bundle URL 请求 skill `incident-review` 的版本 `abc123`
- **THEN** platform 返回该版本的压缩包
- **AND** 压缩包内容解开后等价于公共 skill 池中该 skill 版本的目录树

#### Scenario: Bundle is immutable by version
- **WHEN** 同一 `skill_name + base_version` 的 bundle 已生成
- **THEN** 后续请求 MUST 返回相同内容
- **AND** platform MUST NOT 原地改写该 bundle

### Requirement: Bundle cache is generated lazily and safely

platform SHALL 维护本地 bundle cache。Bundle API 收到请求时，若 cache 命中则直接返回；若 cache miss，则从公共 skill 池对应目录打包到临时文件，完成路径校验与 hash 校验后原子移动到 cache。

#### Scenario: Cache miss generates bundle once
- **WHEN** node 首次请求某 skill 版本 bundle 且 cache 不存在
- **THEN** platform 从公共 skill 池打包该目录
- **AND** 写入临时文件后原子发布到 bundle cache
- **AND** 返回该 bundle

#### Scenario: Cache hit avoids repackaging
- **WHEN** node 再次请求已缓存的同一 skill 版本 bundle
- **THEN** platform 直接返回缓存文件
- **AND** 不重新扫描或打包公共 skill 目录

### Requirement: Bundle packaging and extraction metadata are safe

platform 生成 bundle 时 MUST 拒绝绝对路径、`..` 路径、`.git` 目录、symlink/hardlink 逃逸与超过大小上限的内容。bundle metadata SHALL 包含内容 hash 和压缩包 hash，供 node 下载后校验。

#### Scenario: Unsafe path is rejected
- **WHEN** 公共 skill 目录中存在会逃逸目标目录的路径或链接
- **THEN** platform 拒绝生成 bundle
- **AND** Bundle API 不返回该不安全内容

#### Scenario: Bundle metadata includes verification hashes
- **WHEN** platform 在 desired-state 中引用某 bundle
- **THEN** manifest 包含 `base_version` 与 `bundle_sha256`
- **AND** node 可用这些值校验下载内容

