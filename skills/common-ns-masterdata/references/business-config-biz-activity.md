# 业务配置 - 业务线与行为 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

## 业务线 (Biz Lines)

### GET /v1/biz_lines — 业务线列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_lines" \
  'query_params={"name": "业务线名称", "status": 1, "page": 1, "page_size": 20}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|---|---|---|
| id | string | 业务线 ID |
| name | string | 业务线名称（模糊匹配） |
| type | int | 父子类型：`1`=父业务线，`2`=子业务线，`3`=独立父业务线及子业务线 |
| pid | string | 父业务线 ID |
| status | int | 状态：`1`=启用，`2`=禁用 |
| company | string | 公司主体 |
| side_type | int | 资金资产端类型：`1`=资金端，`2`=资产端-通用类，`4`=资产端-借贷类，`5`=资产端-挖矿类，`6`=资产端-兑换类，`7`=资产端-理财 |
| department_id | string | 部门 ID |
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**（`list` 列表项）

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | string | 业务线 ID |
| name | string | 业务线名称 |
| abbreviation | string | 业务线简称 |
| pid | string | 父业务线 ID |
| p_name | string | 父业务线名称 |
| type | int | 父子类型：`1`=父业务线，`2`=子业务线 |
| status | int | 状态：`1`=启用，`2`=禁用 |
| side_type | int | 资金资产端类型：`1`=资金端，`2`=资产端-通用类，`4`=资产端-借贷类，`5`=资产端-挖矿类，`6`=资产端-兑换类，`7`=资产端-理财 |
| companies | array | 关联公司主体列表，每项包含 `id`、`name` |
| department | object | 所属部门，包含 `id`、`name` |
| email_group | array[string] | 邮件组 |
| owners | array | 负责人列表，每项包含 `id`、`nickname`、`email` |
| created_at | string | 创建时间（UTC，展示转 UTC+8） |
| updated_at | string | 更新时间（UTC，展示转 UTC+8） |

**响应字段**（顶层）

| 字段名 | 类型 | 说明 |
|---|---|---|
| list | array | 业务线列表 |
| page_info | object | 分页信息 |

---

### GET /v1/biz_lines/keyword — 业务线名称列表（ID 查名称，全量）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_lines/keyword" \
  'query_params={"status": 1}'
```

**请求参数**：同业务线列表（见上方），返回简化信息，适合 ID 查名称场景。

---

## 行为 (Activity)

### GET /v1/activity — 行为列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/activity" \
  'query_params={"name": "行为名称", "attr": 3, "page": 1, "page_size": 20}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|---|---|---|
| id | string | 行为 ID |
| name | string | 行为名称（模糊匹配） |
| business_line_ids | array[string] | 业务线 ID 列表 |
| attr | int | 行为属性：`1`=子行为，`2`=子行为可单独使用，`3`=父行为可关联路径 |
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**（`list` 列表项）

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | string | 行为 ID |
| name | string | 行为名称 |
| memo | string | 备注 |
| attr | int | 行为属性：`1`=子行为，`2`=子行为可单独使用，`3`=父行为可关联路径 |
| business_lines | array | 关联业务线列表，每项包含 `id`、`name`、`type` |
| can_relate_others | bool | 是否可关联其他行为 |
| participant_type | string | 参与方向：`inbound`=入账方，`outbound`=出账方 |
| required_same_currency | bool | 是否需要同币种 |
| role | int | 角色：`1`=付款方，`2`=收款方，`3`=付款方和收款方 |
| role_when_asset | int | 资产端角色 |
| role_when_funding | int | 资金端角色 |
| parent_activities | array | 父活动列表 |
| sub_activities | array | 子活动列表 |

**响应字段**（顶层）

| 字段名 | 类型 | 说明 |
|---|---|---|
| list | array | 行为列表 |
| page_info | object | 分页信息 |

---

### GET /v1/activity/{id} — 行为详情

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/activity/{id}" \
  'path_params={"id": "act-123"}'
```

**Path 参数**

| 参数名 | 类型 | 说明 |
|---|---|---|
| id | string | 行为 ID（必填） |

**响应字段**

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | string | 行为 ID |
| name | string | 行为名称 |
| memo | string | 备注 |
| attr | int | 行为属性：`1`=子行为，`2`=子行为可单独使用，`3`=父行为可关联路径 |
| business_lines | array | 关联业务线列表，每项包含 `id`、`name`、`type` |
| can_relate_others | bool | 是否可关联其他行为 |
| participant_type | string | 参与方向：`inbound` / `outbound` |
| required_same_currency | bool | 是否需要同币种 |
| role | int | 角色：`1`=付款方，`2`=收款方，`3`=付款方和收款方 |
| role_when_asset | int | 资产端角色 |
| role_when_funding | int | 资金端角色 |
| role_when_exchange_asset | int | 交易所资产端角色 |
| role_when_ming_asset | int | 挖矿资产端角色 |
| role_when_sp_asset | int | SP 资产端角色 |
| role_when_wealth_asset | int | 财富资产端角色 |
| parent_activities | array | 父活动列表 |
| sub_activities | array | 子活动列表 |
| pids | array[string] | 父级活动 ID 列表 |

---

### GET /v1/behavior/label — 行为名称列表（ID 查名称）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" get "/v1/behavior/label"
```

**请求参数**：无

**响应字段**

| 字段名 | 类型 | 说明 |
|---|---|---|
| list | array | 行为列表 |
| list[].id | string | 行为 ID |
| list[].name | string | 行为名称 |
