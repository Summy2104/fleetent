# fleetent Admin 控制台 — 功能与接口开发文档

> 本文覆盖 React Admin 前端(`fleetent-admin-frontend`)左侧导航的 11 个功能模块。每个模块包含**功能说明** + **逐接口规格**(HTTP 方法、精确路径、query 参数、请求体字段、响应结构、特殊 header、权限)。既是功能文档,也是前后端联调的开发参考。
>
> 来源:`frontend/src/features/<feature>/api.ts`(路径与参数的权威)+ 后端 `src/fleetent/platform/<module>/*_api.py`(响应结构与权限)。

---

## 0. 通用约定(所有接口适用)

### 鉴权
- 所有 admin 接口统一用 **`Authorization: Session <token>`** header(注意是 `Session ` 前缀,**不是** `Bearer ma-<key>`——后者是 agent/model API key)。
- token 由登录获得:`POST /admin/login`(邮箱密码)或 OIDC `GET /admin/oidc/login`(回调带 `?token=`);前端存 `localStorage['fleetent.admin.token']`,降级内存。
- 前端封装在 `lib/api-client.ts` 的 `useAdminApi()`,提供 `get/post/put/patch/delete<T>`,自动注入 token、`content-type: application/json`。

### 权限分级(role)
- **viewer**:只读端点(多数 `GET`)。
- **admin / built_in_admin**:所有写端点(`POST/PUT/PATCH/DELETE`)。
- 前端按 `GET /admin/me` 的 `role` 字段控制 UI:`role === 'viewer'` 时隐藏/禁用写操作(`canWrite = role !== 'viewer'`)。
- 个别模块整体 admin-only(如 **Nodes**、**Tenancy**);**Stats** viewer 可读但 per-user 的 `user_id` 脱敏为 `***`。

### 高危操作确认
- 部分破坏性端点要求 header **`X-Confirm: true`**,缺失返回 **428 Precondition Required**。
- 涉及:删除 agent/skill/KB/文档/node、KB 目录 sync、撤销连接器授权、吊销 API key、强制结束/清空/重置会话、KB connector 真实 sync(`dry_run=false`)等。

### 通用错误码
| 码 | 含义 |
|----|------|
| 401 | token 失效 → 前端自动 `clearToken()` 跳登录 |
| 403 | 权限不足(PermissionError) |
| 404 | 资源不存在 |
| 409 | 冲突:id 重复 / 仍有绑定无法删除(body 常含 `error` + 关联实体列表) |
| 422 | 参数非法(枚举值越界等) |
| 428 | 缺 `X-Confirm: true` |

### 命名差异(前端 camelCase → 后端 snake_case)
前端 hook 入参常用驼峰,序列化到请求体/路径时转 snake_case。例:`keepTurns→keep_turns`、`sessionIds→session_ids`、`newName→new_name`、`runAs→run_as`、`userId→user_id`。掩码字段(`api_key`、token、secret)**永不明文返回**(显示 `first4…last4` 或 `****`)。

### 数据获取模式
- 列表/详情用 TanStack Query(`useXxxQuery`,全局 `retry: false`);写操作用 `useXxxMutation`,`onSuccess` 后 `invalidateQueries` 触发刷新。
- **例外**:**Chat** 走原生 `fetch` + SSE 流式解析;**Stats 导出**走裸 `fetch` 取 CSS Blob。

---

## 1. Agents — Agent 管理控制台

列出/创建/编辑/删除 agent 定义,管理生命周期(enable/disable/archive/restore)、克隆、版本激活、默认 agent,以及绑定(MCP server / OAuth connector / KB / 用户 / IM group)、IM 能力、Skill 开关、密钥注入。读 viewer+,写 admin;归档/删除需 `X-Confirm`。
后端:`agent_console_api.py`(CRUD/生命周期/clone)+ `agent_admin_api.py`(版本/绑定/skill/kb/secret/oauth/im/default)。

### 列表与读取
| Hook | 方法 路径 | 参数/请求体 | 响应 |
|------|-----------|-------------|------|
| `useAgentsQuery` | `GET /admin/agents` | `?include_archived=bool`(前端固定 true) | `AgentListItem[]`:`agent_name`、`is_default?`、`status`、`provenance`、`system_prompt?`、`allowed_tools?`、`icon` |
| `useAgentDetailQuery` | `GET /admin/agents/{name}` | — | `AgentDetail`:`agent`、`allowed_tools[]`、`status`、`system_prompt`、`supports_dm?`、`supports_groups?`(+ `provenance/version/tenant_id/team_id/plugins/features/skills_dir/mcp_server_ids/model_overrides/memory_namespace/icon/config_overrides`) |

