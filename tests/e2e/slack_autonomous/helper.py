"""Slack Web API helper CLI — the mechanical "hands" of the autonomous e2e suite.

Subcommands ``send`` / ``read`` / ``upload`` / ``download`` / ``resolve`` each emit a
single JSON object to stdout and exit 0/1 per ``_pure.exit_code_for``. No LLM, no
verdict — decision-making lives in the driver (the slack-e2e-autonomous skill).

Credentials/targets come from CLI flags or ``SLACK_E2E_*`` env vars; never hardcoded.

    uv run python -m tests.e2e.slack_autonomous.helper resolve
    uv run python -m tests.e2e.slack_autonomous.helper send --text "hi" --thread-ts 123.45
    uv run python -m tests.e2e.slack_autonomous.helper read --thread-ts 123.45 --after-ts 123.45
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

from . import _pure

ENV_TOKEN = "SLACK_E2E_TOKEN"
ENV_BOT = "SLACK_E2E_BOT_USER_ID"
ENV_CHANNEL = "SLACK_E2E_CHANNEL"


def _opt(value: str | None, env: str) -> str | None:
    return value or os.environ.get(env)


def _client(token: str) -> Any:
    # Imported lazily so unit tests importing sibling pure modules need no slack_sdk.
    from slack_sdk import WebClient

    return WebClient(token=token)


def cmd_send(args: argparse.Namespace) -> dict[str, Any]:
    token = _opt(args.token, ENV_TOKEN)
    channel = _opt(args.channel, ENV_CHANNEL)
    if not token:
        return _pure.error_result("missing token (SLACK_E2E_TOKEN)")
    if not channel:
        return _pure.error_result("missing channel (SLACK_E2E_CHANNEL)")
    from slack_sdk.errors import SlackApiError

    try:
        resp = _client(token).chat_postMessage(
            channel=channel, text=args.text, thread_ts=args.thread_ts
        )
    except SlackApiError as exc:
        return _pure.error_result(f"chat_postMessage failed: {exc}")
    return _pure.ok_result(ts=resp["ts"], channel=resp["channel"])


def cmd_read(args: argparse.Namespace) -> dict[str, Any]:
    token = _opt(args.token, ENV_TOKEN)
    channel = _opt(args.channel, ENV_CHANNEL)
    bot = _opt(args.bot_user_id, ENV_BOT)
    if not (token and channel and bot):
        return _pure.error_result("missing token/channel/bot_user_id")
    from slack_sdk.errors import SlackApiError

    client = _client(token)
    deadline = time.monotonic() + args.timeout
    while True:
        try:
            if args.thread_ts:
                raw = client.conversations_replies(channel=channel, ts=args.thread_ts)
            else:
                raw = client.conversations_history(channel=channel)
        except SlackApiError as exc:
            return _pure.error_result(f"read failed: {exc}")
        new = _pure.filter_new_bot_messages(
            list(raw.get("messages", [])), bot_user_id=bot, after_ts=args.after_ts
        )
        if new:
            return _pure.ok_result(messages=new, timed_out=False)
        if time.monotonic() >= deadline:
            return _pure.ok_result(messages=[], timed_out=True)
        time.sleep(args.poll_interval)


def cmd_upload(args: argparse.Namespace) -> dict[str, Any]:
    token = _opt(args.token, ENV_TOKEN)
    channel = _opt(args.channel, ENV_CHANNEL)
    if not (token and channel):
        return _pure.error_result("missing token/channel")
    from slack_sdk.errors import SlackApiError

    try:
        # files_upload_v2 wraps getUploadURLExternal → PUT → completeUploadExternal.
        resp = _client(token).files_upload_v2(
            channel=channel, file=args.file, title=args.title, thread_ts=args.thread_ts
        )
    except SlackApiError as exc:
        return _pure.error_result(f"upload failed: {exc}")
    files = resp.get("files") or ([resp["file"]] if resp.get("file") else [])
    file_id = files[0]["id"] if files else None
    return _pure.ok_result(file_id=file_id)


def cmd_download(args: argparse.Namespace) -> dict[str, Any]:
    import httpx

    token = _opt(args.token, ENV_TOKEN)
    if not token:
        return _pure.error_result("missing token (SLACK_E2E_TOKEN)")
    url = args.url
    if not url and args.file_id:
        from slack_sdk.errors import SlackApiError

        try:
            info = _client(token).files_info(file=args.file_id)
        except SlackApiError as exc:
            return _pure.error_result(f"files_info failed: {exc}")
        url = info["file"]["url_private_download"]
    if not url:
        return _pure.error_result("need --url or --file-id")
    out = args.out or _pure.safe_local_filename(url.rsplit("/", 1)[-1])
    resp = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, follow_redirects=True)
    if resp.status_code != 200:
        return _pure.error_result(f"download HTTP {resp.status_code}")
    with open(out, "wb") as fh:
        fh.write(resp.content)
    return _pure.ok_result(path=out, bytes=len(resp.content))


def cmd_resolve(args: argparse.Namespace) -> dict[str, Any]:
    token = _opt(args.token, ENV_TOKEN)
    bot = _opt(args.bot_user_id, ENV_BOT)
    channel = _opt(args.channel, ENV_CHANNEL)
    if not token:
        return _pure.build_resolve_report(
            token_ok=False, bot_user_id=bot, bot_found=False, channel_ok=False
        )
    from slack_sdk.errors import SlackApiError

    client = _client(token)
    token_ok = bot_found = channel_ok = False
    missing_scopes: list[str] = []
    try:
        client.auth_test()
        token_ok = True
    except SlackApiError:
        token_ok = False
    if token_ok and bot:
        try:
            client.users_info(user=bot)
            bot_found = True
        except SlackApiError:
            bot_found = False
    if token_ok and channel:
        try:
            client.conversations_info(channel=channel)
            channel_ok = True
        except SlackApiError as exc:
            if "missing_scope" in str(exc):
                missing_scopes.append("channels:read")
    return _pure.build_resolve_report(
        token_ok=token_ok,
        bot_user_id=bot,
        bot_found=bot_found,
        channel_ok=channel_ok,
        missing_scopes=tuple(missing_scopes),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="slack-e2e-helper", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--token")
        p.add_argument("--channel")

    p_send = sub.add_parser("send", help="post a text message (optionally into a thread)")
    common(p_send)
    p_send.add_argument("--text", required=True)
    p_send.add_argument("--thread-ts")
    p_send.set_defaults(func=cmd_send)

    p_read = sub.add_parser("read", help="poll for new bot messages in a thread/channel")
    common(p_read)
    p_read.add_argument("--bot-user-id")
    p_read.add_argument("--thread-ts")
    p_read.add_argument("--after-ts")
    p_read.add_argument("--timeout", type=float, default=60.0)
    p_read.add_argument("--poll-interval", type=float, default=3.0)
    p_read.set_defaults(func=cmd_read)

    p_up = sub.add_parser("upload", help="upload a local file as an attachment")
    common(p_up)
    p_up.add_argument("--file", required=True)
    p_up.add_argument("--title")
    p_up.add_argument("--thread-ts")
    p_up.set_defaults(func=cmd_upload)

    p_dl = sub.add_parser("download", help="download a file the agent posted, for verification")
    common(p_dl)
    p_dl.add_argument("--url")
    p_dl.add_argument("--file-id")
    p_dl.add_argument("--out")
    p_dl.set_defaults(func=cmd_download)

    p_res = sub.add_parser("resolve", help="validate token/bot/channel preconditions")
    common(p_res)
    p_res.add_argument("--bot-user-id")
    p_res.set_defaults(func=cmd_resolve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = args.func(args)
    print(_pure.dump_json(result))
    return _pure.exit_code_for(result)


if __name__ == "__main__":
    sys.exit(main())
