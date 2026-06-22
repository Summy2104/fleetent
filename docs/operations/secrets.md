# 部署 Secret 文件约定

Fleetent Pilot 使用项目根目录下的 `secrets/` 保存本地部署级 credential 文件。该目录不进 git，
Docker Compose 以只读方式挂载到容器内的 `/app/secrets`。

`secrets/` 目录保持平铺，不按 provider、tenant、agent 或 connector scope 分目录。文件名只表达
credential 类型，不表达业务 scope，例如：

```text
secrets/
  confluence-api-token
  github-mcp-api-key
```

scope 由 `agents/<agent-id>/agent.yaml` 的 connector 配置表达，不靠 secret 文件路径表达。Google Drive
推荐使用平铺环境变量，避免把整段 OAuth JSON 放入单个环境变量或文件：

```yaml
access_token_env: FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN
refresh_token_env: FLEETENT_GOOGLE_DRIVE_REFRESH_TOKEN
client_id_env: FLEETENT_GOOGLE_DRIVE_CLIENT_ID
client_secret_env: FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET
```

对应环境变量：

```bash
FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN=...
FLEETENT_GOOGLE_DRIVE_REFRESH_TOKEN=...
FLEETENT_GOOGLE_DRIVE_CLIENT_ID=...
FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET=...
```

Confluence 使用 username env 和 token env：

```yaml
username_env: "FLEETENT_CONFLUENCE_USERNAME"
api_token_env: FLEETENT_CONFLUENCE_TOKEN
```

不要把真实 secret、token、credential payload 写入 `.env.example`、`agent.yaml.example`、日志、
trace、diagnostics package、issue 或测试 fixture。`fleetent admin init-config` 只创建空的
`secrets/` 目录，不生成任何真实 secret 文件。
