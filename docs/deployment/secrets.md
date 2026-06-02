# 部署 Secret 文件约定

Fleetent Pilot 使用项目根目录下的 `secrets/` 保存本地部署级 credential 文件。该目录不进 git，
Docker Compose 以只读方式挂载到容器内的 `/app/secrets`。

`secrets/` 目录保持平铺，不按 provider、tenant、agent 或 connector scope 分目录。文件名只表达
credential 类型，不表达业务 scope，例如：

```text
secrets/
  google-drive-token.json
  confluence-api-token
  github-mcp-api-key
```

scope 由 `config/settings.yaml` 或后续 connector 配置表达，不靠 secret 文件路径表达。支持文件引用
的配置使用 `credential_ref`：

```yaml
credential_ref: "file:///app/secrets/google-drive-token.json"
```

不要把真实 secret、token、credential payload 写入 `.env.example`、`settings.yaml.example`、日志、
trace、diagnostics package、issue 或测试 fixture。`fleetent-admin init-config` 只创建空的
`secrets/` 目录，不生成任何真实 secret 文件。
