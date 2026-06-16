# 客户写操作 API 参考（bs-customer-drafting）

本文件定义 `bs-customer-drafting` skill 允许调用的 3 个端点。所有字段名、类型、枚举值以本文档为准。

> 调用走 armada 两步交互（见 SKILL.md「armada 两步交互」）：`bash_exec` 跑 `scripts/ns-call.sh` 拿 `ARMADA_CALL` 行 → agent 发起 `armada__armada_post` / `armada__armada_put` / `armada__armada_get` 工具调用 → 返回 JSON 由 `run_code` 加工。

## 端点清单

| 端点 | 方法 | 用途 | 对外暴露 |
|------|------|------|---------|
| `/v1/customers` | POST | 创建客户 | ✅ |
| `/v1/customers/{id}` | PUT | 修改客户 | ✅ |
| `/v1/customers/{id}/close` | POST | close（创建后内联；对用户称草稿态） | ❌ 仅用于创建后自动内联调用 |

---

## 请求格式规则（所有端点通用）

- **大整数 ID 必须传字符串**：NS 系统使用 64-bit 雪花 ID（19 位左右，例如 `"2046555212949643264"`），超出 JS 安全整数范围 2^53-1，JSON 里必须用字符串，否则后端 400。这条适用于**所有 ID 字段**：`biz_lines[]` 元素、path 里的 `{id}`、`contacts[].xxx_id`、响应里的 `id` 等。
  - 正例：`"biz_lines": ["2046554312949643264", "2046555212949643264"]`
  - 反例：`"biz_lines": [2046554312949643264, 2046555212949643264]`（会被截断成错误数值）
- **数组**：`"biz_lines": ["12", "34"]`、`"email": ["a@x.com", "b@x.com"]`；单值时也必须用数组形式 `["x"]`
- **嵌套对象**：`"contacts": [{"name":"张三","email":"zhangsan@x.com","phone":"..."}]`
- **枚举**：`kyc` / `nda` / `status` 这类**小范围整数**枚举**必须传整数**，**不得传字符串**。正例：`"kyc": 2`；反例：`"kyc": "2"`。注意：枚举和 ID 是两类，ID 传字符串，枚举传整数，不要混。
- **空值**：不想设的字段直接不放进 body，不要用 `null` 或 `""` 占位

## 响应失败形态（所有端点通用）

NS 后端写操作的失败分两种形态，skill 必须同时检测：

### 形态 1：HTTP 4xx/5xx（传输/参数/服务端错误）

```
HTTP 400 Bad Request
{"error":"...","message":"..."}
```

### 形态 2：HTTP 200 + body 含 `error_code`（业务规则不通过）

```
HTTP 200 OK
{
  "error_code": "ErrCustomerLastBizLine",
  "error_message": "无法删除最后一条关联业务线，如需删除请禁用客户"
}
```

**检测规则**：响应 body 存在非空 `error_code` 字段即为失败，**不得因为 HTTP 200 就判定成功**。已知业务错误码：

| error_code | 触发条件 |
|-----------|---------|
| `ErrCustomerLastBizLine` | PUT 未传 `biz_lines` 或传入空数组（后端视为清空最后一条业务线） |

### 成功判定

HTTP 2xx **且** body 不含 `error_code`。

---

### 典型完整 POST body（创建客户）

```json
{
  "name": "示例科技有限公司",
  "short_name": "示例科技",
  "biz_lines": ["2046554312949643264", "2046555212949643264"],
  "email": ["contact@example.com"],
  "kyc": 2,
  "nda": 2,
  "memo": "2026-Q1 新客户"
}
```

### 典型 PUT body（修改客户）

**本 skill 采用完整 PUT 模式**：body 带上所有可改字段的最终值（改动的用新值，未改的用从 `GET /v1/customers/{id}` 拉回的原值）。这样避免单字段 PUT 在不同后端实现下行为不一致。

```json
{
  "short_name": "AI 客户02",
  "customer_code": "C1102",
  "code": "CUST001",
  "biz_lines": ["1937032282944163858"],
  "email": ["a@x.com", "b@x.com"],
  "register_address": "上海市浦东新区",
  "kyc": 2,
  "nda": 1,
  "memo": "2026-Q2 续签",
  "contacts": [{"name": "张三", "email": "zhangsan@x.com"}]
}
```

**唯一例外**：详情接口未返回的字段（首次联调时 `biz_lines` 可能未返回）且用户也没要改 → 不放进 body，让后端保持原值。

---

## `POST /v1/customers` — 创建客户

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  post "/v1/customers" \
  'body={"name":"...","biz_lines":["2046555212949643264"],"kyc":2,"nda":2}'
