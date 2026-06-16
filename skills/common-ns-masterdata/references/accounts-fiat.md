# 账户管理 - 法币账户 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 依赖**：若参数含 `biz_line_id`/`biz_line`/`biz_line_ids`，先到父 skill `references/common-id-mapping.md` 取业务线字典；ID 翻名、11 个字典接口见同文档。

## 法币账户

账户类型路径规则：将下方路径中的 `{type}` 替换为 `company` / `customer` / `employee` / `supplier`

### `GET /v1/accounts/fiat/account_manager/list` - 账户管理员列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" get "/v1/accounts/fiat/account_manager/list"
```

无请求参数。

**响应字段**

顶层结构：`list`（列表）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | string | 用户 ID |
| nickname | string | 昵称 |
| email | string | 邮箱 |

---

### `GET /v1/accounts/fiat/{type}/account/list` - 法币账户列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/accounts/fiat/{type}/account/list" \
  'query_params={"entity_id": "456", "page": 1, "page_size": 20}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| entity_id | string | 主体 ID |
| account_name | string | 账户名称 |
| business_unit | string | 业务单元 |
| account_manager | string | 账户管理员 |
| bank_id | string | 银行 ID |
| platform_id | string | 平台 ID |
| account_id | string | 账户 ID |
| type | int | 账户类型：`1` 公司账户，`2` 客户账户，`3` 员工账户，`4` 供应商账户 |
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**

顶层结构：`list`（列表）、`page_info`（分页信息）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | string | 账户 ID |
| account_name | string | 账户名称 |
| account_address | string | 账户地址 |
| account_number_list | array | 账号列表 |
| account_manager | array\<{id, name}\> | 账户管理员列表 |
| active | bool | 是否激活 |
| bank.name | string | 银行名称（完整名称，含 "CLOSED" 等后缀，禁止拆分或推断状态） |
| bank.swift_code | string | SWIFT 代码 |
| bank.approve_status | int | 银行审核状态：`0` 待审核，`1` 审核通过，`2` 审核拒绝 |
| business_unit | string | 业务单元 |
| customer | object\<{id, name}\> | 客户信息 |
| entity | object\<{id, name}\> | 主体信息 |
| platform | object\<{id, name}\> | 平台信息 |
| remark | string | 备注 |
| type | int | 账户类型：`1` 公司账户，`2` 客户账户，`3` 员工账户，`4` 供应商账户 |

---

### `GET /v1/accounts/fiat/{type}/account/{id}/account_numbers` - 账号列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/accounts/fiat/{type}/account/{id}/account_numbers" \
  'path_params={"id": "789"}' \
  'query_params={"currency": "USD", "page": 1}'
```

**路径参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 账户 ID |

**请求参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| account_number | string | 账号 |
| currency | string | 币种 |
| swift_code | string | SWIFT 代码 |
| aba_number | string | ABA 编号 |
| reference | string | 参考号 |
| tag | string | 标签 |
| business_line_id | string | 业务线 ID |
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**

顶层结构：`list`（列表）、`page_info`（分页信息）

---

## 辅助查询

### `GET /v1/accounts/platform/label` - 平台名称列表（ID 查名称）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" get "/v1/accounts/platform/label"
```

无请求参数。

**响应字段**

顶层结构：`list`（列表）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | string | 平台 ID |
| name | string | 平台名称 |