### CRUD(均 admin)
| Hook | 方法 路径 | 请求体 | 响应/备注 |
|------|-----------|--------|-----------|
| `useCreateAgentMutation` | `POST /admin/agents` | `name`、`system_prompt`、`allowed_tools[]`(后端另接受 `tenant_id/team_id/plugins/features/skills_dir/mcp_server_ids/model_overrides/memory_namespace/icon/capabilities_yaml/config_overrides_*`) | `_def_response`,HTTP 201;已存在 409 |
| `useUpdateAgentMutation` | `PATCH /admin/agents/{name}` | `allowed_tools[]`、`system_prompt` | 编辑即快照出新 active version |
| `useDeleteAgentMutation` | `DELETE /admin/agents/{name}` | header `X-Confirm: true` | `{agent, deleted:true}`;仍有绑定 409 + `{error,users,channels}` |

### 生命周期 / 克隆 / 默认(均 admin)
| Hook | 方法 路径 | 请求体 | 响应 |
|------|-----------|--------|------|
| `useAgentLifecycleMutation` | `POST /admin/agents/{name}/{action}` | action ∈ enable/disable/archive/restore;archive 需 `X-Confirm: true` | `{agent, status}`;archive 有绑定 409 |
| `useCloneAgentMutation` | `POST /admin/agents/{name}/clone` | `{new_name}` | `{agent, cloned_from, provenance:"adhoc"}`;重名 409,源不存在 404 |
| `useAgentVersionsQuery` | `GET /admin/agents/{name}/versions` | — | `AgentVersion[]`:`id`、`is_active`、`version`、`created_at` |
| `useActivateAgentVersionMutation` | `POST /admin/agents/{name}/versions/{version}/activate` | 路径 `version:number` | `{name, active_version}`;version 不存在 404 |
| `useSetDefaultAgentMutation` | `PUT /admin/agents/{name}/default` | `{}` | `{agent, is_default:true}` |
| `useClearDefaultAgentMutation` | `DELETE /admin/agents/default` | — | `{cleared:true}` |

### 绑定(均 admin)
| Hook | 方法 路径 | 请求体 | 响应 |
|------|-----------|--------|------|
| `useAgentBindingsQuery` | `GET /admin/agents/{name}/bindings` | — | `{mcp_servers[], users[]}` |
| `useAgentSkillsQuery` | `GET /admin/agents/{name}/skills` | — | `{skill_name, enabled}[]` |
| `useSetAgentSkillMutation` | `PUT /admin/agents/{name}/skills/{skillName}` | `{enabled}` | `{agent, skill_name, enabled}` |
| `useBindAgentMcpMutation` | `POST /admin/agents/{name}/bindings/mcp/{serverId}` | — | `{agent, server_id, bound:true}`;未知 server 404 |
| `useUnbindAgentMcpMutation` | `DELETE /admin/agents/{name}/bindings/mcp/{serverId}` | — | `{...bound:false}` |
| `useBindAgentUserMutation` | `POST /admin/agents/{name}/bindings/users/{userId}` | — | `{agent, user_id, bound:true}` |
| `useUnbindAgentUserMutation` | `DELETE /admin/agents/{name}/bindings/users/{userId}` | — | `{...bound:false}` |
| `useAgentKbsQuery` | `GET /admin/agents/{name}/kbs` | — | `{agent, kb_ids[]}` |
| `useBindAgentKbMutation` | `POST /admin/agents/{name}/kbs` | `{kb_id}` | `{agent, kb_id, bound:true}` |
| `useUnbindAgentKbMutation` | `DELETE /admin/agents/{name}/kbs/{kbId}` | — | `{...bound:false}` |
| `useAgentOauthBindingsQuery` | `GET /admin/agents/{name}/bindings/oauth` | — | `{agent, connector_ids[], service_grants:[{run_as, service_id}]}` |
| `useBindAgentOauthMutation` | `POST /admin/agents/{name}/bindings/oauth/{connectorId}` | `{run_as:'agent'\|'user'}` | `{...run_as, bound:true}`;非法 run_as 422,未知 connector 404 |
| `useUnbindAgentOauthMutation` | `DELETE /admin/agents/{name}/bindings/oauth/{connectorId}` | — | `{...bound:false}` |

