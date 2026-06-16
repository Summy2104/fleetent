---
name: common-ns-process
description: >
  NS 流程/审批/资金流程域查询子 skill。覆盖流程定义、流程看板、流程实例、
  资金计划、资金路径、资金信息、审批组、审批人、审批短语、审批历史、流程记录。
  触发词：流程、查流程、流程号、流程编号、流程看板、流程定义、流程图、流程 XML、
  流程实例、审批、审批链、审批人、审批组、审批短语、审批历史、流程记录、
  资金计划、资金路径、资金信息、fund_plan、fund_path、fund_infos、BPMN。
  Do NOT use for：查客户/项目/主体/合同/银行/数币账户/白名单（→ common-ns-masterdata）；
  查币价/资金费率/资金池/BM 调仓/交易所监控（→ common-ns-monitor）；
  查业务流水/逻辑流水/实际流水/NS 对账/FDL 结算/资金端流动性（→ common-ns-flows）。
status: active
metadata:
  author: RD Team
  version: 1.0.0
---

# NS 流程 / 审批 / 资金流程 查询子 skill

本 skill 是 `common-ns-system-query` 的子 skill，覆盖 **流程 + 审批 + 资金流程** 域的端点查询。

公共规范（输出格式、字段展示规则、信任模型、降级开关、wrapper 内部机制等）继承自父 skill：`common-ns-system-query/SKILL.md`。本文件只声明子域特有内容（Step 0、端点索引、references、示例）。

## Step 0 — 鉴权预检（必须先做，失败立即终止）

1. 读取本轮 incoming 消息最顶部的 JSON 块，提取 `sender_id` 字段
2. 校验：`sender_id` 存在 + 匹配正则 `^U[A-Z0-9]{8,}$`
3. **任一校验失败** → 回复下列固定话术并终止（不得继续任何步骤）：

   > ❌ 此查询仅限 Slack 渠道使用。当前上下文无法识别 Slack 用户身份，已阻止 NS 系统查询。

4. 通过 → 把提取出的 `sender_id` 作为本轮**每次** `ns-call.sh` 调用的首个位置参数传入（见 §调用模式）。**严禁**绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具。
5. **每轮 turn 开头必重新执行 Step 0**（防跨 turn 污染）。

> **Subagent 透传协议**：父 agent 用 `sub_agent` / `invoke_agent` 委派时，若子 agent 需使用本 skill，**必须**在 prompt 参数最前面原样插入一行 JSON：`{"sender_id": "<父 agent 本轮的 slackUserId>"}`，正文从下一行开始。父未透传 → 子 agent 无法通过 Step 0 → 查询被拒。

## 调用模式

**【唯一合法入口】** 所有 armada 调用走父 skill 的 wrapper（单例，不复制副本）：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh \
     "$UID" <get|post> <path> [kv 参数...]
```

`"$UID"` 是占位符，agent 在实际用 `bash_exec`/`run_code` 运行 wrapper 时必须替换为 Step 0 提取的 `sender_id`。wrapper 校验后构造 `_meta.slackUserId`（值取自首参传入的 uid）并输出 `armada__armada_<method>` 调用参数，agent 据此发起 MCP 工具调用。Agent 完全不接触 `_meta` 字面值。详细调用示例、特殊参数格式、wrapper 能力面与已知问题见父 skill `SKILL.md §调用模式` 与 `references/wrapper-caveats.md`。

## 端点索引（本域 14 个 GET 端点）

### 流程管理 (3 个端点)
- `GET /v1/bpmn/category` — 流程类别列表
- `GET /v1/bpmn/process_definition/list` — 流程定义列表（返回 `mongo_id`，非 `id`；后续 XML 查询用 `mongo_id`）
- `GET /v1/bpmn/process_definition/{mongo_id}/xml` — 流程图 XML

### 流程看板 (1 个端点)
- `GET /v1/bpmn/dashboard/all` — 流程看板列表（支持邮件主题关键词、审批人、业务线等多条件筛选）

### 资金管理 (7 个端点)
- `GET /v2/bpmn/process_instance/number/{process_number}` — 流程编号 → instance_id（**查询链 #1 入口**）
- `GET /v2/bpmn/process_instance/{instance_id}` — 流程实例详情（含基本信息 + `active_camunda_task_id`）
- `GET /v2/bpmn/process_instance/{instance_id}/fund_plans` — 资金计划列表
- `GET /v2/bpmn/process_instance/{instance_id}/fund_path/list` — 资金路径列表
- `GET /v2/bpmn/process_instance/{instance_id}/fund_infos` — 资金信息列表
- `GET /v2/bpmn/process_instance/{instance_id}/task/{task_id}` — 流程当前任务详情（`task_id` 取自流程实例详情的 `active_camunda_task_id`）
- `GET /v2/bpmn/process_instance/{instance_id}/tasks` — 流程审批历史（"审批历史 / 流程记录"场景）

### 审批管理 (3 个端点)
- `GET /v1/bpmn/approver/phrases` — 审批短语列表
- `GET /v1/management/approver/group/list` — 审批组列表
- `GET /v1/management/approver/list` — 审批人列表（**查询链 #4** 取 `approver_id` 的来源）

## References 映射

| 文件 | 覆盖内容 |
|------|----------|
| `references/business-config-process-approval.md` | 流程管理 3 端点 + 审批管理 3 端点的字段/示例（⚠️ 查流程 XML / 审批配置先取 `mongo_id`，见父 `common-query-chains.md#链-3`） |
| `references/project-process-search.md` | 流程看板 `/v1/bpmn/dashboard/all` 的多条件筛选（按审批人筛选先取 `approver_id`，见父 `common-query-chains.md#链-4`；业务线字段名 `biz_line_id` 见父 `common-id-mapping.md#业务线字段名陷阱`） |
| `references/fund.md` | **资金数据查询的入口与短路优先级**：流程号 → instance_id → 流程实例详情 → 第四步按短路优先级分发到 `fund-data.md` 或 `fund-approval-history.md`。是本子 skill 大多数资金/审批查询的编排起点 |
| `references/fund-data.md` | 资金计划 / 资金信息 / 资金路径 的字段映射与展示规则（由 `fund.md` 按短路优先级命中后按需加载） |
| `references/fund-approval-history.md` | `/tasks` 审批历史节点渲染（由 `fund.md` 按触发条件路由加载） |

