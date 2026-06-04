## Context

fleetent 是纯 Python（>=3.12）+ FastAPI 项目，用 uv 管理依赖（`uv.lock`），schema lifecycle 归 Alembic（`alembic.ini` + `migrations/`），三个 console-script 入口定义在 `pyproject.toml`：`fleetent` / `fleetent-admin` / `fleetent-tui`。现有部署资产有两类：容器路径（`Dockerfile` + `docker-compose.yml`，面向 on-prem 生产）和升级脚本（`scripts/upgrade.py`，面向已安装实例的 backup+migrate）。缺口是**从干净环境到可运行**的 bootstrap。

review 确定的目标形态：**全局可用、与工作目录解耦**的 `fleetent` 命令——用户在任意目录敲 `fleetent`，状态固定在 `~/.fleetent`。这要求 config/data 路径不再相对 CWD，由前置 change `configurable-data-home` 引入的 `FLEETENT_HOME` 解析提供支撑。本 change 在其之上落地安装器。

参考蓝本是 NousResearch/hermes-agent 的 `scripts/install.sh`，借用其工程实践，但**大幅收窄范围**（不做 Windows 原生/Termux），并用 uv 原生能力替代 hermes 的手写 shim。

## Goals / Non-Goals

**Goals:**
- 单条命令从干净 Linux/macOS/WSL2 环境 bootstrap 出**全局可用、与 CWD 解耦**的 fleetent。
- 幂等可重入：重复运行只补缺失项，绝不破坏 `~/.fleetent` 下已有 `.env`/`config`/数据库。
- 借用 hermes 的稳健实践：env 净化、`set -e`、多地探测 uv、失败给可复现命令、非交互 flag、PATH 提示。
- 与 Docker 交付互补且边界清晰：install.sh = 开发者/单机体验；Docker = on-prem 生产。

**Non-Goals:**
- 不支持 Windows 原生 / Termux / Android（hermes 的大半复杂度来自此，本 change 明确排除；WSL2 走 Linux 路径）。
- 不替代 Docker 生产部署；不处理 sandbox 的 Docker 安装（仅预检告警）。
- 不引入新运行时依赖；不新增配置项或 schema。
- 不做 systemd service 注册、不自动启动服务（留给后续 change 或 operator 手动）。
- 不实现 `FLEETENT_HOME` 路径解析本身（属前置 change `configurable-data-home`）。

## Decisions

**D1：用 `uv tool install` 安装全局命令，不手写 shim。**
`uv tool install`（uv 原生）把 console-script 入口装进隔离环境并链接到 `~/.local/bin`，三入口在任意目录可调用，`uv tool upgrade fleetent` 免费拿到升级路径。这比 hermes 的手写 shim（symlink 自递归坑 #21454、需自管 PATH）干净得多。可行的前提正是前置 change——`uv tool` 隔离了包但 app 仍按 `FLEETENT_HOME` 找 config/data，故全局调用才不会找不到状态。
- 备选：`uv sync` + 手写 shim（C2）。弃因：仅在"config/data 跟随仓库副本"模型下成立，与本次"解耦"目标冲突。
- 备选：`uv sync` 留在仓库 + `uv run`。弃因：非全局、绑 CWD，不满足 review 结论。

**D2：状态目录固定 `~/.fleetent`，经 `FLEETENT_HOME` 注入。**
安装器写 `FLEETENT_HOME=~/.fleetent` 到用户 shell rc（幂等：已存在则不重复写），并在本次进程内 export 以便后续 `alembic`/模板步骤命中。`--dir PATH` 覆盖默认。config/data/db 全在此目录下，备份/迁移只搬一个目录。

**D3：数据库初始化复用 Alembic（`alembic upgrade head`），不自建建表逻辑。**
严格遵守 CLAUDE.md「schema lifecycle 归 Alembic」「禁止扩散 SQLite 细节」。针对 `FLEETENT_HOME/data` 运行，`alembic upgrade head` 天然幂等。
- 备选：调用某 `_init_db()`。弃因：CLAUDE.md 明确禁止复制建表模式。

**D4：配置模板拷贝采用「存在即跳过」语义。**
`[ -f $FLEETENT_HOME/.env ] || cp .env.example ...`，`config/*.yaml` 同理。保证幂等且不毁 operator 已填好的密钥。

**D5：Docker 仅预检告警，不阻断。**
sandbox 依赖宿主 Docker 是既有事实，但安装器不应强制 Docker——许多开发场景用不到沙箱。`command -v docker` 失败时打印告警继续（显式 `|| true` 避免被 `set -e` 误杀）。

**D6：函数化编排，main() 串联，结尾分流支持 flag。**
照 hermes 结构：顶部 env 净化 + 颜色/日志 helper + arg 解析 → 一组单一职责函数 → `main()` 顺序调用：`detect_os → ensure_uv → check_python → install_tool → setup_home_env → copy_config_templates → init_db → precheck_docker → print_success`。各步受 flag 短路。

**D7：可测试性优先做无副作用的契约点，测试入 `tests/integration/`。**
bash 脚本的 spec 可测场景（`--help` 退出 0、未知 flag 非零退出、env 净化、幂等、缺 Docker 不阻断、`FLEETENT_HOME` 写入）通过 `tests/integration/test_install_script.py` 以 bash 调用 + 临时 HOME/目录隔离验证，**进 PR 门禁**（守住 TDD 红绿），绝不触碰真实 `data/`/`~`。

## Risks / Trade-offs

- **[uv / uv tool install 需联网]** → 干净环境装 uv 与拉依赖要访问网络；预检网络，失败时打印手动安装链接，不静默卡住。
- **[`set -e` 与「告警但继续」冲突]** → Docker 预检等非阻断步骤显式 `|| true` 或包在条件里。
- **[`~/.local/bin` 不在 PATH]** → `uv tool install` 后命令可能仍不可直接调用；调用 `uv tool update-shell`（若可用）或安装结尾打印「把 `~/.local/bin` 加入 PATH」提示，而非偷偷改 shell rc 之外的东西。
- **[依赖前置 change 未合入]** → 若 `configurable-data-home` 未先入 main，全局命令会回退仓库本地解析、找不到 `~/.fleetent` 数据；安装器启动时校验 fleetent 版本/能力，缺失则 fail fast 提示先升级。
- **[与 Docker 交付职责重叠的认知混淆]** → README/脚本头部注释明确「install.sh 面向开发者单机，生产用 Docker」。
- **[bash 跨发行版差异]** → 仅声明支持 Linux/macOS/WSL2 bash；OS 探测失败时 fail fast 并提示走 Docker 路径。

## Migration Plan

纯新增文件，无运行时改动（运行时改动在前置 change）。先合入 `configurable-data-home`，再实施本 change。回滚 = 删除 `scripts/install.sh`。现有 Docker / upgrade 路径完全不受影响。