### IM 能力 / group / Secret(均 admin)
| Hook | 方法 路径 | 请求体 | 响应 |
|------|-----------|--------|------|
| `useSetAgentImCapabilitiesMutation` | `PUT /admin/agents/{name}/im-capabilities` | `{supports_dm, supports_groups}` | 同上回显 |
| `useAddAgentImGroupMutation` | `POST /admin/agents/{name}/bindings/groups` | `{group_id, platform}` | `{...bound:true}`,HTTP 201 |
| `useRemoveAgentImGroupMutation` | `DELETE /admin/agents/{name}/bindings/groups/{platform}/{group_id}` | — | 204 |
| `useAgentSecretsQuery` | `GET /admin/agents/{name}/secrets` | — | `{agent, secrets:[{env_name, mode, status}]}` |
| `useSetAgentSecretMutation` | `PUT /admin/agents/{name}/secrets/{envName}` | `{value}` | `{env_name, status}`;空 value 400 |
| `useDeleteAgentSecretMutation` | `DELETE /admin/agents/{name}/secrets/{envName}` | — | `{env_name, status}` |

> 后端未被前端封装的端点:`GET .../observability?window=7d`、`GET .../agent-yaml`、`POST .../deploy`、`GET .../required-env`。

---

## 2. Chat — Agent 对话调试(SSE 流式)

从 `useAgentsQuery` 选一个 agent,发送单轮消息并通过 **SSE** 流式接收回复。前端用原生 `fetch` + `ReadableStream`,**不走 TanStack Query**。
链路:`server.py:563` → `DirectHttpAgentTransport.chat` → node forwarder → agent 进程 `agent_app.chat` → `runtime.loop.run_stream`。

### 发送消息
- **`useAgentChat().sendMessage(agentName, message)`** → `POST /admin/agents/{agentName}/chat`
  - 请求体:`{ message: string }`
  - header:`content-type: application/json` + `authorization: Session <token>`
  - 响应:`Content-Type: text/event-stream`,HTTP 200 流式
  - 权限:`_require_admin_session`(admin)
  - 错误:401→`clearToken()`;404→agent 不存在;503→agent 无 active placement(未部署);其它→`failed with status N`
- **`useAgentChat().abort()`** — 纯客户端,取消 reader,把当前消息标 `aborted`,无网络请求。

### SSE 事件协议
每个事件为 `data: <json>\n\n`。前端只识别 3 种 `type`:

| `type` | payload | 前端处理 |
|--------|---------|----------|
| `text_delta` | `{type, content}` | 追加到当前 assistant 消息,保持 `streaming` |
| `error` | `{type, content}` | 设 error,消息置 `error`,停止 |
| `done` | `{type, content}` | 消息置 `done`,停止读取 |

> 后端 `run_stream` 还会发 `tool_call`/`tool_result`/`reasoning_delta` 等,前端**静默忽略**未列出的 type。流级异常被 agent 端兜底为一条 `{type:"error",content:...}` 事件而非 HTTP 500。

**解析机制**:`TextDecoder` 增量解码 → 按 `\n\n` 切块 → 取 `data:` 行 `JSON.parse`(失败的块丢弃)→ 收到 `done`/`error` 即停;若流自然结束未见 `done`,按是否已有内容决定 `done`/`error`。并发保护:`activeRequestIdRef` 单调递增,新请求/abort 使旧 stream 回调失效。
**消息状态机**:`state ∈ streaming|done|error|aborted`,`role ∈ user|assistant`;发送时一次性 push 一条 user(done) + 一条空 assistant(streaming)。

---

## 3. Skills — 技能管理

技能的列表/搜索、上传/编辑的安全审计门控、全局与按 agent 启用、归档与引用保护、版本历史 diff、reflection 提案收件箱。读 viewer+,写 admin。后端 `skill_admin_api.py`(prefix `/admin/skills`)。

| Hook | 方法 路径 | 参数/请求体 | 响应/备注 |
|------|-----------|-------------|-----------|
| `useSkillsQuery` | `GET /admin/skills` | `?include_archived=bool`(前端 true);后端另支持 `?q=`、`?audit_verdict=` | `SkillListItem[]`:`name`、`description`、`status`、`global_enabled`、`audit_verdict`、`source`、`drifted_agents[]`、`enabling_agents[]` |
| `useSkillContentQuery` | `GET /admin/skills/{name}/content` | — | `{name, content}`;不存在 404 |
| `useSkillAgentBindingsQuery` | `GET /admin/skills/{name}/agents` | — | `[{agent_id, enabled, name?}]` |
| `useSkillVersionsQuery` | `GET /admin/skills/{name}/versions` | — | `[{sha, message, author, timestamp}]`;无 git pool 返回 `[]` |
| `useSkillDiffQuery` | `GET /admin/skills/{name}/versions/{ref}/diff` | — | `{diff, files?, truncated?}`;无历史 404 |
| `useSkillProposalsQuery` | `GET /admin/skills/proposals` | — | `[{id, type, target_skill, reason, risk_level, has_diff}]` |
| `useSkillProposalDiffQuery` | `GET /admin/skills/proposals/{id}/diff` | — | `{diff, files?, truncated?}` |
| `useSkillLifecycleMutation` | `POST /admin/skills/{name}/{enable\|disable\|restore}` 或 `DELETE /admin/skills/{name}` | delete 需 `X-Confirm: true` | enable→`{global_enabled:1}`、disable→`{global_enabled:0}`、restore→`{status:"active"}`、delete→`{status:"archived"}`;**仍有 agent 启用则 delete 409**(`{error,agents}`) |
| `useForcePublishSkillMutation` | `POST /admin/skills/{name}/force-publish` | `X-Confirm: true` | `{status:"active", forced:1}`;越过安全审计隔离强制发布 |
| `useReloadSkillsMutation` | `POST /admin/skills/reload` | — | `{ok, error?}`;失败 503;原子热重载索引 |
| `useSetSkillAgentBindingMutation` | `PUT /admin/skills/{name}/agents/{agentId}` | `{enabled}` | `{name, agent_id, enabled}`;触发该 agent 重新物化 |

