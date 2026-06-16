# 数币账户 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 依赖**：若参数含 `biz_line_id`/`biz_line`/`biz_line_ids`，先到父 skill `references/common-id-mapping.md` 取业务线字典；ID 翻名、11 个字典接口见同文档。

> **🔗 查询链 #5**：按链+币种筛选数币账户时，先在父 skill `references/common-query-chains.md#链-5` 查 chain_id/coin_id 的获取流程。

## 地址标签

### `GET /v1/accounts/address/tags` - 指定账户虚拟货币地址标签列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/accounts/address/tags" \
  'query_params={"account_id": "xxx"}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| account_id | string | 数币账户 ID |

**响应字段**

顶层结构：`list`（地址标签列表）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| list | array | 地址标签列表 |

---

### `GET /v1/accounts/address/tags/list` - 所有地址标签列表（全量）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" get "/v1/accounts/address/tags/list"
```

无请求参数。

**响应字段**

顶层结构：`list`（地址标签列表）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| list | array | 地址标签列表 |

---

## 数币账户

### `GET /v1/accounts/digital_coin/category` - 数币账户平台列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" get "/v1/accounts/digital_coin/category"
```

无请求参数。

**响应字段**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| market | array | 平台/交易所列表 |

---

### `POST /v1/accounts/digital_coin` - 数币账户信息列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  post "/v1/accounts/digital_coin" \
  'body={"market_id": "xxx", "page": 1, "page_size": 20}'
```

**请求参数（body）**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| account | string | 账户名称 |
| account_id | string | 母账户 ID（仅支持母账户 ID 查询） |
| children | - | 子账户（具体类型参考接口） |
| childrens | string | 子账户名称 |
| coin | string | 币种 |
| company_id | string | 公司/主体 ID |
| market_id | string | 平台/交易所 ID |
| project_no | string | 项目号 |

**响应字段**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| account | array/object | 数币账户信息 |

---

## 白名单账户

> **查询白名单地址的完整流程**
>
> 用户通常只知道账户名，需要按以下步骤组装参数：
>
> **Step 1 — 通过账户名查 account_id**
> 调用 `POST /v1/accounts/digital_coin`，传 `{"account": "<账户名>"}` → 取返回的 `id` 作为 `account_id`，`market_id` 备用。
>
> **Step 2 — 并行补全剩余参数**
> - `address_tag`：调用 `GET /v1/accounts/address/tags?account_id=<id>` 获取该账户实际拥有的标签列表，从中取值
> - `chain_id`：调用 `GET /v1/coins/nets`，按链名称找对应的数字 id（如 ACA → `"59"`）
> - `coin_id`：调用 `GET /v1/coins/mo`，按币种符号找对应的 `mo_id`（如 USDT → `"379"`）
> - `market`：调用 `GET /v1/accounts/digital_coin/category`，按 `market_id` 找对应的平台名称字符串（如 35 → `"Cobo MPC"`）
>
> **Step 3 — 查询白名单地址**
> 用以上参数调用 `POST /v1/account/whitelist/symbol/address`。
>
> **注意事项：**
> - `chain_id` 和 `coin_id` 均为**数字字符串 ID**，不能直接传链名或币种符号，必须先查表转换
> - `market` 传平台**名称**字符串（如 `"Cobo MPC"`），不是 market_id 数字；可从账户信息的 market_id 通过 `/v1/accounts/digital_coin/category` 反查
> - `address_tag` 必须从该账户实际拥有的标签中取（`/address/tags` 接口），不可随意传字符串
>
> **用户未提供 address_tag / coin_id 时的处理策略（重要）：**
> 当用户只说"查询某账户在某网络的地址"，不知道 address_tag 和 coin_id 时，**不得**直接用不完整参数查询（会返回空）。应按以下顺序处理：
> 1. 调用 `GET /v1/accounts/address/tags?account_id=<id>` 获取该账户所有地址标签
> 2. 若只有一个标签，直接使用；若有多个，向用户展示并询问选哪个
> 3. coin_id 若未指定，可先不传（省略该字段）；market 可从账户的 market_id 反查后传入
> 4. 以上参数齐全后再发起查询

### `POST /v1/account/whitelist/symbol/address` - 数币账户白名单地址查询

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  post "/v1/account/whitelist/symbol/address" \
  'body={"account_id": "xxx", "coin_id": "xxx"}'
```

**请求参数（body）**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| account_id | string | 数币账户 ID |
| address_tag | string | 地址标签名称（字符串，如 "测试"） |
| chain_id | string | 链 ID（数字字符串，非链名称，可从 `/v1/coins/nets` 获取） |
| coin_id | string | 币种 ID（数字字符串，非币种符号，可从 `/v1/coins/mo` 获取） |
| id | string | 白名单账户主键 ID |
| market | string | 平台/交易所名称（字符串，如 "Cobo MPC"） |

**响应字段**

顶层结构：`list`（白名单地址列表）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| address | string | 地址 |
| address_tag | array | 地址标签列表 |
| memo | string | Memo / Tag |
| remark | string | 备注 |
