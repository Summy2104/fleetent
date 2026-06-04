## Context

config/data 路径是 ~20 处散落的硬编码相对常量（`config.py` 的 `SETTINGS_YAML_PATH`/`database_url`、`user_store.py` 的 `DB_PATH`、`session/manager.py` 的 `SESSIONS_DIR`、`observability/traces.py` 直接 `os.environ.get("DATABASE_URL", "sqlite:///data/fleetent.db")` 等），全部相对 CWD，迫使应用只能在仓库根运行。已有 `src/fleetent/db.py` 作为 DB runtime 边界（吃 `database_url` → `SQLiteDatabase`），但它不负责"路径从哪来"。CLAUDE.md 明确：这些 legacy 模块级路径常量是迁移前技术债，且新增/改造数据库代码须经统一边界、禁止扩散 SQLite 细节与路径常量。

本 change 是 `install-script`（全局解耦安装）的前置：先让应用支持仓库外固定家目录。

## Goals / Non-Goals

**Goals:**
- 单一中心 `paths.py` 解析所有 config/data 路径，优先级：`FLEETENT_HOME` → 仓库本地 → `~/.fleetent`。
- 开发态零改动：仓库内 `uv run pytest` / `uv run fleetent` 仍命中 `./config`+`./data`，无需设环境变量。
- 保持现有 `monkeypatch` 注入习惯可用（测试隔离不破）。
- 不改 SQL、不改 schema、不改文件名、不引入依赖。

**Non-Goals:**
- 不统一 `fleetent.db` vs `users.db` 命名矛盾（单独 cleanup）。
- 不做 XDG 拆分（决策定为单一 home）。
- 不做老数据从 `./data` 到 `~/.fleetent` 的自动迁移（operator/文档负责）。
- 不改 `db.py` 的 DB runtime 边界契约。

## Decisions

**D1：单一 `FLEETENT_HOME`，config/data 为其子目录。**
`$FLEETENT_HOME/config` + `$FLEETENT_HOME/data`，默认 `~/.fleetent`。比 XDG 拆分直观，备份/迁移只搬一个目录，对齐 hermes 的 `~/.hermes`。

**D2：解析优先级 env → 仓库本地 → 家目录。**
```
base():
  if $FLEETENT_HOME set:        return $FLEETENT_HOME        # 显式覆盖最高
  if repo_marker_present(CWD):  return <repo root>            # 开发态零改动
  return ~/.fleetent                                          # 全局安装态回退
```
`repo_marker_present` 以 CWD（向上若干层）存在 `pyproject.toml` 且含 `name = "fleetent"`、或存在 `./config` 目录为准。env 优先于仓库本地，使开发者可显式覆盖；仓库本地优先于家目录，保证现有开发流程零改动。
- 备选：纯 env（无仓库回退）。弃因：打断现有所有 `uv run` 习惯、测试全要改，blast radius 失控。

**D3：`paths.py` 暴露解析函数 + 派生路径，模块从中派生常量。**
`paths.py` 提供 `config_dir()`、`data_dir()`，以及派生便捷项（`settings_yaml_path()`、`users_db_path()`、`sessions_dir()` 等）。各模块的 `SETTINGS_YAML_PATH`/`DB_PATH`/`SESSIONS_DIR` 等常量改为在 import 时 `= paths.xxx()` 求值。env 在进程启动前设定，import 时求值即可正确解析。
- 备选：每模块各自 `os.getenv("FLEETENT_HOME")`。弃因：违反 CLAUDE.md「禁止扩散」——路径解析逻辑必须收口一处。

**D4：保留模块级常量作为注入 seam，叠加 env 注入。**
现有测试 `monkeypatch.setattr(session_manager, "SESSIONS_DIR", tmp_path/...)` 继续有效（仍是模块属性）。新增整体重定向能力：`monkeypatch.setenv("FLEETENT_HOME", tmp_path)` + 重新解析。两种隔离方式并存，迁移期不破坏既有测试。

**D5：`observability/traces.py` 等直接读 `os.environ["DATABASE_URL"]` 的旁路收编。**
统一改为经 `paths.py`/config 的 `database_url` 解析，消除"绕过 config 直接拼 `sqlite:///data/fleetent.db`"的旁路，但保持 `DATABASE_URL` 环境变量优先级语义（与 `deployment` 的 upgrade 脚本一致）。

**D6：逐模块 TDD 迁移，按 blast radius 排序。**
先立 `paths.py` + 其单测；再从调用方少的（eval_logger、builtin_tools、sandbox config）迁到核心（config.py、user_store、session/*）。每模块红→绿，全程保持全量测试绿。

## Risks / Trade-offs

- **[import 时求值无法响应运行中改 env]** → 设计即假设 `FLEETENT_HOME` 进程启动前设定；测试要动态重定向走 monkeypatch 模块常量或提供 `paths.reset()` 重解析钩子。
- **[repo_marker 误判]** → 在某个恰好有 `./config` 的无关目录运行会误用本地；以 `pyproject.toml` 含 `name="fleetent"` 为强标记，`./config` 仅作弱回退，降低误判。
- **[~20 处一次性改动面大]** → 按 D6 逐模块 TDD，每步独立可回滚；不一次性大改。
- **[traces.py 旁路收编改变默认 DB 来源]** → 加回归测试锁定 `DATABASE_URL` 优先级与默认值不变。
- **[与 install-script 的耦合]** → 本 change 先行合入 main，install-script 再依赖；二者分两个 PR，顺序明确。

## Migration Plan

纯路径来源重定向，默认行为（仓库内）不变。部署：随分支合入 main。回滚：还原 `paths.py` 引入前的常量定义。老用户 `./data` 数据不受影响（仓库内运行仍读它）；切到全局安装的用户需把数据置于 `~/.fleetent/data`（install-script 负责初始化，老数据迁移由文档指引）。

## Open Questions

- `repo_marker` 是否需要向上递归查找 `pyproject.toml`（支持在仓库子目录运行），还是仅查 CWD？倾向仅查 CWD + 一层父级，避免意外命中外层无关项目。