> 后端未封装:`POST /admin/skills`(create)、`PUT /admin/skills/{name}`(edit)、`POST /admin/skills/import/upload`(multipart)、`GET .../observability`。

---

## 4. Sessions — 会话治理

实时会话列表/回放、人工接管(takeover/release)、注入消息、强制结束/清空/重置、批量处置。读 viewer+,写 admin。后端 `chat_admin_api.py`(prefix `/admin`)。

| Hook | 方法 路径 | 参数/请求体 | 响应/备注 |
|------|-----------|-------------|-----------|
| `useSessionsQuery` | `GET /admin/sessions` | `?status=`、`?user_id=`、`?agent_name=`(空值不带) | `SessionListItem[]`:`session_id`、`origin`、`status`、`takeover_actor?`、`takeover_at?`、`agent_name?`、`user_id?`、`channel?`、`updated_at?`、`turns?`、`message_count?`(+`total_tokens/rounds/pending_approvals` 占位 0);agent_name 不存在 404 |
| `useSessionDetailQuery` | `GET /admin/sessions/{sessionId}` | — | `{meta:SessionListItem, transcript:[{role, content}]}` |
| `useTakeoverSessionMutation` | `POST /admin/sessions/{id}/takeover` | — | `{session_id, taken_over:true}` |
| `useReleaseSessionMutation` | `POST /admin/sessions/{id}/release` | — | `{session_id, taken_over:false}` |
| `useInjectSessionMutation` | `POST /admin/sessions/{id}/inject` | `{role, content}`(role 默认 `human_agent`) | `{injected:true}`;origin=im 时经 im-gateway 投递 |
| `useForceEndSessionMutation` | `POST /admin/sessions/{id}/force-end` | `X-Confirm: true` | `{status:"ended"}` |
| `useClearSessionMutation` | `POST /admin/sessions/{id}/clear` | `X-Confirm: true` | `{cleared:true}` |
| `useResetSessionMutation` | `POST /admin/sessions/{id}/reset` | `{keep_turns}`(前端 `keepTurns`)+ `X-Confirm: true` | `{keep_turns}`;截断仅保留前 N 条 |
| `useBulkSessionMutation` | `POST /admin/sessions/bulk` | `{action:'end'\|'clear', session_ids[]}`(前端 `sessionIds`)+ `X-Confirm: true` | `{batch_id, count, action}`;非法 action 422 |

---

## 5. Providers — 模型提供商管理

provider 的增删改查、连通性测试、定价配置。`api_key` 始终掩码。读 viewer+,写 admin。后端 `provider_admin_api.py`。

| Hook | 方法 路径 | 请求体 | 响应/备注 |
|------|-----------|--------|-----------|
| `useProvidersQuery` | `GET /admin/providers` | — | `ProviderListItem[]`:`id`、`description`、`provider`、`protocol`、`base_url`、`model`、`api_key`(掩码)、`api_key_env`、`api_key_set`、`input_price_per_1k`、`output_price_per_1k` |
| `useCreateProviderMutation` | `POST /admin/providers` | 必填 `id`、`base_url`、`model`;可选 `description/provider/protocol/api_key/api_key_env/max_tokens/temperature/params` | 单个 item;id 重复 409;填 inline `api_key` 未给 env 名时自动派生 `FLEETENT_MODEL_<SLUG>_API_KEY` |
| `useUpdateProviderMutation` | `PUT /admin/providers/{id}` | 全部可选(同上去掉 id) | `exclude_unset` 局部更新;不存在 404 |
| `useDeleteProviderMutation` | `DELETE /admin/providers/{id}` | — | `{id, deleted}` |
| `useConnectivityTestMutation` | `POST /admin/providers/{id}/connectivity-test` | — | `{reachable, latency_ms?, model?, base_url?, details?, error?}`;不计用量/成本 |
| `useUpdatePricingMutation` | `PUT /admin/providers/{id}/pricing` | `{input_price_per_1k, output_price_per_1k}`(可 null) | 未配置时回 `"未配置"` 字符串 |

