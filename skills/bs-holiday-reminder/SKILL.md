---
name: bs-holiday-reminder
description: 法定假期提醒(多订阅)。每天检查美国/新加坡/香港法定假期,按各频道/用户的订阅规则分别发送提醒。任何人可用自然语言订阅/退订/定制自己频道的提醒规则。
status: active
metadata:
  author: BS Team
  version: 3.0.0
---

# 法定假期提醒(多订阅版)

## 触发词
法定假期提醒、假期提醒、holiday reminder、订阅假期提醒、修改假期提醒规则

## 架构(重要:职责边界)

- **脚本** `scripts/check_holiday.py`(skill 自带,纯日期/判断逻辑,**不要改**):遍历所有订阅,各自做假期 API 调用与日期计算,把「该发给谁/发什么」以结构化行 `HOLIDAY_SEND <json>`(字段 channel/text/mention)打印到 stdout;坏规则/解析失败以 `HOLIDAY_ALERT <文本>` 行输出。脚本本身**不发消息、不依赖 Slack token**。用 `run_code`(python)运行它。
- **每日检查任务**(fleetent 内置 `schedule` 工具,cron):每天北京时间 10:00 触发 agent,agent 用 `run_code` 跑 `check_holiday.py`,再对每条 `HOLIDAY_SEND` 用内置 `send_im_message` 投递到其 channel;每条 `HOLIDAY_ALERT` 上报给管理员。
- **订阅目录** `/workspace/scripts/subscriptions/`(fleetent sandbox workspace 内,你可以直接用 `read_file`/`write_file` 读写):每个频道/用户一个 JSON 文件,文件名=频道或用户 ID(如 `C0AKYPT5WTH.json`、`U05K7R8TBST.json`)。

> NOTE (fleetent): 原 hermes 由「宿主机 host scheduler 每天 10:00 跑 check_holiday.py + 脚本直接 curl Slack chat.postMessage」。fleetent 无宿主机调度器/宿主机脚本部署假设——改用内置 `schedule` 工具(cron)按周期触发 agent + sandbox workspace 存订阅状态,投递由 agent 的 `send_im_message` 完成。脚本默认 `HOLIDAY_EMIT_MODE=stdout`;若 sandbox env 中确有 `SLACK_BOT_TOKEN`,可设 `HOLIDAY_EMIT_MODE=post` 让脚本自投递(备选方案①,见脚本头注)。

**你(模型)的唯一职责是按用户要求增/删/改订阅 JSON。绝对禁止:**
- ❌ 自己计算日期/判断哪天是假期(一律由脚本判断)
- ❌ 修改或重写脚本;脚本是纯逻辑入口,只许运行不许改
- ❌ 自行编造/手动拼接假期提醒文本(提醒文本由脚本输出,你只负责把 `HOLIDAY_SEND` 行原样投递)
- ❌ 修改或删除每日检查任务("提前几天"靠 advance_days 字段,不是改任务)
- ✅ 允许:用户要求立即/几分钟后跑一遍检查时,用 `schedule` 工具创建一次性任务(schedule_kind=once,如 5 分钟后触发),或当场直接 `run_code` 跑一次脚本并按上述投递,执行后任务自动结束

## 调度与执行(fleetent `schedule` 工具)

- **建立每日检查**(管理员一次性设置):用 `schedule` 工具 create_task,schedule_kind=cron,每天北京时间 10:00 触发本 agent 执行本 skill 的检查流程。
- **检查流程**(每次触发或手动跑时):
  1. `run_code`(python)运行 `scripts/check_holiday.py`(订阅目录 `/workspace/scripts/subscriptions/`;可用 `HOLIDAY_CHECK_TODAY=YYYY-MM-DD` 伪造今天做测试)。
  2. 解析 stdout:每行 `HOLIDAY_SEND <json>` → 用内置 `send_im_message` 把 `text` 投递到该条的 `channel`(原样投递,不改写文案)。
  3. 每行 `HOLIDAY_ALERT <文本>` → 作为管理员告警上报(发给管理员或当前对话说明),不要静默吞掉。
- **立即/几分钟后跑一遍**:用 `schedule` 工具 create_task,schedule_kind=once(触发时间如 5 分钟后),触发后执行同一检查流程;或当场直接走上面的检查流程跑一次。

> NOTE (fleetent): 写脚本失败、订阅目录写入失败等错误一律**原样报错并停止**,不要猜测或绕过。

## 订阅文件字段(subscriptions/<频道或用户ID>.json)

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| channel | str | 必填 | 提醒发送目标:频道 ID(C开头)或用户 ID(U开头,发DM) |
| advance_days | int 1-30 | 1 | 提前几天提醒 |
| regions | list | ["US","SG","HK"] | 关注地区,三者子集 |
| mention | str | "none" | "channel"=@所有人 / "none"=不@ |
| mute_until | str/null | null | "YYYY-MM-DD",该日(含)前静默 |
| extra_dates | list | [] | 自定义提醒 [{"date":"YYYY-MM-DD","label":"说明"}] |
| enabled | bool | true | false=暂停该订阅 |

字段写错不会丢提醒:脚本逐字段校验,非法值回退默认并附警告。

## 用户请求 → 操作示例

- "给我们频道也来个假期提醒,提前2天" → 新建 `subscriptions/<当前频道ID>.json`,channel=当前频道,advance_days=2
- "给我个人也发一份,只看美国" → 新建 `subscriptions/<该用户ID>.json`,channel=用户ID,regions=["US"]
- "改成提前3天" → 只改**当前频道对应订阅**的 advance_days,其他字段原样保留
- "取消我们频道的假期提醒" → 该订阅 enabled=false(或删除文件,先和用户确认)
- "现在的规则是什么" → 读当前频道的订阅文件,展示 JSON

**订阅文件命名与定位:**
- 文件名 = `<频道或用户ID>.json`(每目标一份时)或 `<频道或用户ID>__<别名>.json`(同一目标多份时,别名用简短英文,如 `U05K7R8TBST__us.json` / `U05K7R8TBST__hk.json`)
- 投递目标由文件内 channel 字段决定,文件名只是唯一键;同一个人/频道可以有多份互相独立的订阅
- 按消息来源频道 ID 定位订阅;用户说"我个人/私聊我"时用其用户 ID;同目标有多份时先列出所有订阅让用户指明改哪一份
- 新建第二份订阅时不要动已有订阅文件;改完回读文件,把完整 JSON 展示给用户确认