```

### 字段表（已对齐 Web 端表单）

| 字段 | 类型 | 必填 | UI 对应 | 说明 |
|------|------|------|---------|------|
| `name` | string | ✅ | 客户名称（红星） | — |
| `biz_lines` | array[string] | ✅ | 业务线（红星） | 业务线 ID 数组，**元素必须是字符串**（雪花 ID）；先通过 `/v1/biz_lines/keyword` 查得，`id` 字段取出后原样保留为字符串，**禁止 parseInt** |
| `short_name` | string | — | 客户简称 | — |
| `customer_code` | string | — | 客户编码 | — |
| `email` | array[string] | — | 客户邮箱（带 + / - 多值） | 数组；单值时也须传 `["x@x.com"]` |
| `register_address` | string | — | 注册地址 | — |
| `kyc` | int | — | 认证状态 | `1`=未完成（**默认**），`2`=已完成，`3`=已关户 |
| `nda` | int | — | NDA 状态 | `1`=未签署（**默认**），`2`=已签署 |
| `memo` | string | — | 备注（上限 500 字） | — |
| `contacts` | array[object] | — | 联系人信息（可增删多个） | 子字段见下方 |
| ~~`type`~~ | int | ❌ 不传 | **UI 未暴露** | **本 skill 不把 type 放进 body**，由后端默认处理；不追问用户，不进预览表 |

### 后端自动生成 / 不在 body 的字段

| 字段 | UI 对应 | 说明 |
|------|---------|------|
| `id` | 系统编号 | API 响应返回 |
| `status` | 客户状态（默认"正常"） | 后端自动，本 skill 创建后会立即调用 `/close`（实现草稿；对用户勿称「关户」） |
| `source_type` | 来源类型（"手动创建"） | 后端根据调用入口自动赋值（通常为 `1`=内部） |
| `source_id` | 客户来源编号 | 后端自动 |

### `contacts[]` 子字段（对齐 Web 表单"联系人信息"）

用户字段（POST 创建 / PUT add / PUT update 都要传）：

| 子字段 | 类型 | UI 对应 |
|--------|------|---------|
| `name` | string | 姓名 |
| `email` | string | 邮箱 |
| `phone` | string | 联系方式 |
| `role` | string | 角色 |
| `memo` | string | 备注 |

> **GET 返回会附加后端元数据**：`id` / `created_at` / `created_by` / `updated_at` / `updated_by` / `customer_id`。
>
> - **POST 创建** `contacts` 时：**不传**任何后端字段（创建本身就没有 id）
> - **PUT 修改** `contacts` 时：**必须保留 `id`**（`update` 和 `delete` 依赖它匹配目标联系人），但**剥离** `created_at` / `created_by` / `updated_at` / `updated_by` / `customer_id` 这些后端元数据
> - PUT 的 `contacts` 结构是 diff 对象，不是数组，详见下方「PUT 时 `contacts` 的 diff 结构」

### 响应

```json
{ "id": "新创建的客户 ID" }
```

---

## `PUT /v1/customers/{id}` — 修改客户

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  put "/v1/customers/{id}" \
  'path_params={"id":"123"}' \
  'body={"kyc":2,"memo":"更新备注"}'
```

### 路径参数

| 字段 | 说明 |
|------|------|
| `id` | 客户 ID（必填） |

### 请求 body（字段白名单）

仅以下字段可改；未传的字段保持原值。

| 字段 | 类型 | 说明 |
|------|------|------|
| `short_name` | string | 简称 |
| `customer_code` | string | 客户编码 |
| `biz_lines` | array[string] | 业务线 ID 数组（元素为字符串，同 POST）。⚠️ **PUT 必传**：后端不支持未传保持原值，未传时会触发 `ErrCustomerLastBizLine`（HTTP 200 + body.error_code 形式） |
| `email` | array[string] | 邮箱（数组） |
| `register_address` | string | 注册地址 |
| `nda` | int | `1`=未签署，`2`=已签署 |
| `kyc` | int | `1`=未完成，`2`=已完成，`3`=已关户 |
| `memo` | string | 备注 |
| `contacts` | object | 联系人 diff（**非整体替换**）。结构 `{"add":[...],"delete":[...],"update":[...]}`，详见下方「PUT 时 `contacts` 的 diff 结构」 |

### PUT 时 `contacts` 的 diff 结构

修改客户时 `contacts` 不是数组、不是整体替换，而是 diff 对象 `{add, delete, update}`：

| 子字段 | 类型 | 元素结构 | 说明 |
|-------|------|---------|------|
| `add` | array | `{name, email, phone, role, memo}` | 新增联系人，**不带 `id`** |
| `update` | array | `{id, name, email, phone, role, memo}` | 修改联系人，**必须带 `id`**（来自 GET baseline 的 `contacts[*].id`） |
| `delete` | array[string] | `["contactId1", "contactId2"]` | 删除联系人，**元素是 `contacts[*].id` 的字符串**，不是对象 |

**示例**：用户只改了一个已有联系人「李四」的 memo，新增/删除都没做：

```json
"contacts": {
  "add": [],
  "delete": [],
  "update": [
    {"id":"2046839899915968513","name":"李四","email":"lisi@test.com","phone":"13800000002","role":"技术","memo":"备联系人2"}
  ]
}
```

**diff 构造规则**（由 baseline + 用户意图计算）：

