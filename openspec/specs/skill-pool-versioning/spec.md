# skill-pool-versioning Specification

## Purpose
公共 skill 池的 git-on-disk 版本化：池目录作为 git 仓库管理，每次池写路径产生可归因 commit，per-skill 版本精确到子树最后 commit，写操作串行化保证仓库完整性，并暴露只读历史与 diff 接口。

## Requirements

### Requirement: 公共池是 git-on-disk 仓库

公共 skill 池目录 SHALL 是一个 git 仓库。平台首次使用时 SHALL 幂等初始化（已是 git 仓则跳过）。存量非 git 池在升级时 SHALL `git init` 并把当前全部内容提交为初始 commit（author=`system`）。git 操作 SHALL 经纯 Python 实现，不依赖宿主 `git` 二进制。

#### Scenario: 存量池升级时初始化为 git 仓
- **WHEN** 平台在一个非 git 仓的池目录上首次运行升级后的版本化逻辑
- **THEN** 池目录成为 git 仓库，且当前内容被提交为一个初始 commit

#### Scenario: 已是 git 仓不重复初始化
- **WHEN** 池目录已是 git 仓库
- **THEN** 不重复 `git init`、不产生多余的初始 commit

### Requirement: 每次池变更提交一次可归因 commit

池的每次写路径（create / edit / upload / archive、builtin seed）SHALL 在文件改完后提交一次 commit，commit 信息 SHALL 含操作类型与目标 skill，author SHALL 为操作者（admin 用户）或 `system`（seed / init）。builtin seed SHALL 仅在内容实际变化时提交（不产空 commit）。

#### Scenario: 编辑池 skill 产生归因 commit
- **WHEN** admin 经写路径编辑池中 skill "crm-ops"
- **THEN** 池 git 仓新增一个 commit，记录该编辑与操作者

#### Scenario: 无变化的 seed 不产空 commit
- **WHEN** builtin seed 运行但池内容未变化
- **THEN** 不产生新的 commit

### Requirement: per-skill 版本 = 子树最后 commit

某 skill 的版本标识 SHALL 为**最后触及该 skill 子目录的 commit** 标识（per-skill，单仓内精确到子树），而非全局仓库 head。改动一个 skill SHALL NOT 改变其它未被触及 skill 的版本标识。

#### Scenario: 改 A 不动 B 的版本
- **WHEN** 池中 skill "A" 被编辑提交，"B" 未被触及
- **THEN** "A" 的版本标识前移到新 commit，"B" 的版本标识不变

### Requirement: 池写串行化

池 git 写操作（commit / init）SHALL 经跨进程串行化（单机文件锁），避免并发写损坏仓库。只读操作（history / diff）SHALL NOT 被写锁阻塞。

#### Scenario: 并发写串行化
- **WHEN** 两个写路径几乎同时提交池变更
- **THEN** 提交被串行化，池仓不损坏，两次变更各成一个 commit

### Requirement: 只读版本历史与 diff 接口

平台 SHALL 暴露只读接口返回某 skill 的版本历史（`GET /admin/skills/{name}/versions`）与某版本相对前一版本的 diff（`GET /admin/skills/{name}/versions/{ref}/diff`）。diff SHALL 针对文本内容；超出合理大小时 SHALL 降级为「仅列变更文件名」并告警，SHALL NOT 静默截断。

#### Scenario: 列出版本历史
- **WHEN** admin 请求 skill "crm-ops" 的版本历史
- **THEN** 返回按时间倒序的 commit 列表（含标识、时间、author、信息）

#### Scenario: 查看某版本 diff
- **WHEN** admin 请求 skill "crm-ops" 某版本的 diff
- **THEN** 返回该版本相对前一版本的文本 diff

#### Scenario: 超大 diff 降级不静默
- **WHEN** 某版本 diff 超出合理大小
- **THEN** 响应降级为变更文件名清单并带告警标记，而非被静默截断

### Requirement: 池可作为外部 git 的本地镜像

当配置外部 git 源（见 `skill-git-sync`）时，公共 skill 池 SHALL 作为该外部仓库指定分支的本地只读镜像：池内容经 fetch + reset --hard 与外部分支对齐，外部仓库为权威。此模式下 per-skill 版本仍 = 子树最后 commit，但 commit 来自外部同步（及内置 seed 恢复），而非平台 UI 写入——平台 UI 的内容写路径在此模式下关闭（见 `skill-admin-api`）。

若外部源额外配置了 `skills_subdir`（子目录作为 skill 扫描根，见 `skill-git-sync`），per-skill 版本解析的 git 树路径 SHALL 为 `<skills_subdir>/<name>` 而非 `<name>`：查询版本历史、diff、bundle 内容时 SHALL 以 git 仓根打开仓库、以 `<skills_subdir>/<name>` 定位子树，对外暴露的仍是干净的 skill 名（不带 `skills_subdir` 前缀）。未配置 `skills_subdir` 时，树路径退化为 `<name>`，与本 change 之前完全一致。

未配置外部源时，既有「平台内部自管 git 池」语义（创建/编辑/上传/归档各产生归因 commit）不变。

#### Scenario: 外部源启用时池为镜像
- **WHEN** 配置并启用了外部 git 源
- **THEN** 池内容与外部分支对齐，skill 版本取自外部同步的 commit，平台 UI 不再写入池内容

#### Scenario: 配置 skills_subdir 时版本按子目录树路径解析
- **WHEN** 外部源配置了 `skills_subdir="skills"`，查询 skill "clean" 的版本或 diff
- **THEN** 平台以 git 仓根打开仓库、以树路径 `skills/clean` 定位子树取得版本/diff，响应中的 skill 名仍为干净的 "clean"

#### Scenario: 未配置 skills_subdir 时树路径不变
- **WHEN** 外部源未配置 `skills_subdir`
- **THEN** per-skill 版本解析的树路径仍为 `<name>`，行为与本 change 之前一致

#### Scenario: 未配置外部源时保持自管
- **WHEN** 未配置外部 git 源
- **THEN** 池仍为平台内部自管 git，既有写路径与版本语义不变
