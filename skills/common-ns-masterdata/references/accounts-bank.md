# 账户管理 - 银行账户 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

## 银行账户

### `GET /v1/accounts/bank` - 银行列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/accounts/bank" \
  'query_params={"name": "中国银行", "page": 1, "page_size": 20}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 银行 ID |
| name | string | 银行名称 |
| relationship_manager | string | 客户经理 |
| email | string | 邮箱 |
| phone | string | 电话 |
| swift_code | string | SWIFT 代码 |
| aba_number | string | ABA 编号 |
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**

顶层结构：`list`（列表）、`page_info`（分页信息）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | string | 银行 ID |
| name | string | 银行名称 |
| code | string | 银行编码 |
| account_number | string | 中转行账号 |
| address | string | 地址 |
| approve_reason | string | 审核原因 |
| approve_status | int | 审核状态：`1` 审核通过，`2` 审核拒绝 |
| branch_code | string | 分行代码 |
| branch_name | string | 分行名称 |
| contacts | string | 联系人 |
| country | string | 国家 |
| currency | array | 币种列表 |
| email | string | 邮箱 |
| fedwire_number | string | Fedwire 编号 |
| iban_number | string | 中转行 IBAN |
| iin_or_bin | string | IIN/BIN |
| intermediary_bank | array | 中转行列表 |
| phone | string | 电话 |
| relationship_manager | string | 客户经理 |
| remarks | string | 备注 |
| sort_code | string | Sort Code |
| swift_code | string | SWIFT 代码 |

---

### `GET /v1/accounts/bank/{id}` - 银行详情

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/accounts/bank/{id}" \
  'path_params={"id": "123"}'
```

**路径参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| id | string | 银行 ID |

**响应字段**

响应字段与银行列表列表项相同，额外包含：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| aba_number | string | ABA 编号 |

---

### `GET /v1/accounts/bank/label` - 银行名称列表（ID 查名称）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" get "/v1/accounts/bank/label"
```

无请求参数。

**响应字段**

顶层结构：`list`（列表）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | string | 银行 ID |
| name | string | 银行名称 |
