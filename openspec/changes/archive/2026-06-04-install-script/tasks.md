## 0. 前置确认

- [x] 0.1 确认前置 change `configurable-data-home` 已合入 main（`FLEETENT_HOME` 路径解析可用）；否则本 change 不进入实施

## 1. 脚手架与参数解析（含 --help）

- [x] 1.1 Write failing tests：`tests/integration/test_install_script.py` —— 断言 `scripts/install.sh` 存在且可执行；`--help` 退出码 0 且输出含全部受支持 flag（`--skip-db`/`--skip-config`/`--dir`/`--help`）且不产生副作用；未知 flag 以非零退出码退出并打印用法。用临时 HOME/CWD 隔离，绝不触碰真实 `data/`/`~`
- [x] 1.2 Implement：创建 `scripts/install.sh`（`#!/bin/bash` + `chmod +x`）——顶部 env 净化（unset `PYTHONPATH`/`PYTHONHOME`、`set -e`）、颜色/日志 helper、arg 解析与 `usage()`、`main()` 骨架（函数留空 stub），使 1.1 转绿

## 2. uv 探测与全局命令安装

- [x] 2.1 Write failing tests：注入假 `uv` 到临时 PATH 验证「已存在则复用、缺失才装」；断言安装步骤调用 `uv tool install`；缺入口时告警并打印可复现命令；`check_python` 对 `<3.12` fail fast
- [x] 2.2 Implement：`ensure_uv()`（探测 `PATH`→`~/.local/bin`→`~/.cargo/bin`，缺失才装）、`check_python()`（校验 `>=3.12`）、`install_tool()`（`uv tool install`，校验三入口生成）使测试转绿

## 3. FLEETENT_HOME 状态目录

- [x] 3.1 Write failing tests：默认 `FLEETENT_HOME=~/.fleetent`（隔离 HOME 验证）并写入 shell rc（幂等：重跑不重复写）；`--dir PATH` 覆盖默认；`~/.local/bin` 不在 PATH 时打印加入提示
- [x] 3.2 Implement：`setup_home_env()` —— 解析 `FLEETENT_HOME`（默认 `~/.fleetent`，`--dir` 覆盖）、本次进程内 export、幂等写入 shell rc、PATH 提示，使测试转绿

## 4. 配置模板拷贝（幂等）

- [x] 4.1 Write failing tests：fresh 时从 `.env.example`→`$FLEETENT_HOME/.env`、`config/*.yaml.example`→`$FLEETENT_HOME/config/*.yaml`；已存在时不覆盖（写哨兵内容后重跑，断言保留）；`--skip-config` 时不拷贝
- [x] 4.2 Implement：`copy_config_templates()` —— 「存在即跳过」语义（`[ -f x ] || cp`），受 `--skip-config` 短路，使测试转绿

## 5. Alembic 数据库初始化（幂等）

- [x] 5.1 Write failing tests：默认运行针对 `$FLEETENT_HOME/data` 调用 `alembic upgrade head` 并生成数据库；重复运行不报错、不破坏已有数据；`--skip-db` 时不运行 Alembic
- [x] 5.2 Implement：`init_db()` —— 针对 `FLEETENT_HOME/data` 运行 `alembic upgrade head`（复用 `alembic.ini`/`migrations/`，不自建建表逻辑），受 `--skip-db` 短路，使测试转绿

## 6. Docker 非阻断预检

- [x] 6.1 Write failing tests：临时 PATH 无 `docker` 时 script 打印沙箱告警但以退出码 0 完成；有 `docker`（注入假 docker）时不发沙箱告警
- [x] 6.2 Implement：`precheck_docker()` —— `command -v docker` 失败时告警继续（`|| true`，避免被 `set -e` 误杀），使测试转绿

## 7. 端到端编排与收尾

- [x] 7.1 Write failing tests：`main()` 全流程在隔离环境跑通（mock 网络相关步骤）——顺序执行各步、`--dir` flag 生效；`print_success` 输出含「如何把 `~/.local/bin` 加入 PATH」提示
- [x] 7.2 Implement：`main()` 串联 `detect_os → ensure_uv → check_python → install_tool → setup_home_env → copy_config_templates → init_db → precheck_docker → print_success`，`--dir` 短路逻辑接好，使测试转绿
- [x] 7.3 收尾：脚本头部注释标注「面向开发者/单机；生产用 Docker」；README 增补一键安装说明（含 Linux/macOS/WSL2 范围）；全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -x -q` 通过；`uv run ruff format && uv run ruff check` 仅校验本 change 新增测试文件；运行 `shellcheck scripts/install.sh`（若可用）无致命告警