| 情况 | 归属 |
|------|------|
| 用户列表里有、baseline 里没有（按身份匹配） | `add` |
| baseline 里有、用户列表里没有 | `delete` |
| 两边都有（按 `id` 匹配）、字段不同 | `update` |
| 两边都有、字段相同 | 不进任何组 |

### 不可修改的字段

- `name` — 客户名称不支持改名
- `type` — 客户类型不支持改类型
- `status` — 由启用/禁用/关户端点管理，不走 PUT
- `source_type` / `source_id` — 后端自动管理

### 响应

返回完整客户对象，字段结构参见 `common-ns-masterdata/references/master-data-customer.md` 的客户列表响应字段。

---

## `POST /v1/customers/{id}/close` — close（内部使用；对用户称草稿）

> ⚠️ **本端点不作为用户可触发的动作**。本 skill 仅在「创建客户」流程的 Step 6 自动内联调用一次，实现「草稿」效果（技术上为 close；**对用户禁止使用「关户」「关闭客户」话术**）。
> 常规的启用/禁用用户动作请走对应端点 / skill。

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  post "/v1/customers/{id}/close" \
  'path_params={"id":"123"}' \
  'body={}'
```

### 路径参数

| 字段 | 说明 |
|------|------|
| `id` | 客户 ID |

### 请求 body

空对象 `{}`。

### 响应

通常为空或 `{"ok": true}`；以后端实际返回为准。

### 失败处理

若本 skill 在创建后调用 close 失败：
- **不得回滚创建**
- 必须把完整错误原文透传给用户
- 并提示（勿对用户说「关户」）：「客户已创建（ID=xxx），未能完成草稿置位：{错误}。请到管理端处理。」

---

## 枚举值速查

| 字段 | 值 | 语义 |
|------|----|------|
| ~~`type`~~ | — | 本 skill 不传；后端默认处理 |
| `kyc` | `1` | 未完成 |
| `kyc` | `2` | 已完成 |
| `kyc` | `3` | 已关户 |
| `nda` | `1` | 未签署 |
| `nda` | `2` | 已签署 |
| `status`（只读） | `1` | 草稿 |
| `status` | `2` | 待审核 |
| `status` | `3` | 可用 |
| `status` | `4` | 拒绝 |
| `status` | `5` | 冻结 |
| `status` | `6` | 关闭 |

## 字段对齐验证备忘

首次联调已完成（2026-04-22 集成测试），结论如下：

1. ✅ **不传 `type`**：后端落库为 `0`（不在 `1`/`2` 枚举值域内），不会拒绝——「不传 type」策略可行
2. ✅ **`email` 数组**：`["a@x.com"]` 单值 / 多值顺序均保留
3. ✅ **`contacts[]` 子字段名**：`name` / `email` / `phone` / `role` / `memo` 全部被后端接受
4. ✅ **创建后 `status=3`**（可用），必须立即调用 `/close`；close 成功后 `status=6`（关闭）。对用户沟通称「草稿」；勿称关户。
5. ✅ **close 端点 body 为空 `{}`** 即可

### 详情接口（`GET /v1/customers/{id}`）字段映射

| 详情字段名 | 对应 POST/PUT body 字段名 | 说明 |
|-----------|------------------------|------|
| `biz_type` | `biz_lines` | 结构 `[{id, name}]`。PUT 前从 `biz_type[*].id` 提取字符串数组作为 `biz_lines` 回填；预览表展示 `biz_type[*].name` |
| `code` | — | **详情响应只读字段**，后端自动分配（如 `C1303`）。POST body 没有此字段；PUT body 也没有（MCP descriptor 若标了 `code` 是 descriptor 误标，实际后端 API 无此参数） |
| `status` | — | 只读，由 enable/disable/close 端点管理 |
| `source_type` / `source_id` / `institution_id` / `addresses` / `desc` | — | 后端自管，不作为可改字段 |
| `contacts[*].id` | PUT `update[*].id` / `delete[*]` 要用 | 身份标识。PUT 的 `update` 和 `delete` 依赖它匹配；POST 不涉及 |
| `contacts[*]` 的 `created_at` / `created_by` / `updated_at` / `updated_by` / `customer_id` | — | 后端元数据。回填进 PUT body 前**必须剥离** |
| `created_at` / `created_by` / `updated_at` / `updated_by` | — | 后端自管；`updated_by` 当前有后端 bug，忽略即可 |

### 已知后端行为（需注意）

- **PUT 未传 `biz_lines` = 清空**：后端不实现「未传字段保持原值」——不传 `biz_lines` 会触发 `ErrCustomerLastBizLine`
- **部分业务错误走 HTTP 200 + `body.error_code`**：例如 `{"error_code":"ErrCustomerLastBizLine","error_message":"..."}`；处理时需同时覆盖 4xx/5xx **和** status=200 带 error_code 两种分支
- **终态客户 `biz_type` 视图过滤**：`kyc=3`（已关户）或 `status≠3` 时详情接口返回 `biz_type: []`，不代表存储层清空
- **多业务线返回顺序**：按 ID 升序排列，不保留 POST/PUT 的传入顺序
