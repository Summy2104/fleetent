## Context

部署 home 现为 `FLEETENT_HOME/config/agent.yaml`（`paths.agent_file()=config_dir()/agent.yaml`，install.sh seed 到此）。而 `fleetent agent run <id>` 用扁平 per-agent home `FLEETENT_HOME/<id>/agent.yaml`。两套布局不一致。仓库示例 `config/agent.yaml.example` + 根 `.env.example` 混在一起，不分使用方。`.env` 由进程 CWD `./.env` 加载（`Settings.env_file=".env"`），示例文件仅为模板（操作者拷贝/source）。

## Goals / Non-Goals

**Goals:** 部署 home 扁平（`agent.yaml` 在根）；示例按 agent/platform 分目录、`.env.example` 收进 `config/`；三方（spec/代码/模板）一致。
**Non-Goals:** 不改 `.env` 的加载机制（仍 CWD `./.env`，本次只重排模板，Q1=A 的精神）；不改 `agent run <id>`；不动加载器/平台；不动部署的 `data/` 位置。

## Decisions

**D1 `paths.agent_file()` → `base_dir()/agent.yaml`。** home agent（一次性 `fleetent "<prompt>"`）读扁平根；与 install.sh seed 位置、与 `agent run <id>` 的扁平 per-agent home 一致。这是 Q3 扁平 home 成立的必要 1 行运行时改动（用户已确认接受，超出"纯 A"）。

**D2 示例按使用方分目录。** `config/agent/{agent.yaml.example,.env.example}` + `config/platform/.env.example`；删根 `.env.example` 与 `config/agent.yaml.example`。`.env.example` 收进 `config/` 满足"放到 config 下"。

**D3 .env 分割边界（共用项两份都列）。**
- agent：`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`、该 agent 的 IM/MCP/KB token（SUPPORT_SLACK_*、ACME_DOCS_MCP_TOKEN、BILLING_DB_DSN、GITHUB_MCP_API_KEY、FLEETENT_GOOGLE_DRIVE_*、FLEETENT_CONFLUENCE_*、FLEETENT_EVAL_*）、`MICROSANDBOX_URL`、`VISION_URL/MODEL`、`PERMISSION_GATE_*`、`CONTEXT_*`、`LOG_FORMAT`。
- platform：`ANTHROPIC_API_KEY`（Settings 必填，注释「与 agent 重复」）、`FLEETENT_AUTO_UPGRADE`、`DATABASE_URL`、`FLEETENT_TUI_URL`/`FLEETENT_TOKEN`、`LOG_FORMAT`。

**D4 install.sh 扁平 seed。** seed `$FLEETENT_HOME/agent.yaml`（从 `config/agent/agent.yaml.example`）+ `$FLEETENT_HOME/.env`（从 `config/agent/.env.example`）；移除 `mkdir config` 与 config/ 拷贝。部署 home：`agent.yaml`+`.env`+`data/`。

**D5 init_config 用 platform 模板。** `fleetent-admin init-config`（平台脚手架）的 `.env` 源 = `config/platform/.env.example`。

**D6 .gitignore 修正。** 忽略 `config/agent/agent.yaml`、`config/**/.env`、`config/platform/*.yaml`（如有）；committed 仅 `*.example`。

## Risks / Trade-offs

- **[BREAKING 已有部署]** 旧 `FLEETENT_HOME/config/agent.yaml` 不再被读 → home agent 落空。Mitigation：proposal/README/CLAUDE 写明迁移（把 agent.yaml 移到 home 根）；install.sh「存在即跳过」对扁平路径，不会误删旧 config/。
- **[一致性回归]** `.env.example` 与 agent.yaml.example 的 `*_env` 引用必须仍同步（已有 `test_env_example_covers_agent_yaml_example_env_refs`，路径需指向 `config/agent/`）。
- **[测试面广]** ~7 个测试引用旧路径，逐一更新；全量套件兜底。

## Migration Plan

代码+模板+spec 同改；回滚=还原 `agent_file()`、模板位置、install.sh。运行时 `.env` 加载不变（CWD）。
