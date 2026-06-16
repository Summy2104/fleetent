# 客户 (Customer) 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 依赖**：若参数含 `biz_line_id`/`biz_line`/`biz_line_ids`，先到父 skill `references/common-id-mapping.md` 取业务线字典；ID 翻名、11 个字典接口见同文档。

### `GET /v1/customers` — 客户列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/customers" \
  'query_params={"name": "客户名称", "status": 3, "page": 1, "page_size": 20}'
```

**请求参数**

| 字段 | 说明                                            |
|------|-----------------------------------------------|
| `code` | 客户编码                                          |
| `name` | 名称（模糊匹配）                                      |
| `institution_id` | 机构 ID                                         |
| `status` | 状态：`1`=草稿，`2`=待审核，`3`=可用，`4`=拒绝，`5`=冻结，`6`=关闭 |
| `source_type` | 来源类型：`1`=内部，`2`=Prime，`3`=中台                  |
| `source_id` | 来源 ID                                         |
| `biz_line_ids` | 业务线 ID                                        |
| `nda` | NDA 状态：`1`=未签署，`2`=已签署                        |
| `kyc` | KYC 状态：`1`=未完成，`2`=已完成，`3`=已关户                |
| `bd` | BD                                            |
| `kyc_type` | KYC 类型                                        |
| `kyc_pass_date_start` | KYC 通过时间-开始                                   |
| `kyc_pass_date_end` | KYC 通过时间-结束                                   |
| `kyc_review_date_start` | 最近 Review 时间-开始                               |
| `kyc_review_date_end` | 最近 Review 时间-结束                               |
| `director` | Director                                      |
| `ubo` | UBO                                           |
| `ar` | 授权签字人                                         |
| `register_region` | 注册地                                           |
| `sort` | 排序字段                                          |
| `customer_code` | 客户编码（同 `code`）                                |
| `project_id` | 项目 ID                                         |
| `type` | 客户类型：`1`=员工客户，`2`=供应商客户                       |
| `short_name` | 客户简称                                          |
| `page` | 页码                                            |
| `page_size` | 每页数量                                          |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 客户 ID |
| `code` | string | 客户 Code |
| `name` | string | 名称 |
| `short_name` | string | 简称 |
| `customer_code` | string | 客户编码 |
| `status` | int | 状态：`1`=草稿，`2`=待审核，`3`=可用，`4`=拒绝，`5`=冻结，`6`=关闭 |
| `type` | int | 客户类型：`0`=默认，`1`=员工客户，`2`=供应商客户 |
| `kyc` | int | KYC 状态：`1`=未完成，`2`=已完成，`3`=已关户 |
| `nda` | int | NDA 状态：`1`=未签署，`2`=已签署 |
| `source_type` | int | 来源类型：`1`=内部，`2`=Prime，`3`=中台 |
| `source_id` | string | 来源 ID |
| `institution_id` | string | 机构 ID |
| `register_address` | string | 注册地址 |
| `memo` | string | 备注 |
| `email` | array[string] | 邮箱列表 |
| `biz_type` | array[{id,name}] | 业务类型列表 |
| `contacts` | array | 联系人列表 |
| `addresses` | array | 地址列表 |
| `desc` | string | 描述 |
| `created_at` | string | 创建时间（UTC，展示转 UTC+8） |
| `updated_at` | string | 更新时间（UTC，展示转 UTC+8） |

---

### `GET /v1/customers/{id}/kyc` — 客户 KYC 详情

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/customers/{id}/kyc" \
  'path_params={"id": "客户ID"}'
```

**路径参数**

| 字段 | 说明 |
|------|------|
| `id` | 客户 ID |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `customer_name` | string | 客户名称 |
| `kyc` | array | KYC 信息列表，见下方字段说明 |
| `type` | int | 客户类型：`0`=默认，`1`=员工客户，`2`=供应商客户 |

**`kyc[]` 列表项字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| `kyc_type` | int | KYC 类型：`1`=Counterparty DD，`2`=KYC，`3`=Service Provider DD |
| `kyc_pass_date` | string | KYC 通过时间（UTC，展示转 UTC+8） |
| `kyc_review_date` | string | 最近 Review 时间（UTC，展示转 UTC+8） |
| `kyc_package_url` | string | KYC 材料链接 |
| `register_region` | string | 注册地 |
| `bd` | array[string] | BD |
| `director` | array[string] | Director |
| `ubo` | array[string] | UBO |
| `ar` | array[{name, email}] | 授权签字人列表 |

---

### `GET /v1/customers/keyword` — 客户名称列表（ID 查名称）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/customers/keyword" \
  'query_params={"types": [1, 2]}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `types` | 客户类型数组：`1`=员工客户，`2`=供应商客户 |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 客户 ID |
| `name` | string | 名称 |
| `code` | string | 客户 Code |
| `short_name` | string | 简称 |
| `type` | int | 客户类型：`1`=员工客户，`2`=供应商客户 |
