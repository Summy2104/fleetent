# 用户与部门 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

## 用户 (User)

### `GET /v1/users` — 用户列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/users" \
  'query_params={"status": 1, "page": 1, "page_size": 20}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `nickname` | 姓名（模糊匹配） |
| `email` | 邮箱 |
| `phone` | 手机号 |
| `status` | 状态：`1`=启用，`2`=禁用 |
| `role_id` | 角色 ID |
| `role_ids` | 角色 ID 列表 |
| `page` | 页码 |
| `page_size` | 每页数量 |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 用户 ID |
| `nickname` | string | 昵称 |
| `email` | string | 邮箱 |
| `phone` | string | 手机号 |
| `phone_code` | string | 手机区号 |
| `status` | int | 状态：`1`=启用，`2`=禁用 |
| `timezone` | string | 时区 |
| `slack_bind` | int | Slack 绑定状态 |
| `roles` | array | 角色列表 |
| `created_at` | string | 创建时间（UTC，展示转 UTC+8） |
| `updated_at` | string | 更新时间（UTC，展示转 UTC+8） |

---

### `GET /v1/users/keyword` — 用户名称列表（ID 查名称）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/users/keyword" \
  'query_params={"nickname": "张三"}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `role_id` | 角色 ID |
| `role_ids` | 角色 ID 列表 |
| `nickname` | 名称（模糊匹配） |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 用户 ID |
| `nickname` | string | 昵称 |
| `email` | string | 邮箱 |

---

## 部门 (Department)

### `GET /v1/department/list` — 部门列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/department/list" \
  'query_params={"name": "技术部", "status": 1}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `id` | 部门 ID |
| `name` | 部门名称（模糊匹配） |
| `leader_email` | 负责人邮箱 |
| `leader_id` | 负责人 ID |
| `status` | 状态：`1`=启用，`2`=禁用 |
| `abbreviation` | 部门简称 |
| `page` | 页码 |
| `page_size` | 每页数量 |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 部门 ID |
| `name` | string | 部门名称 |
| `abbreviation` | string | 部门简称 |
| `description` | string | 描述 |
| `leader_id` | string | 负责人 ID |
| `leader_name` | string | 负责人名称 |
| `leader_email` | string | 负责人邮箱 |
| `status` | int | 状态：`1`=启用，`2`=禁用 |

---

### `GET /v1/department/keyword` — 部门名称列表（ID 查名称）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" get "/v1/department/keyword"
```

**请求参数**：无

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 部门 ID |
| `name` | string | 部门名称 |
