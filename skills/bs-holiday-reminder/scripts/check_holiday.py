#!/usr/bin/env python3
"""法定假期提醒脚本 v3 — 多订阅版(fleetent 适配)

设计原则:
- 所有日期判断/通知决策都在本脚本内确定性实现;模型(机器人)唯一允许的
  操作是读写订阅 JSON,绝不参与日期计算。
- 多订阅:每个频道/用户一份订阅文件,互不影响,机器人可自助增删改。
- 投递(fleetent 方案②,默认):脚本不直接发消息,而是遍历所有订阅、做完
  日期计算后,把「该发给谁/发什么」以结构化 JSON 打印到 stdout
  (一行一条 `HOLIDAY_SEND <json>`,字段 channel/text/mention);
  agent 据此对每条用内置 `send_im_message` 工具投递。
  脚本本身不依赖任何 Slack token。

  > NOTE (fleetent): 备选方案① —— 若 sandbox 运行环境中 SLACK_BOT_TOKEN 可得,
  > 可把 EMIT_MODE 设为 "post" 让脚本自投递(post_to_slack 直接调
  > Slack chat.postMessage,与原 hermes 自投递等价)。默认 EMIT_MODE="stdout"
  > 走 fleetent 路径,不依赖该 env。

订阅目录(fleetent sandbox workspace 内,机器人可读写):
  /workspace/scripts/subscriptions/<name>.json
  (相对脚本位置 ../subscriptions/;可用 HOLIDAY_SUBS_DIR 覆盖绝对路径)

订阅文件字段:
  channel      : str  必填,Slack 频道 ID(C...)或用户 ID(U...,发 DM)
  advance_days : int 1-30   提前几天提醒(默认 1)
  regions      : list       US/SG/HK 子集(默认全部)
  mention      : str        "channel"(@所有人) | "none"(默认 none)
  mute_until   : str|null   "YYYY-MM-DD",该日(含)前静默
  extra_dates  : list       [{"date":"YYYY-MM-DD","label":"说明"}]
  enabled      : bool       false 则跳过(默认 true)

字段非法时回退默认值,并把警告附在该订阅的提醒里(fail-open,提醒不丢)。
正常情况输出 `HOLIDAY_SEND` 行供 agent 投递;无任何提醒=无 SEND 行。
执行告警(坏规则/解析失败)以 `HOLIDAY_ALERT` 行输出,供 agent 上报。
测试:HOLIDAY_CHECK_TODAY=YYYY-MM-DD 伪造"今天"。
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
HOLIDAY_API_BASE = "https://date.nager.at/api/v3/PublicHolidays"
SLACK_API = "https://slack.com/api/chat.postMessage"

# fleetent 适配:默认 "stdout"(发结构化 HOLIDAY_SEND 行,由 agent 用 send_im_message 投递)。
# 设为 "post" 走备选方案①(脚本自投递,需 SLACK_BOT_TOKEN 在 env 中)。
EMIT_MODE = os.environ.get("HOLIDAY_EMIT_MODE", "stdout").strip().lower()

ALL_REGIONS = {
    "US": {"name": "美国", "flag": "🇺🇸"},
    "SG": {"name": "新加坡", "flag": "🇸🇬"},
    "HK": {"name": "中国香港", "flag": "🇭🇰"},
}

DEFAULTS = {
    "advance_days": 1,
    "regions": ["US", "SG", "HK"],
    "mention": "none",
    "mute_until": None,
    "extra_dates": [],
    "enabled": True,
}

_holiday_cache: dict = {}


def subs_dir() -> Path:
    """订阅目录:fleetent sandbox workspace 内的 scripts/subscriptions/。

    默认相对脚本位置取 ../subscriptions/(脚本在 scripts/ 下时即
    /workspace/scripts/subscriptions/);可用 HOLIDAY_SUBS_DIR 覆盖绝对路径。
    """
    override = os.environ.get("HOLIDAY_SUBS_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "subscriptions"


def parse_date(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except Exception:
        return None


def load_subscription(p: Path):
    """逐字段校验;非法字段回退默认并记录警告。返回 (sub, warnings) 或 (None, err)。"""
    warnings = []
    sub = dict(DEFAULTS)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("顶层不是 JSON 对象")
    except Exception as e:
        return None, [f"订阅文件 {p.name} 解析失败({e}),已跳过"]

    ch = raw.get("channel")
    if not (isinstance(ch, str) and ch[:1] in ("C", "U", "D") and len(ch) > 5):
        return None, [f"订阅文件 {p.name} 的 channel={ch!r} 非法,已跳过"]
    sub["channel"] = ch

    ad = raw.get("advance_days")
    if ad is not None:
        if isinstance(ad, int) and 1 <= ad <= 30:
            sub["advance_days"] = ad
        else:
            warnings.append(f"advance_days={ad!r} 非法(需 1-30 整数),使用默认 1")

    rg = raw.get("regions")
    if rg is not None:
        if isinstance(rg, list) and rg and all(r in ALL_REGIONS for r in rg):
            sub["regions"] = rg
        else:
            warnings.append(f"regions={rg!r} 非法(需 US/SG/HK 非空子集),使用默认全部")

    mt = raw.get("mention")
    if mt is not None:
        if mt in ("channel", "none"):
            sub["mention"] = mt
        else:
            warnings.append(f"mention={mt!r} 非法(需 channel/none),使用默认 none")

    mu = raw.get("mute_until")
    if mu is not None:
        if parse_date(mu):
            sub["mute_until"] = mu
        else:
            warnings.append(f"mute_until={mu!r} 非法(需 YYYY-MM-DD),忽略")

    ed = raw.get("extra_dates")
    if ed is not None:
        ok = []
        if isinstance(ed, list):
            for item in ed:
                if isinstance(item, dict) and parse_date(item.get("date")):
                    ok.append({"date": item["date"], "label": str(item.get("label", "自定义提醒"))})
                else:
                    warnings.append(f"extra_dates 含非法条目 {item!r},已忽略")
            sub["extra_dates"] = ok
        else:
            warnings.append(f"extra_dates={ed!r} 非法(需列表),忽略")

    if raw.get("enabled") is False:
        sub["enabled"] = False

    return sub, warnings


def get_holidays(year: int, country_code: str) -> dict:
    """返回 {date: 假期名};带跨订阅缓存,API 失败返回空(静默,不误报)。"""
    key = (year, country_code)
    if key in _holiday_cache:
        return _holiday_cache[key]
    url = f"{HOLIDAY_API_BASE}/{year}/{country_code}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        _holiday_cache[key] = {}
        return {}
    out = {}
    for h in data:
        if not h.get("global", False):
            continue
        d = parse_date(h.get("date"))
        if d:
            out[d] = {
                "local_name": h.get("localName") or h.get("name"),
                "en_name": h.get("name"),
            }
    _holiday_cache[key] = out
    return out


def build_message(sub, today):
    """按订阅规则计算提醒文本;无事返回 None。"""
    mu = parse_date(sub.get("mute_until")) if sub.get("mute_until") else None
    if mu and today <= mu:
        return None

    target = today + timedelta(days=sub["advance_days"])
    alerts = []
    for code in sub["regions"]:
        info = ALL_REGIONS[code]
        holidays = get_holidays(target.year, code)
        if target not in holidays:
            continue
        if (target - timedelta(days=1)) in holidays:
            continue  # 连续假期中间日,只在段首前提醒一次
        end = target
        while (end + timedelta(days=1)) in holidays:
            end += timedelta(days=1)
        days = (end - target).days + 1
        alerts.append({
            "region": f"{info['flag']} {info['name']}",
            "name": holidays[target]["local_name"],
            "en_name": (holidays[target]["en_name"]
                        if holidays[target]["en_name"] != holidays[target]["local_name"] else None),
            "days": days, "start": target, "end": end,
        })

    extra_hits = [e for e in sub["extra_dates"] if parse_date(e["date"]) == target]
    if not alerts and not extra_hits:
        return None

    out = []
    if sub["mention"] == "channel":
        out.append("<!channel>")
        out.append("")
    out.append("📢 *【法定假期提醒】*")
    when = "明天" if sub["advance_days"] == 1 else f"{sub['advance_days']} 天后"
    out.append(f"{when}（{target.strftime('%Y-%m-%d')}）有以下安排：\n")
    for a in alerts:
        if a["days"] > 1:
            rng = f"{a['start'].strftime('%m/%d')}-{a['end'].strftime('%m/%d')}"
            out.append(f"{a['region']} - {a['name']}（连续{a['days']}天，{rng}）")
        else:
            out.append(f"{a['region']} - {a['name']}")
        if a["en_name"]:
            out.append(f"   ({a['en_name']})")
        out.append("")
    for e in extra_hits:
        out.append(f"📌 {e['label']}（{e['date']}）")
        out.append("")
    out.append("请注意相关业务安排。")
    return "\n".join(out)


def post_to_slack(channel, text):
    """备选方案①(EMIT_MODE="post"):脚本自投递,直接调 chat.postMessage。

    成功返回 None,失败返回错误描述。fleetent 默认路径不用此函数
    (走 EMIT_MODE="stdout" 由 agent 用 send_im_message 投递)。
    """
    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    if not token:
        return "SLACK_BOT_TOKEN 不在环境中"
    body = json.dumps({"channel": channel, "text": text, "mrkdwn": True}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_API, data=body,
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            r = json.loads(resp.read().decode("utf-8"))
        if not r.get("ok"):
            return f"Slack API: {r.get('error')}"
        return None
    except Exception as e:
        return f"发送异常: {e}"


def main():
    override = os.environ.get("HOLIDAY_CHECK_TODAY")
    today = parse_date(override) if override else datetime.now(BEIJING_TZ).date()
    if today is None:
        today = datetime.now(BEIJING_TZ).date()

    d = subs_dir()
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    errors = []
    if not files:
        errors.append(f"订阅目录为空或不存在: {d}")

    for p in files:
        sub, warnings = load_subscription(p)
        if sub is None:
            errors.extend(warnings)
            continue
        if not sub["enabled"]:
            continue
        msg = build_message(sub, today)
        if msg is None and warnings:
            # 无提醒但规则有问题:作为管理员告警输出,避免坏规则永远无人发现
            errors.append(f"[{p.name}] 规则字段非法已回退默认: " + "；".join(warnings))
            continue
        if msg is None:
            continue
        if warnings:
            msg += "\n\n⚠️ 部分规则字段非法已回退默认: " + "；".join(warnings)

        if EMIT_MODE == "post":
            # 备选方案①:脚本自投递(需 SLACK_BOT_TOKEN)
            err = post_to_slack(sub["channel"], msg)
            if err:
                errors.append(f"[{p.name} → {sub['channel']}] 发送失败: {err}")
        else:
            # fleetent 默认方案②:结构化输出,由 agent 用 send_im_message 投递。
            # mention 已内联进 text(<!channel>),此处仅透传供 agent 参考。
            print("HOLIDAY_SEND " + json.dumps(
                {"channel": sub["channel"], "text": msg, "mention": sub["mention"]},
                ensure_ascii=False))

    # 执行告警(坏规则/解析失败/发送失败):以 HOLIDAY_ALERT 行输出,供 agent 上报管理员
    for e in errors:
        print("HOLIDAY_ALERT " + e)


if __name__ == "__main__":
    main()