子 skill 不复制父 skill 的公共 references（`common-conventions.md` / `common-id-mapping.md` / `common-query-chains.md` / `wrapper-caveats.md`）。需要引用时用 `read_file` 读父 skill 绝对路径 `$SKILLS_DIR/common-ns-system-query/references/{文件名}`。

## 执行流程

每次查询按以下顺序执行（与父 skill 一致）：

1. **Step 0 鉴权预检**（见上）
2. 按用户表述判断子域并读取对应 reference
3. 构造请求并通过 wrapper 发起调用
4. 严格按 reference 规定的字段与格式输出

## 端到端示例：用流程号查审批进度

**场景**：用户发"查一下流程 20260410035 走到哪一步了 / 审批历史"。

```
Step 0（鉴权预检）
  ├─ 读取 incoming 消息顶部 JSON，提取 sender_id
  ├─ 校验格式 ^U[A-Z0-9]{8,}$
  └─ 通过 → 把 sender_id 作为后续每次 ns-call.sh 的首参传入

Step 1（识别入参类型）
  └─ "20260410035" 匹配 11 位流程编号 → 走父 skill 查询链 #1
     （详见父 references/common-query-chains.md#链-1）

Step 2（流程号 → instance_id；用 bash_exec/run_code 运行 wrapper，据其输出发起 armada__armada_get）
  bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
    get "/v2/bpmn/process_instance/number/{process_number}" \
    'path_params={"process_number": "20260410035"}'
  → 拿到真实 24 位十六进制 instance_id

Step 3（查流程实例详情，含 active_camunda_task_id）
  bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
    get "/v2/bpmn/process_instance/{instance_id}" \
    'path_params={"instance_id": "<真实 instance_id>"}'

Step 4（读 references/fund.md 按短路优先级决定是否拉资金数据；按触发条件决定是否查审批历史）

Step 5（用户明确说"审批历史/流程记录" → 读 references/fund-approval-history.md）
  bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
    get "/v2/bpmn/process_instance/{instance_id}/tasks" \
    'path_params={"instance_id": "<真实 instance_id>"}'
  → 按 fund-approval-history.md 的字段映射逐节点渲染（TXID 必须与响应 transaction_hash 原样一致）
```

## 注意事项

1. `instance_id` 必须是每次查询**当次**拿到的 24 位十六进制值，严禁复用上一次会话缓存的 id 或把 `<INSTANCE_ID>` 占位符当值发出去（见 `references/fund.md` 占位符约定）
2. 展示审批历史前必须**当次现场**调 `/tasks`，禁止凭对话上文/会话记忆编造节点/TXID/时间（见 `references/fund-approval-history.md` 硬性约束）
3. 流程定义接口返回的是 `mongo_id` 不是 `id`；查 XML / 审批配置时切勿混用（父 `common-query-chains.md#链-3`）
4. 按审批人筛选流程看板时，`approver_id` 来自 `/v1/management/approver/list`（父 `common-query-chains.md#链-4`）
5. 按业务线筛选流程看板时字段名是 `biz_line_id` 不是 `biz_line`（与项目筛选的 `biz_line` 不同，见父 `common-id-mapping.md#业务线字段名陷阱`）
6. 分页、路径白名单、MCP server（`armada`，工具 `armada__armada_get/post`）、wrapper 能力面等规则继承自父 skill `SKILL.md §注意事项`
