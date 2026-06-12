# sandbox-workspace-root Specification

## Purpose
TBD - created by archiving change sandbox-execution-world. Update Purpose after archive.
## Requirements
### Requirement: 模型只见单根 /workspace 坐标系

面向模型暴露的执行与文件世界 SHALL 收敛为单一根 `/workspace`。模型 MUST 以 workspace 相对路径表达文件位置(如 `uploads/a.png`、`generated/x.png`、`skills/<name>/SKILL.md`),物理解析交由后端;模型 MUST NOT 被要求理解或拼接宿主绝对路径来定位会话文件、上传、生成产物或 skills。涉及容器内执行的工具指引 MUST 一致地表述「你处在 /workspace 这个单根世界」,使模型不再面对宿主/容器双坐标系。

#### Scenario: 工具路径输入按 workspace 相对解析
- **WHEN** 模型对任一文件类工具传入相对路径(如 `sub/a.txt`)
- **THEN** 该路径相对 `/workspace` 解析,模型无需提供宿主绝对路径

#### Scenario: 越界绝对路径被拒
- **WHEN** 模型传入 workspace 之外的绝对路径(如 `/etc/passwd` 或 `../../etc/passwd`)
- **THEN** 路径被拒绝并返回明确越界错误,不读写任何 workspace 外文件

### Requirement: 相对路径在容器与降级模式下解析到同一物理文件

对**同一 workspace 相对路径**,容器模式(经 bind-mount 的 `/workspace`)与无-docker 降级模式(宿主 workspace 目录 + normpath 围栏)SHALL 解析到**同一个物理文件**。任一模式写入某相对路径后,另一模式按同一相对路径 MUST 读到该写入结果(相对路径不变式)。该不变式 MUST 覆盖文件工具、`generate_image` 产物、入站上传等所有以 workspace 相对引用流转的产物。

#### Scenario: 容器写、降级读同一文件
- **WHEN** 容器模式下经 `/workspace/data.txt` 写入内容,随后部署降级为无-docker(宿主围栏)并按相对路径 `data.txt` 读取
- **THEN** 读到容器模式写入的同一内容(同一宿主 workspace 物理文件)

#### Scenario: 降级写、容器读同一文件
- **WHEN** 降级模式下按相对路径 `out/r.txt` 写入,随后 docker 恢复、容器按 `/workspace/out/r.txt` 读取
- **THEN** 读到降级模式写入的同一内容

#### Scenario: 生成产物以相对引用跨模式可读
- **WHEN** `generate_image` 在某模式下产出 `generated/<name>.png` 相对引用,另一模式按该相对引用读取
- **THEN** 两模式解析到同一物理图片文件

### Requirement: 降级态须为 skills 单独供给

当沙箱降级为 OFF(docker 不可用或 mode=off)、skills 目录无法经容器 bind-mount 进入 `/workspace/skills` 时,系统 SHALL 仍为 skill 脚本提供一个**真实可达**的 skills 根:或把 skills 物化(复制)到宿主 workspace 下的 `skills/`,或把注入的 `SKILLS_DIR` 改指向宿主上真实存在的 skills 目录。系统 MUST NOT 在 OFF 态把 `SKILLS_DIR` 指向一个容器内才存在、宿主上不存在的路径,导致 skill 脚本找不到目录。

#### Scenario: OFF 态 SKILLS_DIR 指向真实目录
- **WHEN** 沙箱为 OFF,skill 脚本经降级执行面运行并读取 `$SKILLS_DIR`
- **THEN** `$SKILLS_DIR` 指向宿主上真实存在、脚本可访问的 skills 根(物化目录或真实宿主 skills 目录)

#### Scenario: OFF 态脚本能按 SKILLS_DIR 找到 skill 资源
- **WHEN** 某 skill 在其目录内带有同目录资源文件,沙箱为 OFF,脚本按 `$SKILLS_DIR/<name>/<资源>` 访问
- **THEN** 该资源可被读到,不因降级而 `FileNotFoundError`

