# 项目 (Project) 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 依赖**：若参数含 `biz_line_id`/`biz_line`/`biz_line_ids`，先到父 skill `references/common-id-mapping.md` 取业务线字典；ID 翻名、11 个字典接口见同文档。

### `GET /v1/projects` — 项目列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/projects" \
  'query_params={"status": 2, "biz_line": "1813912038663606273", "page": 1, "page_size": 20}'
```

**请求参数**

| 字段 | 说明 |
|------|------|
| `no` | 项目号（**支持模糊匹配**，如 `TR036` 可匹配所有 TR036xx 项目） |
| `status` | 状态：`1`=筹备中，`2`=运营中，`3`=已结束 |
| `biz_line` | 业务线 **ID**（非名称；先查 `/v1/biz_lines` 获取 id，再传入此字段） |
| `id` | 项目 ID |
| `ids` | 项目 ID 列表 |
| `contains_bm_funds` | 是否包含 BM 资金：`1`=不包含，`2`=包含 |
| `not_biz_lines` | 排除的业务线 |
| `cooperate_company_name` | 合作公司名称 |
| `company_id` | 签署主体 ID |
| `project_desc` | 项目简称（**支持模糊搜索**；用户查询"名称含 XX"时使用此字段，非 `no`） |
| `former_project_nos` | 曾用项目号 |
| `page` | 页码 |
| `page_size` | 每页数量 |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 项目 ID |
| `no` | string | 项目号 |
| `project_desc` | string | 项目简称 |
| `status` | int | 状态：`1`=筹备中，`2`=运营中，`3`=已结束 |
| `business_line_id` | string | 业务线 ID |
| `business_line_name` | string | 业务线名称 |
| `contains_bm_funds` | int | 是否包含 BM 资金：`1`=不包含，`2`=包含 |
| `company` | array[{id,name}] | 签署主体列表 |
| `cooperate_company` | array[{id,name}] | 合作公司列表 |
| `owners` | array | 负责人列表 |
| `former_project_nos` | string | 曾用项目号 |
| `remark` | string | 备注 |
| `start_time` | string | 开始时间（UTC，展示转 UTC+8） |
| `end_time` | string | 结束时间（UTC，展示转 UTC+8） |
| `created_at` | string | 创建时间（UTC，展示转 UTC+8） |
| `updated_at` | string | 更新时间（UTC，展示转 UTC+8） |

---

### `GET /v1/projects/labels` — 项目名称列表（ID 查名称）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/projects/labels" \
  'query_params={"status": 2}'
```

**请求参数**（同项目列表）

| 字段 | 说明 |
|------|------|
| `no` | 项目号（**支持模糊匹配**，如 `TR036` 可匹配所有 TR036xx 项目） |
| `status` | 状态：`1`=筹备中，`2`=运营中，`3`=已结束 |
| `biz_line` | 业务线 **ID**（非名称；先查 `/v1/biz_lines` 获取 id，再传入此字段） |
| `id` | 项目 ID |
| `ids` | 项目 ID 列表 |
| `contains_bm_funds` | 是否包含 BM 资金：`1`=不包含，`2`=包含 |
| `cooperate_company_name` | 合作公司名称 |
| `company_id` | 签署主体 ID |
| `project_desc` | 项目简称（**支持模糊搜索**；用户查询"名称含 XX"时使用此字段） |
| `former_project_nos` | 曾用项目号 |
| `page` | 页码 |
| `page_size` | 每页数量 |

**响应字段** — `list[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `value` | string | 项目 ID |
| `label` | string | 项目号 |
| `project_desc` | string | 项目简称 |
| `code` | string | 编码 |
