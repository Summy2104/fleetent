#!/usr/bin/env python3
"""
orchestrate_email_sync.py — Email template batch sync orchestrator

Usage:
  python3 orchestrate_email_sync.py

Cron example:
  0 2 * * * python3 /path/to/orchestrate_email_sync.py

Required environment variables:
  SLACK_NOTIFY_CHANNEL         Target Slack channel ID
  HOST_MEDIA_DIR               Host-side per-agent media dir
                               (fleetent: <FLEETENT_HOME>/<agent>/media)

Optional environment variables:
  AGENT_ID            Agent to invoke (default: bs-intern)

NOTE (fleetent): host 端的 Slack 推送在 fleetent 上没有对应的 CLI 通道
  （OpenClaw 的 `openclaw message send` 无等价物——agent 内发 Slack 用内置
   `send_im_message` 工具，而非 host CLI）。本脚本的 Slack 汇总改为：让 agent
  在最后一轮对话里自行用 send_im_message 发到 SLACK_NOTIFY_CHANNEL，host 端
  只负责编排与本地日志。send_slack() 因此通过 `fleetent agent run` 把"请把这条
  汇总发到频道 X"的指令交给 agent 执行，而不是直接调 host 端发送命令。
"""

import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
AGENT_ID = os.environ.get("AGENT_ID", "bs-intern")


def get_workspace_dir() -> Path:
    """Returns host-side email-template-sync working directory for the agent.

    HOST_MEDIA_DIR is the per-agent media dir on host. Host-side runners like
    this script must export it themselves — see run_email_sync.sh.
    """
    host_media = os.environ.get("HOST_MEDIA_DIR")
    if not host_media:
        raise EnvironmentError("HOST_MEDIA_DIR is not set")
    return Path(host_media) / "email-template-sync"


# ── Logging ────────────────────────────────────────────────────────────────────
def setup_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


# ── Agent Call ─────────────────────────────────────────────────────────────────
def call_agent(message: str, timeout_ms: int = 600_000) -> str:
    """
    Calls the fleetent agent with the given message and returns the response text.

    Uses the standalone `fleetent agent run` CLI (no platform required). The agent
    runs the message to a final reply and prints it to stdout.
    """
    result = subprocess.run(
        [
            "fleetent", "agent", "run", message,
            "--agent", AGENT_ID,
            f"--timeout-ms={timeout_ms}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


# ── Slack Notification ─────────────────────────────────────────────────────────
def send_slack(message: str, channel: str) -> None:
    """Asks the agent to deliver the summary to Slack via its send_im_message tool.

    NOTE (fleetent): host 端没有直接发 Slack 的 CLI；让 agent 用内置
    send_im_message 工具把汇总发到目标频道。
    """
    call_agent(
        f"请用 send_im_message 工具把下面这条消息原样发送到 Slack 频道 {channel}，"
        f"不要做任何改写或补充：\n\n{message}"
    )


# ── Result Classification ──────────────────────────────────────────────────────
def classify_result(output: str) -> str:
    """Classifies agent output as success, skipped, or failure."""
    if "同步完成" in output:
        return "✅"
    if "跳过" in output:
        return "⏭️"
    return "❌"


# ── Slack Message Builder ──────────────────────────────────────────────────────
def build_slack_message(
    start_time: datetime,
    elapsed: int,
    success: list,
    skipped: list,
    failed: list,
) -> str:
    lines = [
        f"📧 邮件模版同步完成 [{start_time.strftime('%Y-%m-%d %H:%M')}]（耗时 {elapsed}s）",
        f"✅ 成功：{len(success)} 个  ⏭️ 跳过：{len(skipped)} 个  ❌ 失败：{len(failed)} 个",
    ]
    if success:
        lines += ["", "已转换："] + [f"  • {n}" for n in success]
    if failed:
        lines += ["", "失败："] + [f"  • {n} — {e}" for n, e in failed]
    return "\n".join(lines)


# ── Preflight ──────────────────────────────────────────────────────────────────
def preflight() -> tuple:
    """
    Validates required env vars and fleetent binary existence.
    Returns (slack_channel, fleetent_path).
    Calls sys.exit(1) on any missing requirement.
    """
    errors = []

    slack_channel = os.environ.get("SLACK_NOTIFY_CHANNEL", "")

    if not slack_channel:
        errors.append("SLACK_NOTIFY_CHANNEL is not set")
    if not os.environ.get("HOST_MEDIA_DIR"):
        errors.append("HOST_MEDIA_DIR is not set")

    fleetent_path = shutil.which("fleetent")
    if not fleetent_path:
        errors.append("fleetent binary not found in PATH")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    return slack_channel, fleetent_path


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    slack_channel, _ = preflight()

    workspace = get_workspace_dir()
    setup_logging(workspace / "orchestrate.log")

    start_time = datetime.now()
    logging.info("=== 邮件模版批量同步开始 ===")

    # 1. 清理上次残留的 scan-result.json
    scan_result_path = workspace / "scan-result.json"
    if scan_result_path.exists():
        scan_result_path.unlink()
        logging.info("已删除旧 scan-result.json")

    # 2. Trigger scan
    logging.info("触发 scan...")
    try:
        call_agent("重新加载skill common-email-template-scan，严格按着skill 扫描邮件模版")
        logging.info("scan 完成")
    except subprocess.CalledProcessError as e:
        msg = f"❌ scan 失败：{e.stderr[:200] if e.stderr else str(e)}"
        logging.error(msg)
        try:
            send_slack(msg, slack_channel)
        except Exception:
            pass
        sys.exit(1)

    # 3. Read scan-result.json
    if not scan_result_path.exists():
        msg = "❌ scan 未写出结果文件：scan-result.json 不存在"
        logging.error(msg)
        try:
            send_slack(msg, slack_channel)
        except Exception:
            pass
        sys.exit(1)

    templates = json.loads(scan_result_path.read_text(encoding="utf-8"))
    logging.info(f"共 {len(templates)} 个模版")

    if not templates:
        msg = "✅ 邮件模版全部最新，无需同步。"
        logging.info(msg)
        send_slack(msg, slack_channel)
        return

    # 4. Serial sync loop
    success, skipped, failed = [], [], []

    for item in templates:
        name = item["name"]
        file_id = item["fileId"]
        logging.info(f"同步：{name}（fileId={file_id}）")
        t0 = datetime.now()
        try:
            result = call_agent(
                f"重新加载skill common-email-template-sync，严格按着skill同步邮件模版 {name} --file-id {file_id}"
            )
            status = classify_result(result)
            elapsed_s = (datetime.now() - t0).seconds
            logging.info(f"{status} {name}（{elapsed_s}s）")
            if status == "✅":
                success.append(name)
            elif status == "⏭️":
                skipped.append(name)
            else:
                failed.append((name, result[:100]))
        except subprocess.CalledProcessError as e:
            err = (e.stderr or str(e))[:100]
            logging.error(f"❌ {name}：{err}")
            failed.append((name, err))

    # 5. Send Slack summary
    elapsed = (datetime.now() - start_time).seconds
    msg = build_slack_message(start_time, elapsed, success, skipped, failed)
    logging.info("发送 Slack 通知...")
    try:
        send_slack(msg, slack_channel)
        logging.info("Slack 通知已发送")
    except Exception as e:
        logging.error(f"Slack 通知发送失败：{e}")

    logging.info(f"=== 批量同步完成（{elapsed}s）===")


if __name__ == "__main__":
    main()