> 后端未封装:`GET /admin/providers/health`、`GET .../{id}/observability`(占位)。

---

## 6. Knowledge Base — 知识库

分两类:**KB 本体**(CRUD/文档/sync/绑定)与 **KB Connectors**(Google Drive / Confluence 数据源)。多租户写操作带可选 `tenant_id`(默认 `"default"`)。读 viewer+,写 admin;高危需 `X-Confirm`。后端 `kb_admin_api.py`。

### 6a. KB 本体
| Hook | 方法 路径 | 参数/请求体 | 响应/备注 |
|------|-----------|-------------|-----------|
| `useKbsQuery` | `GET /admin/kb` | `?tenant_id=`、`?q=`(前端未传) | `KnowledgeBase[]`:`kb_id`、`tenant_id`、`description`、`doc_count`、`chunk_count`、`last_import`、`archived`、`bound_agents[]` |
| `useCreateKbMutation` | `POST /admin/kb` | `{kb_id, description, tenant_id?}` | `{kb_id, tenant_id, description}`;tenant 内重名 409 |
| `useUpdateKbMutation` | `PATCH /admin/kb/{kbId}` | `{description}` | 不存在 404 |
| `useDeleteKbMutation` | `DELETE /admin/kb/{kbId}` | `?tenant_id=` + `X-Confirm: true` | `{kb_id, archived}`(软删/归档);仍绑定 agent 409(`{error,agents}`) |
| `useDocumentsQuery` | `GET /admin/kb/{kbId}/documents` | — | `[{document_id, filename, source, source_url, chunks, created_at}]` |
| `useIngestDocumentMutation` | `POST /admin/kb/{kbId}/documents` | `{source, content, document_format(默认 text), tenant_id?}` | 走异步 job,响应含 `job_id/status/...result`;格式非 text/markdown/html 返回 422;KB 须 active |
| `useDeleteDocumentMutation` | `DELETE /admin/kb/{kbId}/documents/{documentId}` | `?tenant_id=` + `X-Confirm: true` | `{deleted, document_id, kb_id}`;级联删 chunks/vectors |
| `useSyncDocumentsMutation` | `POST /admin/kb/{kbId}/sync` | `{path, tenant_id?}` + `X-Confirm: true` | 走 job,响应 `{job_id, scanned, ingested, skipped, failed, ...}`;全量 resync 高危 |
| `useKbAgentsQuery` | `GET /admin/kb/{kbId}/agents` | — | `{kb_id, agents:number[]}` |

> 后端未封装:`POST /admin/kb/search`(检索 playground)、`POST /admin/kb/evaluations`、`GET /admin/kb/by-agent/{agent_id}`、`GET .../documents/{id}/chunks`、`POST/DELETE .../agents`(绑定)、`GET .../observation`、`POST .../extract-entities`。

### 6b. KB Connectors
| Hook | 方法 路径 | 参数/请求体 | 响应/备注 |
|------|-----------|-------------|-----------|
| `useKbConnectorsQuery` | `GET /admin/kb/connectors` | — | `KbConnector[]`:`connector_id`、`kind`、`tenant_id`、`kb_id`、`enabled`、`description`(取自 KB)、`config`、`custom?`、`custom_yaml?` |
| `useCreateConnectorMutation` | `POST /admin/kb/connectors` | `{connector_id, kind('google_drive'\|'confluence'), config, description, kb_id, enabled?, tenant_id?, custom?, custom_yaml?}` | HTTP 201;id 重复 409,kind 未知 422;`<field>_env_value` inline token 加密入 secret store |
| `useUpdateConnectorMutation` | `PATCH /admin/kb/connectors/{id}` | 可选 `tenant_id/kb_id/enabled/description/config/custom/custom_yaml` | `exclude_unset` 局部更新;不存在 404 |
| `useDeleteConnectorMutation` | `DELETE /admin/kb/connectors/{id}` | — | 204;不存在 404 |
| `useConnectorCheckMutation` | `POST /admin/kb/connectors/{id}/check` | — | `{connector_id, status, message}` |
| `useConnectorStatusQuery` | `GET /admin/kb/connectors/{id}/status` | — | `{connector_id, status, summary, error}`(上次 sync) |
| `useConnectorSyncMutation` | `POST /admin/kb/connectors/{id}/sync` | `{dry_run}`(默认 true) | dry_run=true 同步返回 summary;**dry_run=false 需 `X-Confirm: true`(前端当前未注入 → 会 428),走 ingestion job** |

