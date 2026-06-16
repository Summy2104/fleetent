# 主体 (Company) 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

### `GET /v1/companies/search` — 主体列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/companies/search" \
  'query_params={"name": "公司名称", "status": 1, "page": 1, "page_size": 20}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `name` | 名称（模糊匹配） |
| `valid_date` | 有效日期 |
| `signatory` | 签字人 |
| `belonging` | 归属集团：`0`=NS，`1`=AA，`2`=ARM，`3`=Other |
| `former_name` | 曾用名 |
| `registered_number` | 注册号 |
| `status` | 状态：`0`=停用，`1`=启用 |
| `registered_address` | 注册地址 |
| `registered_region` | 注册地区 |
| `sort` | 排序字段，支持 `register_date` / `updated_at`，格式为 `"字段"` 或 `"字段 asc"` / `"字段 desc"` |
| `ubo_name` | UBO 名称（模糊匹配） |
| `page` | 页码 |
| `page_size` | 每页数量 |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 主体 ID |
| `name` | string | 名称 |
| `belonging` | int | 归属集团：`0`=NS，`1`=AA，`2`=ARM，`3`=Other |
| `status` | int | 状态：`0`=停用，`1`=启用 |
| `is_valid` | bool | 是否有效 |
| `registered_address` | string | 注册地址 |
| `registered_region` | string | 注册地区 |
| `registered_number` | string | 注册号 |
| `registered_date` | string | 注册日期 |
| `valid_start_date` | string | 有效期开始 |
| `valid_end_date` | string | 有效期结束 |
| `signatory` | array | 签字人列表 |
| `former_names` | array | 曾用名列表 |
| `ubo_names` | array | UBO 名称列表 |
| `memo` | string | 备注 |
| `contract_count` | string | 合同数量 |
| `fiat_company_account_count` | string | 法币公司账户数 |
| `digital_coin_account_count` | string | 数币账户数 |
| `created_at` | string | 创建时间（UTC，展示转 UTC+8） |
| `updated_at` | string | 更新时间（UTC，展示转 UTC+8） |

---

### `GET /v1/companies/keyword` — 主体名称列表（ID 查名称，全量）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/companies/keyword" \
  'query_params={"page": 1, "page_size": 100}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `page` | 页码 |
| `page_size` | 每页数量 |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 主体 ID |
| `name` | string | 名称 |
| `code` | string | 编码，格式为「名称-注册地区-状态」 |
