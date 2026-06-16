# 合同、数字货币、国家 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 依赖**：若参数含 `biz_line_id`/`biz_line`/`biz_line_ids`，先到父 skill `references/common-id-mapping.md` 取业务线字典；ID 翻名、11 个字典接口见同文档。

## 合同 (Contract)

### `GET /v1/contract/list` — 合同列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/contract/list" \
  'query_params={"status": 6, "project_id": "123", "page": 1, "page_size": 20}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `department_id` | 部门 ID |
| `status` | 合同状态：`1`=审批中，`2`=审批完成，`3`=已作废，`5`=待签署，`6`=已签署，`7`=履约中，`8`=履约完成，`9`=手工作废 |
| `number` | 合同编号 |
| `business_line_id` | 业务线 ID |
| `project_id` | 项目 ID |
| `company_id` | 签约主体 ID |
| `customer_id` | 客户 ID |
| `submitted_by` | 提交人 |
| `signed_email_by` | 签署人邮箱 |
| `begin_date` | 合同生效时间 |
| `end_date` | 合同截止时间 |
| `process_instance_number` | 流程编号 |
| `type` | 合同类型 |
| `email_title` | 邮件标题 |
| `presign` | 是否预签署 |
| `name` | 合同名称 |
| `data_type` | 数据类型：`1`=正式数据，`2`=测试数据 |
| `starter_id` | 发起人 ID |
| `major_category` | 主类别：`1`=业务合同，`2`=非业务合同 |
| `minor_category_id` | 子类别 ID |
| `notify_id` | 通知人 ID |
| `signed_date_start` | 签署时间-开始 |
| `signed_date_end` | 签署时间-结束 |
| `sign_type` | 签名类型：`1`=电子签名，`2`=手写签名，`3`=混合签名 |
| `page` | 页码 |
| `page_size` | 每页数量 |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 合同 ID |
| `name` | string | 合同名称 |
| `number` | string | 合同编号 |
| `status` | int | 状态：`1`=审批中，`2`=审批完成，`3`=已作废，`5`=待签署，`6`=已签署，`7`=履约中，`8`=履约完成，`9`=手工作废 |
| `major_category` | int | 主类别：`1`=业务合同，`2`=非业务合同 |
| `minor_category` | object {id,name} | 子类别 |
| `company` | object {id,name} | 签约主体 |
| `customer` | object {id,name} | 客户 |
| `project` | object {id,name} | 项目 |
| `department` | object {id,name} | 部门 |
| `business_line` | array[{id,name}] | 业务线列表 |
| `initiated_by` | object {id,name} | 发起人 |
| `submitted_by` | object {id,name} | 提交人 |
| `signed_by` | object | 签署人 |
| `begin_date` | string | 生效时间（纯日期，原样展示） |
| `end_date` | string | 截止时间（纯日期，原样展示） |
| `signed_date` | string | 签署时间（纯日期，原样展示） |
| `sign_type` | int | 签名类型：`1`=电子签名，`2`=手写签名，`3`=混合签名 |
| `email_title` | string | 邮件标题 |
| `process_instance_number` | string | 流程编号 |
| `is_long_term` | bool | 是否长期合同 |

---

### `GET /v1/contract/type/list` — 合同类型列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/contract/type/list" \
  'query_params={"page": 1, "page_size": 50}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `name` | 名称（模糊匹配） |
| `department_id` | 部门 ID |
| `page` | 页码 |
| `page_size` | 每页数量 |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 类型 ID |
| `name` | string | 名称 |
| `code` | string | 编码 |
| `status` | int | 状态 |
| `remark` | string | 备注 |
| `department` | array[{id,name}] | 适用部门列表 |
| `created_at` | string | 创建时间（UTC，展示转 UTC+8） |
| `updated_at` | string | 更新时间（UTC，展示转 UTC+8） |

---

## 数字货币 (Coins)

### `GET /v1/coins/mo` — 数币列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/coins/mo" \
  'query_params={"name": "USDT"}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `name` | 币种名称（过滤） |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 币种代码 |
| `mo_id` | string | MO 内部 ID |
| `name` | string | 币种名称 |

---

### `GET /v1/coins/nets` — 数币网络（Chain）列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/coins/nets" \
  'query_params={"coin": "USDT"}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `coin` | 币种 ID（过滤） |
| `name` | 网络名称（过滤） |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 网络 ID |
| `name` | string | 网络名称 |

---

## 国家列表

### `GET /v1/countries` — 全量国家数据

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" get "/v1/countries"
```

**请求参数**：无

**响应字段** — `list[]`（返回全量国家数据）