> ⚠️ 已知缺口:connector 真实 sync(`dry_run=false`)后端要求 `X-Confirm`,但前端未注入,故前端目前只能安全发起 dry-run。

---

## 7. Connectors — 外部连接器与 MCP

分两组:**OAuth/API-Key 连接器**(配置目录 + 每用户授权矩阵 + 凭据生命周期)和 **MCP servers**(配置 CRUD + 实时握手探测)。所有 secret/token 序列化层掩码为 `****`。读端点 viewer+,写端点 admin。后端 `connector_admin_api.py`。

### 7a. OAuth / API-Key 连接器
| Hook | 方法 路径 | 参数/请求体 | 响应/备注 |
|------|-----------|-------------|-----------|
| `useConnectorsQuery` | `GET /admin/connectors` | — | `[{id, display_name, protocol('oauth2'\|'apikey'), enabled, oauth_config?(掩码)}]` |
| `useCreateConnectorMutation` | `POST /admin/connectors` | `{id, display_name, protocol(默认 oauth2), oauth_config?, enabled?}` | admin;id 重复 409,protocol 非法 422;审计 `connector.add` |
| `useUpdateConnectorMutation` | `PUT /admin/connectors/{id}` | 可选 `display_name/protocol/oauth_config/enabled` | admin;不存在 404 |
| `useDeleteConnectorMutation` | `DELETE /admin/connectors/{id}` | — | `{success, connector_id}`;admin |
| `useConnectorLifecycleQuery` | `GET /admin/connectors/{id}/lifecycle` | — | `{connector_id, refresh_ok, refresh_failed, reauths}`(其余 TS 字段后端暂不填) |
| `useConnectorAgentBindingsQuery` | `GET /admin/connectors/{id}/bindings/agents` | — | `{service_id, agent_ids[]}` |
| `useConnectorGrantsQuery` | `GET /admin/connectors/grants` | — | `{grants:[{user_id, connector_id, status, ...}], consent_hint}`;status ∈ authorized/needs_reauth/credential_error |
| `useOffboardingQuery` | `GET /admin/connectors/offboarding/{userId}` | — | `{user_id, revoked[], failed[]}`;离职级联撤销(幂等) |
| `useConnectorAuthorizeQuery` | `GET /admin/connectors/authorize/{id}` | — | `{authorize_url}`;缺元数据 422 |
| `useConnectorCredentialsMutation` | `POST /admin/connectors/{id}/credentials` | `{api_key}` | **仅需登录会话(非 admin)**,key 绑当前用户本人;非 apikey/空 422 |
| `useConnectorTestMutation` | `POST /admin/connectors/{id}/test` | — | `{success, token_valid?, active_grants?, ...}`;不存在仍 200 但 success:false |
| `useRevokeConnectorGrantMutation` | `POST /admin/connectors/grants/{userId}/{connectorId}/revoke` | `X-Confirm: true` | admin;`{revoked, user_id, connector_id}`;审计 `connector.revoke` |

### 7b. MCP servers
| Hook | 方法 路径 | 参数/请求体 | 响应/备注 |
|------|-----------|-------------|-----------|
| `useMcpServersQuery` | `GET /admin/mcp/servers` | (后端可选 `?agent_id=`) | `[{id, transport, url?, command?, args?, enabled?, status, tool_count, agent_id}]` |
| `useCreateMcpServerMutation` | `POST /admin/mcp/servers` | `{id, transport, url?, command?, args?, agent_id?, enabled?}`(+ server_id/auth_type/api_key_env/env/headers) | admin;id 缺 422,重复 409;触发 `mcp_sync_server`,审计 `mcp.create` |
| `useUpdateMcpServerMutation` | `PUT /admin/mcp/servers/{id}` | 全字段可选 | admin;不存在 404;`enabled:false` 即停用 |
| `useDeleteMcpServerMutation` | `DELETE /admin/mcp/servers/{id}` | — | admin;不存在 404 |
| `useMcpServerToolsQuery` | `GET /admin/mcp/servers/{id}/tools` | — | `{connected, tools:[{name, description?}], error?}`;**实时握手** tools/list |
| `useMcpDoctorQuery` | `GET /admin/mcp/doctor` | — | `{checks:[]}`(占位) |
| `useMcpReconnectMutation` | `POST /admin/mcp/servers/{id}/reconnect` | — | `{server_id, reconnected}`;admin |
| `useMcpServerTestMutation` | `POST /admin/mcp/servers/{id}/test` | — | `{success, connected, transport?, tools_count?, tools?, error?}`;真实 initialize+tools/list |

---

## 8. Nodes — 执行节点与放置

