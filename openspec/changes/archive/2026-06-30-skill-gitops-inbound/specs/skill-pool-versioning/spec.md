## ADDED Requirements

### Requirement: 池可作为外部 git 的本地镜像

当配置外部 git 源（见 `skill-git-sync`）时，公共 skill 池 SHALL 作为该外部仓库指定分支的本地只读镜像：池内容经 fetch + reset --hard 与外部分支对齐，外部仓库为权威。此模式下 per-skill 版本仍 = 子树最后 commit，但 commit 来自外部同步（及内置 seed 恢复），而非平台 UI 写入——平台 UI 的内容写路径在此模式下关闭（见 `skill-admin-api`）。未配置外部源时，既有「平台内部自管 git 池」语义（创建/编辑/上传/归档各产生归因 commit）不变。

#### Scenario: 外部源启用时池为镜像
- **WHEN** 配置并启用了外部 git 源
- **THEN** 池内容与外部分支对齐，skill 版本取自外部同步的 commit，平台 UI 不再写入池内容

#### Scenario: 未配置外部源时保持自管
- **WHEN** 未配置外部 git 源
- **THEN** 池仍为平台内部自管 git，既有写路径与版本语义不变
