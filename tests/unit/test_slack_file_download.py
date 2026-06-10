"""Slack gateway downloads non-image files into FileAttachment items."""

from unittest.mock import patch

import httpx
import pytest

import fleetent.im_gateway.slack as slack
from fleetent.im_gateway.normalizer import FileAttachment

_SHEET_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class _Resp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        pass


class _FakeClient:
    """Async-context httpx.AsyncClient stand-in with a scripted get()."""

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        self.calls.append(url)
        return self._handler(url)


def _patch_client(client):
    return patch("httpx.AsyncClient", return_value=client)


async def test_non_image_file_downloaded_into_file_attachment():
    files = [
        {
            "name": "笔记列表明细表.xlsx",
            "mimetype": _SHEET_MIME,
            "url_private": "https://files.slack.com/f.xlsx",
            "size": 1234,
        }
    ]
    client = _FakeClient(lambda url: _Resp(b"xlsx-bytes"))
    with _patch_client(client):
        out = await slack._download_attachments(files, "xoxb-tok")
    assert len(out) == 1
    fa = out[0]
    assert isinstance(fa, FileAttachment)
    assert fa.data == b"xlsx-bytes"
    assert fa.mime == _SHEET_MIME
    assert fa.filename == "笔记列表明细表.xlsx"
    assert fa.note == ""


async def test_oversize_file_not_downloaded_placeholder():
    files = [
        {
            "name": "big.csv",
            "mimetype": "text/csv",
            "url_private": "https://files.slack.com/big.csv",
            "size": 21 * 1024 * 1024,
        }
    ]
    client = _FakeClient(lambda url: pytest.fail("over-size file must not be downloaded"))
    with _patch_client(client):
        out = await slack._download_attachments(files, "xoxb-tok")
    assert len(out) == 1
    assert out[0].data is None
    assert "上限" in out[0].note
    assert client.calls == []


async def test_download_failure_degrades_to_placeholder():
    files = [
        {
            "name": "report.pdf",
            "mimetype": "application/pdf",
            "url_private": "https://files.slack.com/report.pdf",
            "size": 100,
        }
    ]

    def _boom(url):
        raise httpx.HTTPError("boom")

    client = _FakeClient(_boom)
    with _patch_client(client):
        out = await slack._download_attachments(files, "xoxb-tok")
    assert len(out) == 1
    assert out[0].data is None
    assert out[0].filename == "report.pdf"
    assert out[0].note != ""


async def test_image_still_returned_as_tuple():
    files = [{"mimetype": "image/png", "url_private": "https://files.slack.com/a.png"}]
    client = _FakeClient(lambda url: _Resp(b"png-bytes"))
    with _patch_client(client):
        out = await slack._download_attachments(files, "xoxb-tok")
    assert out == [(b"png-bytes", "image/png")]


async def test_image_and_file_mixed():
    files = [
        {"mimetype": "image/png", "url_private": "https://files.slack.com/a.png"},
        {
            "name": "data.csv",
            "mimetype": "text/csv",
            "url_private": "https://files.slack.com/data.csv",
            "size": 10,
        },
    ]
    client = _FakeClient(lambda url: _Resp(b"png" if url.endswith(".png") else b"csv"))
    with _patch_client(client):
        out = await slack._download_attachments(files, "xoxb-tok")
    assert out[0] == (b"png", "image/png")
    assert isinstance(out[1], FileAttachment)
    assert out[1].data == b"csv"