托管部署的 node 注册表与 agent→node 放置(pinning)。注册时签发一次性 service key。**整个 router admin-only**。后端 `node_admin_api.py`。

| Hook | 方法 路径 | 参数/请求体 | 响应/备注 |
|------|-----------|-------------|-----------|
| `useNodesQuery` | `GET /admin/nodes` | — | `[{id, name, labels, registered_at, last_seen_at}]`(剔除 key_hash) |
| `useNodePlacementsQuery` | `GET /admin/nodes/{nodeId}/placements` | — | `[{agent_id, node_id, pinned_at, pinned_by, updated_at, agent_name}]` |
| `useNodeAgentsQuery` | `GET /admin/agents?include_archived=true` | 复用 agents 列表作 pin 下拉 | `[{agent_id, agent_name, status, provenance}]` |
| `useRegisterNodeMutation` | `POST /admin/nodes` | `{node_id, name?, labels?}` | `NodeRecord & {service_key_plaintext_once}`(仅此一次);重复 409;审计 `node.register` |
| `useDeleteNodeMutation` | `DELETE /admin/nodes/{nodeId}` | `X-Confirm: true` | 204;仍有 pin 的 agent 409(`{detail, pinned_agents}`);审计 `node.deregister` |
| `usePinAgentMutation` | `POST /admin/nodes/{nodeId}/pin` | `{agent_id}`(+ `pinned_by?`) | `NodePlacement`;agent/node 不存在 404;审计 `node.pin` |
| `useUnpinAgentMutation` | `DELETE /admin/nodes/{nodeId}/pin?agent_id={id}` | query `agent_id`(必填) | 204;审计 `node.unpin` |

> `node_desired_state_api.py` 的端点(`/nodes/{id}/desired-state`、`/status`、`/identity/*`、`/link-confirm`)是 **node→platform 数据面**,由 node 用 service key(`Bearer`)调用,非 admin 前端接口。

---

## 9. Users — 用户 / API Key / IM 绑定

三组:admin 用户 CRUD、用户 API key、IM 身份绑定。读 viewer+,写 admin。后端 `user_admin_api.py`。

### 9a. 用户 CRUD
| Hook | 方法 路径 | 请求体 | 响应/备注 |
|------|-----------|--------|-----------|
| `useUsersQuery` | `GET /admin/users` | — | `[{id, name, email, role, status, must_reset}]` |
| `useCreateUserMutation` | `POST /admin/users` | `{email, name, role(默认 viewer), password?, must_reset?}` | HTTP 201;重复 409,无权 403 |
| `useUpdateUserMutation` | `PATCH /admin/users/{userId}` | `{name?, email?}` | name 空 422,email 冲突 409,不存在 404 |
| `useSetRoleMutation` | `PATCH /admin/users/{userId}/role` | `{role}` | 无权 403 |
| `useBlockUserMutation` | `POST /admin/users/{userId}/block` | `{reason}` | `{status:"blocked"}` |
| `useUnblockUserMutation` | `POST /admin/users/{userId}/unblock` | — | `{status:"active"}` |
| `useResetPasswordMutation` | `POST /admin/users/{userId}/password` | `{new_password}` | 强制目标下次改密(must_reset);不存在 404 |
| `useDeleteUserMutation` | `DELETE /admin/users/{userId}` | — | 204;无权 403 |

### 9b. API Keys
| Hook | 方法 路径 | 请求体 | 响应/备注 |
|------|-----------|--------|-----------|
| `useUserKeysQuery` | `GET /admin/users/{userId}/keys` | — | `[{id, prefix, masked, scope[], note, created_at, revoked_at}]` |
| `useCreateKeyMutation` | `POST /admin/users/{userId}/keys` | `{scope[](默认 ["*"]), note?, expires_at?}` | HTTP 201;`{key, plaintext}` 明文仅此次 |
| `useRotateKeyMutation` | `POST /admin/users/{userId}/rotate-key` | — | `{api_key_plaintext_once, user}`;无 key 404 |
| `useRevokeKeyMutation` | `DELETE /admin/keys/{keyId}` | `X-Confirm: true` | 204;路径用全局 keyId |

### 9c. IM 用户绑定
| Hook | 方法 路径 | 请求体 | 响应/备注 |
|------|-----------|--------|-----------|
| `useImUsersQuery` | `GET /admin/im-users` | — | `[{id, platform, platform_user_id, user_id, status, allowed, created_at?, metadata?}]` |
| `useBindImUserMutation` | `POST /admin/im-users/{imUserId}/bind` | `{user_id}` | `{status:"bound"}`;目标用户不存在 404(多对一重绑) |
| `useBlockImUserMutation` | `POST /admin/im-users/{imUserId}/block` | `{reason}` | `{allowed:false}` |
| `useRestoreImUserMutation` | `POST /admin/im-users/{imUserId}/restore` | `{reason}` | `{allowed:true}` |

