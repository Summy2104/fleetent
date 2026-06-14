## Context

`DockerBackend`（`integrations/sandbox/backends/docker.py`）用三个静态方法装配 bind mount，均为位置式 `-v`：
- `_workspace_flags` → `-v {ws}:{/workspace}`（`ws = workspaces_dir()/_name_key(scope_key)`，已清洗，无冒号）
- `_exchange_flags` → `-v {view}:{/exchange}:ro`（`view = artifact_exchange.view_dir(scope_key)` = `.views/<scope_key 原始值>`，**含冒号**）
- `_skill_mount_flags` → `-v {host_src}:{/workspace/skills}[:ro]`

session 作用域 `scope_key = session_id`（`slack:dm:U…:<ts>`）。`docker -v` 按冒号切字段，`_exchange_flags` 的源路径含冒号 → `docker: invalid spec … too many colons` → `docker run` 失败。实测 `docker run --mount type=bind,source=<冒号路径>,target=/exchange,readonly …` 成功。

## Goals / Non-Goals

**Goals:**
- 让 `scope_key`/`session_id` 含 `:` 时容器仍能创建（修复 run_code/沙箱文件工具在 session 作用域下的可用性）。
- 行为等价：挂载点、只读语义、空不挂载不变。

**Non-Goals:**
- 不改 `scope_key`/视图目录命名/`artifact_exchange` 布局（修在 mount 语法层）。
- 不改 workspace 的 `_name_key` 清洗（保留；它本就无冒号，但一并转 `--mount` 以统一+防御）。
- 不引入新挂载或能力。

## Decisions

### D1：用 `--mount type=bind` 取代 `-v`
三个 flag 构造器统一改为 `--mount type=bind,source=<src>,target=<dst>[,readonly]`：
- workspace：`type=bind,source={ws},target=/workspace`
- exchange：`type=bind,source={view},target=/exchange,readonly`
- skill：`type=bind,source={host_src},target=/workspace/skills[,readonly]`
- None/空 → `[]`（不变）。
- **为何 `--mount` 而非"清洗 view 目录名"**：`--mount` 是 key=value、冒号安全，修复点局部（仅 docker 后端 2~3 个函数），不动 `.views` 目录布局与 `artifact_exchange`/resolve/link 的多处引用；而清洗 view 目录名需在 `view_dir`/`_link_into_view`/resolve 等多处一致改动，面更大、风险更高。`--mount` 还顺带防御源路径含任意特殊字符。
- **为何连 workspace/skill 一起改**：保持装配语法一致、消除同类隐患（未来若 workspace 也用未清洗 key 或 skill 路径含特殊字符不会再炸）；行为等价、零风险。

### D2：`--mount` 的字段顺序与只读
`type=bind` 在前;`source=`/`target=` 用完整宿主/容器路径(源含冒号由 key=value 边界保护,docker 只在逗号处分字段);只读用 `readonly`(等价 `ro`)。源路径理论上含逗号会破坏 key=value——但宿主路径由 paths/scope_key 派生、不含逗号(scope_key 字符集为 `slack:dm:<id>:<ts>` 类),非现实风险;如需极致稳健可改 `csv` 转义,YAGNI。

## Risks / Trade-offs

- [源路径含逗号会破坏 `--mount` 的 key=value 解析] → 现实中宿主路径与 scope_key 不含逗号;若未来引入,需 CSV 转义。当前不处理(YAGNI),但设计记录在案。
- [行为差异被测试漏检] → 单测改为断言 `--mount` 形式 + 新增"scope_key 含冒号"回归用例(纯字符串装配,断言不再含裸 `-v` 冒号路径);docker 真机断言留 docker-gated。
- [仅改 docker 后端,microsandbox 后端] → microsandbox 不用 docker `-v`/`--mount`,不受影响;本修复限 `DockerBackend`。
