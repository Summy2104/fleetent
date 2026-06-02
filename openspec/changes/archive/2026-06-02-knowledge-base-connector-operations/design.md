## Context

当前 knowledge-base connector 已经有运行时能力：

- Google Drive connector：指定 folder scope、OAuth `credential_ref`、fake client 默认测试、真实 smoke opt-in。
- Confluence connector：Cloud API token `credential_ref`、space / page scope、fake client 默认测试、真实 smoke opt-in。
- sync planner / executor：可以生成 plan、执行同步并返回 summary。

但这些能力还更像 library API。Pilot 环境需要 operator 能用一个稳定入口执行基本操作。

## Configuration

connector 定义放在 `settings.yaml` 的非 secret 配置中。真实 credential 不放配置文件。

建议结构：

```yaml
knowledge_base:
  google_drive:
    connectors:
      - connector_id: eng-drive
        enabled: true
        tenant_id: default
        kb_id: engineering
        folder_id: "..."
        recursive: true
        credential_ref: "file:///etc/fleetent/secrets/google-drive-eng-token.json"

  confluence:
    connectors:
      - connector_id: eng-confluence
        enabled: true
        tenant_id: default
        kb_id: engineering
        base_url: "https://example.atlassian.net/wiki"
        username: "bot@example.com"
        space_key: "ENG"
        page_id:
        include_children: true
        credential_ref: "env:FLEETENT_CONFLUENCE_API_TOKEN"
```

配置只描述：

- connector identity。
- connector type。
- tenant / kb 写入范围。
- remote scope。
- `credential_ref`。

配置不包含：

- OAuth refresh token 明文。
- client secret 明文。
- Confluence API token 明文。
- 最终用户 ACL。

## Registry

新增 connector registry 负责把配置转成 typed connector config：

- `GoogleDriveConnectorConfig`
- `ConfluenceConnectorConfig`

registry 行为：

- `connector_id` 必须全局唯一。
- disabled connector 可以被 `list` 看见，但不能执行 `sync`，`check` 应返回 disabled 状态。
- 缺少必填字段时 fail fast，并给出字段名。
- 未知 connector type fail fast。

registry 不访问 remote API，也不读取真实 credential 内容；它只解析配置。

## Admin CLI

Pilot MVP 先做 `fleetent-admin` CLI，不做 HTTP endpoint / UI。

命令建议：

```bash
fleetent-admin kb connectors list
fleetent-admin kb connectors check <connector_id>
fleetent-admin kb connectors status <connector_id>
fleetent-admin kb connectors sync <connector_id> --dry-run
fleetent-admin kb connectors sync <connector_id>
```

输出格式先用 human-readable table / key-value，后续如有自动化需求可以再加 `--json`。本 spec 不强制 `--json`。

## Operations

### list

列出配置中的 connector：

- connector_id
- type
- enabled
- tenant_id
- kb_id
- scope 摘要

不显示完整 `credential_ref` 路径中的 secret-like 片段；如果要显示，可以只显示 scheme 和 basename。

### check

检查：

- connector 是否存在。
- connector 是否 enabled。
- `credential_ref` 是否可解析。
- credential 文件 / 环境变量是否存在。
- fake 或 real client 是否能完成认证检查。
- remote scope 是否可访问。

结果状态建议：

- `ok`
- `disabled`
- `credential_missing`
- `credential_invalid`
- `auth_failed`
- `scope_unreachable`
- `unknown_error`

### sync --dry-run

执行 plan，不写入 KB，不更新 source state，不更新 vector index。

dry-run 输出 plan summary：

- scanned
- planned
- new / changed / unchanged / unsupported / archive_missing
- auth_failed
- failed

dry-run 可以更新 `knowledge_connector_status` 为 `dry_run_ok` 或 `dry_run_failed`，但不能把它伪装成真实 sync 成功。

### sync

执行现有 connector planner + executor。运行结束后写入最近一次 status。

状态建议：

- `sync_succeeded`
- `sync_failed`
- `auth_failed`
- `disabled`

失败 item 只保存摘要，不保存文档正文、完整 remote payload 或 credential。

### status

读取 `knowledge_connector_status`，展示最近一次：

- connector_id / type / tenant_id / kb_id
- last_status
- last_started_at
- last_finished_at
- last_summary
- last_error

如果没有历史运行，返回 `never_run`。

## Persistence

新增 knowledge-base-owned 表：

```sql
knowledge_connector_status (
  connector_id TEXT PRIMARY KEY,
  connector_type TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  kb_id TEXT NOT NULL,
  last_status TEXT NOT NULL,
  last_started_at DATETIME,
  last_finished_at DATETIME,
  last_summary_json TEXT NOT NULL,
  last_error TEXT,
  updated_at DATETIME NOT NULL
)
```

只保存最近一次状态，不保存完整历史。

原因：

- Pilot 排障需要知道最近一次同步结果。
- 完整 run history 会引入 retention、分页、item history 和 dashboard 设计，本阶段不需要。

## Credential Boundary

本 spec 只处理 `credential_ref`：

- `file://...`
- 本地路径。
- `env:VAR_NAME`

真实 credential 的创建、授权、刷新、轮换和加密存储不在本 spec 内。

connector operations 可以调用现有 resolver 或新增统一 resolver，但不得把 credential payload 写入日志、trace、status table 或 CLI 输出。

## Testing

默认测试使用 fake connector client，不访问 Google / Atlassian。

测试重点：

- 配置解析和 connector_id 唯一性。
- disabled connector 行为。
- credential missing / invalid / auth failed 状态。
- dry-run 不写 KB、不更新 source state、不写 vector。
- sync 写入最近一次 status。
- status 对 never-run connector 返回稳定结果。
- CLI 命令调用 operations API 并输出脱敏结果。
- 失败摘要不包含 token、secret、credential payload 或文档正文。

## Non-Goals

本 change 不解决：

- connector UI。
- HTTP admin API。
- secret manager。
- scheduler / worker。
- full run history。
- connector ACL。
- 新 connector 类型。