> 后端未封装:`GET /admin/im-users/fields`、`PATCH/DELETE /admin/im-users/{id}`、`POST /admin/service-principals`、`/login`、`/me` 等。

---

## 10. Tenancy — 多租户 / 团队

租户与团队的创建/列举、用户分配到租户、为租户/团队设置审批人。**全部 admin-only**。后端 `tenancy/admin_api.py`。

| Hook | 方法 路径 | 请求体 | 响应/备注 |
|------|-----------|--------|-----------|
| `useTenantsQuery` | `GET /admin/tenancy/tenants` | — | `[{id, name, status, approver_user_id, created_at}]` |
| `useCreateTenantMutation` | `POST /admin/tenancy/tenants` | `{name, id?, status?(默认 active)}` | `TenantListItem` |
| `useTeamsQuery` | `GET /admin/tenancy/teams` | (后端可选 `?tenant_id=`) | `[{id, name, tenant_id, approver_user_id, created_at}]` |
| `useCreateTeamMutation` | `POST /admin/tenancy/teams` | `{name, tenant_id, id?}` | `TeamListItem` |
| `useAssignUserTenantMutation` | `POST /admin/tenancy/users/{user_id}/tenant` | body 仅 `{tenant_id}`(user_id 拼路径) | `{status:"ok", user_id, tenant_id}`;用户不存在 404 |
| `useSetApproverMutation` | `PATCH /admin/tenancy/approvers/{entityId}` | `{entity_type:'tenant'\|'team', approver_user_id(可 null)}` | `{status, entity_type, id}`;非法 entity_type 400 |

---

## 11. Statistics — 运行统计(只读 + 导出)

agent 运行数据的只读聚合:单 agent 总览、多 agent 对比、工具使用、按用户排名、请求/会话级 trace 钻取、CSV 导出。数据源 observability traces / approvals / agent_store。读 viewer+(viewer 的 per-user `user_id` 脱敏为 `***`)。后端 `stats_admin_api.py`。

| Hook | 方法 路径 | 参数 | 响应/备注 |
|------|-----------|------|-----------|
| `useAgentOverviewQuery` | `GET /admin/stats/agents/{agentId}/overview` | `?window=`(默认 7d;有效 1h/24h/7d/30d) | `{agent_id, usage, performance, approvals, cost}` |
| `useCompareAgentsQuery` | `GET /admin/stats/compare` | `?agents=`(逗号拼接 id)、`?key=`(默认 calls) | `[{agent_id, value}]` |
| `useAgentToolsQuery` | `GET /admin/stats/agents/{agentId}/tools` | — | `{top_tools:{top:[[name,count]]}, coverage}` |
| `usePerUserStatsQuery` | `GET /admin/stats/per-user` | `?agent_id=?`、`?sort_by=`(默认 total_tokens) | `[{user_id, ...}]`;viewer 下 user_id `***` |
| `useUserRequestsQuery` | `GET /admin/stats/users/{userId}/requests` | — | `[{request_id, session_id?, ...}]` |
| `useRequestDetailQuery` | `GET /admin/stats/requests/{requestId}` | — | `StatsTrace`:`{events[], subagents[], ...}` |
| `useSessionTraceQuery` | `GET /admin/stats/sessions/{sessionId}/trace` | `?user_id=`(**必需**) | `StatsTrace` |
| `useStatsExportMutation` | `POST /admin/stats/export` | `?agent_id=?`、`?view=`(per-user/tools/默认 flat) | **CSV Blob**(`text/csv`,`Content-Disposition: attachment`);裸 fetch;唯一写入(审计 `stats_export`) |

---

## 附录:接口约定速查

- **统一鉴权**:`Authorization: Session <token>`(非 `Bearer ma-`)。
- **唯一非 admin 写**:`POST /admin/connectors/{id}/credentials`(用户自助填本人 API key)。
- **唯一裸 fetch(非 useAdminApi)**:`useStatsExportMutation`(取 Blob)、`useAgentChat`(SSE)。
- **`X-Confirm: true` 端点**:删除 agent/skill/KB/文档/node、KB 目录 sync、撤销连接器授权、吊销 key、force-end/clear/reset/bulk 会话、KB connector 真实 sync。
- **一次性明文**:node service key(`service_key_plaintext_once`)、用户 key 签发(`plaintext`)/轮换(`api_key_plaintext_once`)——仅返回一次,不可再查。
- **整体 admin-only 模块**:Nodes、Tenancy。
- **多租户**:KB 端点带可选 `tenant_id`(默认 `default`),前端多数未传。
